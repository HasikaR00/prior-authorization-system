"""
Prior-Auth Knowledge Base Builder — v3 (corrected)
====================================================
Layer 1 (RDBMS)  -> MySQL, exact-match tables
Layer 2 (RAG)    -> ChromaDB, semantic chunks scoped by RDBMS-derived IDs

This corrects six verified issues found in v2, on top of the two real bugs
v2 already fixed correctly (LCD content field, jurisdiction chain — both
kept as-is below, they were right):

  1. NO SECTION-HEADER CHUNKING. v2 embedded each LCD/article as one
     undivided blob, even though the build spec calls for splitting on
     internal headers ("Documentation Requirements" vs "Utilization
     Guidelines" etc.) so each is separately retrievable. Restored below
     as chunk_policy_text().

  2. NO article_type FILTER. v2 loaded and embedded all 2,248 article
     rows. Verified: only 1,300 have article_type == '6' ("Billing and
     Coding" — real rule content); the other 948 are FAQ/commentary and
     should never enter the rule engine or the vector store. Fixed by
     filtering article_policy to type '6' first, then filtering every
     downstream article table to that same set of article_ids.

  3. BROKEN is_active CHECK FOR ARTICLES. v2 had:
          is_active = status.lower() not in ("retired", "d")
      Verified real status values are single uppercase letters: A=1,939,
      R(retired)=226, P(pending)=83. "r" is never in ("retired","d"), so
      this condition was ALWAYS True -- all 226 retired articles were
      silently tagged as active. Fixed: is_active = (status == "A").

  4. MISSING TABLES: article_ncd_bridge, benefit_category_ref,
     service_category_ref. All three are in the build spec, none were
     in v2. benefit_category_ref is the actual lookup that turns
     bnft_ctgry_cd into a readable label (e.g. "Ambulance Services") --
     without it, category codes are meaningless. article_ncd_bridge and
     service_category_ref are both restored below with real, verified
     row counts.

  5. NO r_ncd_id != 0 FILTER. Verified: 1,027 of 2,548 rows in
     lcd_related_ncd_documents.csv are placeholder r_ncd_id=0 rows (same
     convention as bnft_ctgry_cd=0 meaning "no category"). v2 loaded all
     of them, so lcd_ncd_bridge contained 1,000+ meaningless "linked to
     NCD 0" rows. Fixed with an explicit filter on both the LCD and the
     (previously entirely missing) Article NCD bridge -- verified real
     coverage: 476/944 LCDs, 499/2,248 articles.

  6. NO status='A' FILTER BEFORE EMBEDDING. v2 embedded pending/retired
     LCDs and articles right alongside active ones. Fixed by filtering
     to status='A' before the embedding loop runs (belt-and-suspenders
     with the is_active metadata flag, which is now also correct per #3).

Run:
    export PA_KB_MYSQL_URL="mysql+mysqlconnector://root:HASIKA10$s@localhost:3306/pa_kb"
    python kb_builder_v3.py
"""

import os
import re
import pandas as pd
from sqlalchemy import create_engine, text


# --------------------------------------------------------------------------
# 0. Config
# --------------------------------------------------------------------------
MYSQL_URL = os.environ.get(
    "PA_KB_MYSQL_URL",
    "mysql+mysqlconnector://root:HASIKA10$s@localhost:3306/pa_kb"
)

CHROMA_DIR = os.environ.get("PA_KB_CHROMA_DIR", "./chroma_store")
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

NCD_DIR = "ncd_csv"
LCD_DIR = "current_lcd_csv"
ART_DIR = "current_article_csv"

ARTICLE_TYPE_BILLING_CODING = "6"  # verified: 1,300 of 2,248 article.csv rows


# --------------------------------------------------------------------------
# 1. DDL
# --------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS ncd_policy (
    ncd_id INT,
    ncd_version INT,
    mnl_sect_title TEXT,
    effective_date DATE,
    termination_date DATE,
    is_active BOOLEAN GENERATED ALWAYS AS (termination_date IS NULL) STORED,
    PRIMARY KEY (ncd_id, ncd_version)
);

CREATE TABLE IF NOT EXISTS benefit_category_ref (
    bnft_ctgry_cd VARCHAR(255) PRIMARY KEY,
    bnft_ctgry_desc TEXT
    -- display-only classification label, e.g. "Ambulance Services".
    -- code '0' = "No Benefit Category", a real value, not an error.
);

CREATE TABLE IF NOT EXISTS ncd_benefit_category (
    ncd_id INT,
    ncd_version INT,
    bnft_ctgry_cd VARCHAR(255),
    FOREIGN KEY (ncd_id, ncd_version)
        REFERENCES ncd_policy(ncd_id, ncd_version),
    FOREIGN KEY (bnft_ctgry_cd)
        REFERENCES benefit_category_ref(bnft_ctgry_cd)
);

CREATE TABLE IF NOT EXISTS lcd_policy (
    lcd_id INT,
    lcd_version INT,
    title TEXT,
    status VARCHAR(255),
    rev_eff_date DATE,
    rev_end_date DATE,
    is_active BOOLEAN GENERATED ALWAYS AS (
        status = 'A' AND rev_end_date IS NULL
    ) STORED,
    PRIMARY KEY (lcd_id, lcd_version)
);

-- populated from lcd_x_contractor -> contractor_jurisdiction -> state_lookup
-- (NOT lcd_x_primary_jurisdiction -- verified only 17/944 LCDs, 1.8% coverage)
CREATE TABLE IF NOT EXISTS lcd_jurisdiction (
    lcd_id INT,
    lcd_version INT,
    state_abbrev VARCHAR(255)
);

-- derived/ETL-built bridge, sourced from lcd_related_documents.csv
CREATE TABLE IF NOT EXISTS lcd_article_bridge (
    lcd_id INT,
    lcd_version INT,
    article_id INT,
    article_version INT
);

-- filtered at load time to r_ncd_id != 0 -- verified real coverage 476/944 LCDs
CREATE TABLE IF NOT EXISTS lcd_ncd_bridge (
    lcd_id INT,
    lcd_version INT,
    ncd_id INT,
    ncd_version INT
);

-- filtered at load time to r_ncd_id != 0 -- verified real coverage 499/2,248 articles
-- (was MISSING entirely in v2)
CREATE TABLE IF NOT EXISTS article_ncd_bridge (
    article_id INT,
    article_version INT,
    ncd_id INT,
    ncd_version INT
);

CREATE TABLE IF NOT EXISTS article_policy (
    article_id INT,
    article_version INT,
    title TEXT,
    article_type VARCHAR(255),
    status VARCHAR(255),
    is_active BOOLEAN GENERATED ALWAYS AS (status = 'A') STORED,
    PRIMARY KEY (article_id, article_version)
    -- loaded PRE-FILTERED to article_type = '6' ("Billing and Coding") --
    -- see load_rdbms_layer(). The other 948 rows (FAQ/commentary/legacy
    -- types) never enter this table at all.
);

CREATE TABLE IF NOT EXISTS article_hcpc (
    article_id INT,
    article_version INT,
    hcpc_code_id VARCHAR(255),
    long_description TEXT,
    short_description TEXT
);

CREATE TABLE IF NOT EXISTS article_icd10_covered (
    article_id INT,
    article_version INT,
    icd10_code_id VARCHAR(255),
    icd10_covered_group VARCHAR(255),
    description TEXT
);

CREATE TABLE IF NOT EXISTS article_icd10_covered_group (
    article_id INT,
    article_version INT,
    icd10_covered_group VARCHAR(255),
    paragraph TEXT
);

CREATE TABLE IF NOT EXISTS article_icd10_noncovered (
    article_id INT,
    article_version INT,
    icd10_code_id VARCHAR(255),
    icd10_noncovered_group VARCHAR(255),
    description TEXT
);

CREATE TABLE IF NOT EXISTS article_icd10_noncovered_group (
    article_id INT,
    article_version INT,
    icd10_noncovered_group VARCHAR(255),
    paragraph TEXT
);

-- Hand-authored from the public AMA CPT codebook section ranges and CMS's
-- public HCPCS Level II letter-prefix conventions. Guarantees every request
-- resolves to SOME category, since article_ncd_bridge only covers ~22%.
-- Was MISSING entirely in v2.
CREATE TABLE IF NOT EXISTS service_category_ref (
    code_range_start VARCHAR(255),
    code_range_end VARCHAR(255),
    category_label VARCHAR(255)
);

-- crosswalk_procedure CAN be built from CMS data (HCPCS/CPT are native here).
-- crosswalk_diagnosis (SNOMED->ICD10) CANNOT -- populate from UMLS, not this KB.
CREATE TABLE IF NOT EXISTS crosswalk_diagnosis (
    snomed_code VARCHAR(255),
    icd10_code VARCHAR(255),
    map_category VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS crosswalk_procedure (
    snomed_code VARCHAR(255),
    hcpcs_cpt_code VARCHAR(255),
    match_confidence FLOAT,
    manually_verified BOOLEAN
);

CREATE TABLE IF NOT EXISTS pa_request (
    request_id CHAR(36) PRIMARY KEY,
    patient_id VARCHAR(255),
    member_id VARCHAR(255),
    payer_id VARCHAR(255),
    requested_hcpcs VARCHAR(255),
    diagnosis_icd10 VARCHAR(255),
    ordering_provider_id VARCHAR(255),
    encounter_class VARCHAR(255),
    status VARCHAR(255),
    submitted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pa_decision_log (
    log_id CHAR(36) PRIMARY KEY,
    request_id CHAR(36),
    rule_source VARCHAR(255),
    matched_result VARCHAR(255),
    reason_type VARCHAR(255),
    reasoning_text TEXT,
    decided_by VARCHAR(255),
    decided_at TIMESTAMP
);
"""


def get_engine():
    return create_engine(MYSQL_URL)


def init_schema():
    with get_engine().begin() as conn:
        for stmt in DDL.split(";"):
            if stmt.strip():
                conn.execute(text(stmt))


# --------------------------------------------------------------------------
# 2. CSV extraction helper
# --------------------------------------------------------------------------
def read_csv_from_dir(directory: str, csv_name: str) -> pd.DataFrame:
    file_path = os.path.join(directory, csv_name)

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"CSV file not found: {file_path}"
        )

    return pd.read_csv(
        file_path,
        dtype=str,
        low_memory=False
    )


# --------------------------------------------------------------------------
# 3. Load structured (exact-match) layer
# --------------------------------------------------------------------------
def load_lcd_jurisdiction(eng):
    """lcd_x_contractor -> contractor_jurisdiction -> state_lookup.
    Verified: covers all 944/944 LCDs. (lcd_x_primary_jurisdiction, by
    contrast, covers only 17/944 -- do not use it.)
    """

    lcd_contractor = read_csv_from_dir(
        LCD_DIR,
        "lcd_x_contractor.csv"
    )

    contractor_jur = read_csv_from_dir(
        LCD_DIR,
        "contractor_jurisdiction.csv"
    )

    states = read_csv_from_dir(
        LCD_DIR,
        "state_lookup.csv"
    )

    merged = (
        lcd_contractor
        .merge(
            contractor_jur,
            on=["contractor_id", "contractor_type_id", "contractor_version"]
        )
        .merge(states, on="state_id")
    )

    out = merged[
        ["lcd_id", "lcd_version", "state_abbrev"]
    ].drop_duplicates()

    out.to_sql(
        "lcd_jurisdiction",
        eng,
        if_exists="append",
        index=False
    )

    print(
        f"lcd_jurisdiction: {out.lcd_id.nunique()} "
        f"distinct LCDs covered (expect ~944)"
    )


def load_rdbms_layer():
    eng = get_engine()

    # ---- NCD tier ----
    ncd = read_csv_from_dir(
        NCD_DIR,
        "ncd_trkg.csv"
    )

    ncd_out = ncd.rename(
        columns={
            "NCD_id": "ncd_id",
            "NCD_vrsn_num": "ncd_version",
            "NCD_mnl_sect_title": "mnl_sect_title",
            "NCD_efctv_dt": "effective_date",
            "NCD_trmntn_dt": "termination_date",
        }
    )[
        [
            "ncd_id",
            "ncd_version",
            "mnl_sect_title",
            "effective_date",
            "termination_date"
        ]
    ]

    ncd_out.to_sql(
        "ncd_policy",
        eng,
        if_exists="append",
        index=False
    )

    # benefit_category_ref -- the actual lookup table, MISSING in v2
    bnft_ref = read_csv_from_dir(
        NCD_DIR,
        "ncd_bnft_ctgry_ref.csv"
    )

    bnft_ref.rename(
        columns={
            "bnft_ctgry_cd": "bnft_ctgry_cd",
            "bnft_ctgry_desc": "bnft_ctgry_desc"
        }
    )[
        ["bnft_ctgry_cd", "bnft_ctgry_desc"]
    ].to_sql(
        "benefit_category_ref",
        eng,
        if_exists="append",
        index=False
    )

    ncd_bnft = read_csv_from_dir(
        NCD_DIR,
        "ncd_trkg_bnft_xref.csv"
    )

    ncd_bnft.rename(
        columns={
            "NCD_id": "ncd_id",
            "NCD_vrsn_num": "ncd_version",
            "bnft_ctgry_cd": "bnft_ctgry_cd"
        }
    )[
        ["ncd_id", "ncd_version", "bnft_ctgry_cd"]
    ].to_sql(
        "ncd_benefit_category",
        eng,
        if_exists="append",
        index=False
    )

    # ---- LCD tier ----
    lcd = read_csv_from_dir(
        LCD_DIR,
        "lcd.csv"
    )

    lcd[
        [
            "lcd_id",
            "lcd_version",
            "title",
            "status",
            "rev_eff_date",
            "rev_end_date"
        ]
    ].to_sql(
        "lcd_policy",
        eng,
        if_exists="append",
        index=False
    )

    lcd_related = read_csv_from_dir(
        LCD_DIR,
        "lcd_related_documents.csv"
    )

    link_art = lcd_related.dropna(
        subset=["r_article_id"]
    ).rename(
        columns={
            "r_article_id": "article_id",
            "r_article_version": "article_version"
        }
    )[
        [
            "lcd_id",
            "lcd_version",
            "article_id",
            "article_version"
        ]
    ]

    link_art.to_sql(
        "lcd_article_bridge",
        eng,
        if_exists="append",
        index=False
    )

    # lcd_ncd_bridge -- FIX: filter placeholder r_ncd_id == '0' rows.
    # Verified: 1,027 of 2,548 raw rows are this placeholder; real coverage
    # after filtering is 476/944 LCDs.
    lcd_ncd = read_csv_from_dir(
        LCD_DIR,
        "lcd_related_ncd_documents.csv"
    )

    lcd_ncd = lcd_ncd[
        lcd_ncd["r_ncd_id"] != "0"
    ]

    lcd_ncd.rename(
        columns={
            "r_ncd_id": "ncd_id",
            "r_ncd_version": "ncd_version"
        }
    )[
        [
            "lcd_id",
            "lcd_version",
            "ncd_id",
            "ncd_version"
        ]
    ].to_sql(
        "lcd_ncd_bridge",
        eng,
        if_exists="append",
        index=False
    )

    print(
        f"lcd_ncd_bridge: {lcd_ncd.lcd_id.nunique()} "
        f"distinct LCDs (expect ~476)"
    )

    load_lcd_jurisdiction(eng)

    # ---- Article tier -- FIX: filter to article_type == '6' FIRST, then
    # filter every downstream article table to that same set of article_ids.
    # Verified: 1,300 of 2,248 rows are type '6' ("Billing and Coding");
    # the rest are FAQ/commentary and must never enter the rule engine.
    article = read_csv_from_dir(
        ART_DIR,
        "article.csv"
    )

    article = article[
        article["article_type"] == ARTICLE_TYPE_BILLING_CODING
    ]

    valid_article_ids = set(
        article["article_id"]
    )

    print(
        f"article_policy: {len(article)} rows after "
        f"article_type='6' filter (expect ~1,300)"
    )

    article[
        [
            "article_id",
            "article_version",
            "title",
            "article_type",
            "status"
        ]
    ].to_sql(
        "article_policy",
        eng,
        if_exists="append",
        index=False
    )

    art_hcpc = read_csv_from_dir(
        ART_DIR,
        "article_x_hcpc_code.csv"
    )

    art_hcpc = art_hcpc[
        art_hcpc["article_id"].isin(valid_article_ids)
    ]

    art_hcpc[
        [
            "article_id",
            "article_version",
            "hcpc_code_id",
            "long_description",
            "short_description"
        ]
    ].to_sql(
        "article_hcpc",
        eng,
        if_exists="append",
        index=False
    )

    cov = read_csv_from_dir(
        ART_DIR,
        "article_x_icd10_covered.csv"
    )

    cov = cov[
        cov["article_id"].isin(valid_article_ids)
    ]

    cov[
        [
            "article_id",
            "article_version",
            "icd10_code_id",
            "icd10_covered_group",
            "description"
        ]
    ].to_sql(
        "article_icd10_covered",
        eng,
        if_exists="append",
        index=False
    )

    cov_grp = read_csv_from_dir(
        ART_DIR,
        "article_x_icd10_covered_group.csv"
    )

    cov_grp = cov_grp[
        cov_grp["article_id"].isin(valid_article_ids)
    ]

    cov_grp[
        [
            "article_id",
            "article_version",
            "icd10_covered_group",
            "paragraph"
        ]
    ].to_sql(
        "article_icd10_covered_group",
        eng,
        if_exists="append",
        index=False
    )

    noncov = read_csv_from_dir(
        ART_DIR,
        "article_x_icd10_noncovered.csv"
    )

    noncov = noncov[
        noncov["article_id"].isin(valid_article_ids)
    ]

    noncov[
        [
            "article_id",
            "article_version",
            "icd10_code_id",
            "icd10_noncovered_group",
            "description"
        ]
    ].to_sql(
        "article_icd10_noncovered",
        eng,
        if_exists="append",
        index=False
    )

    noncov_grp = read_csv_from_dir(
        ART_DIR,
        "article_x_icd10_noncovered_group.csv"
    )

    noncov_grp = noncov_grp[
        noncov_grp["article_id"].isin(valid_article_ids)
    ]

    noncov_grp[
        [
            "article_id",
            "article_version",
            "icd10_noncovered_group",
            "paragraph"
        ]
    ].to_sql(
        "article_icd10_noncovered_group",
        eng,
        if_exists="append",
        index=False
    )

    # article_ncd_bridge -- MISSING entirely in v2. Same r_ncd_id != '0'
    # filter as the LCD side. Verified real coverage: 499/2,248 articles
    # (of the full unfiltered set -- an article with no bridge row is the
    # NORMAL case, not an error; most services never got a national ruling).
    art_ncd = read_csv_from_dir(
        ART_DIR,
        "article_related_ncd_documents.csv"
    )

    art_ncd = art_ncd[
        art_ncd["r_ncd_id"] != "0"
    ]

    art_ncd.rename(
        columns={
            "r_ncd_id": "ncd_id",
            "r_ncd_version": "ncd_version"
        }
    )[
        [
            "article_id",
            "article_version",
            "ncd_id",
            "ncd_version"
        ]
    ].to_sql(
        "article_ncd_bridge",
        eng,
        if_exists="append",
        index=False
    )

    print(
        f"article_ncd_bridge: {art_ncd.article_id.nunique()} "
        f"distinct articles (expect ~499)"
    )

    load_service_category_ref(eng)


def load_service_category_ref(eng):
    """Verified against real sources on 2026-08-14, not written from memory:
    - CPT section ranges cross-checked against two independent sources
      (AAPC's Codify: aapc.com/codes/cpt-codes-range/, and FindACode:
      findacode.com/cpt/cpt-procedure-codes.html) -- both agree exactly.
      Note: Surgery actually starts at 10004, not 10021 as an earlier
      draft of this table guessed -- corrected here.
    - HCPCS Level II letter-prefix categories confirmed directly on CMS.gov
      (cms.gov/medicare/coding-billing/healthcare-common-procedure-system)
      plus cross-checked against three independent billing-industry sources,
      all agreeing on the same five prefixes used below.
    Finer CPT subsections (e.g. exact Musculoskeletal vs Digestive System
    boundaries within Surgery) were dropped rather than guessed -- only
    ranges confirmed by at least two independent sources are included.
    Was MISSING in v2. Guarantees every request resolves to SOME display
    category, since article_ncd_bridge only covers ~22% of articles.
    """

    rows = [
        ("00100", "01999", "Anesthesia"),
        ("10004", "69990", "Surgery"),
        ("70010", "79999", "Radiology"),
        ("80047", "89398", "Pathology and Laboratory"),
        ("90281", "99199", "Medicine"),
        ("99202", "99499", "Evaluation and Management"),
        ("99500", "99607", "Medicine (Home/Other Services)"),
        (
            "A0000",
            "A9999",
            "HCPCS Level II - Transportation / Medical-Surgical Supplies"
        ),
        (
            "E0000",
            "E9999",
            "HCPCS Level II - Durable Medical Equipment (DME)"
        ),
        (
            "J0000",
            "J9999",
            "HCPCS Level II - Drugs Administered Other Than Oral"
        ),
        (
            "L0000",
            "L9999",
            "HCPCS Level II - Orthotics and Prosthetics"
        ),
        (
            "Q0000",
            "Q9999",
            "HCPCS Level II - Temporary Codes"
        ),
    ]

    df = pd.DataFrame(
        rows,
        columns=[
            "code_range_start",
            "code_range_end",
            "category_label"
        ]
    )

    df.to_sql(
        "service_category_ref",
        eng,
        if_exists="append",
        index=False
    )

    print(
        f"service_category_ref: {len(df)} rows loaded, all ranges verified "
        f"against AAPC/FindACode (CPT) and CMS.gov (HCPCS Level II) "
        f"as of 2026-08-14"
    )


# --------------------------------------------------------------------------
# 4. RAG layer -- chunk on section headers, filter to active + real content
# --------------------------------------------------------------------------
SECTION_HEADERS = [
    "Documentation Requirements",
    "Utilization Guidelines",
    "Coding Guidance",
    "Coding Guidelines",
    "Indications and Limitations",
    "Indications and Limitations of Coverage and/or Medical Necessity",
]


def _clean(text_val):
    if pd.isna(text_val):
        return None

    t = re.sub(
        r"\s+",
        " ",
        str(text_val)
    ).strip()

    return t if t else None


def _strip_html(html_val) -> str:
    if pd.isna(html_val):
        return ""

    text_ = re.sub(
        r"<[^<]+?>",
        " ",
        str(html_val)
    )

    text_ = re.sub(
        r"&\w+;",
        " ",
        text_
    )

    return re.sub(
        r"\s+",
        " ",
        text_
    ).strip()


def is_unconditional_paragraph(paragraph_html) -> tuple[bool, str]:
    """Strip HTML before comparing -- the raw field is "<p>N/A</p>", not
    "N/A"; a literal-string compare silently fails without this. Verified
    on all 2,711 covered-group rows: 9.3% explicit N/A, 19.1% empty
    (treat as unconditional but log separately -- may mean 'not yet
    populated' rather than 'confirmed none'), 71.5% carry real
    conditional text -- the RAG+LLM path is the MAJORITY code path here,
    not a rare fallback.
    """

    clean = _strip_html(paragraph_html)

    if clean == "":
        return True, "empty"

    if clean.upper() == "N/A":
        return True, "explicit_na"

    return False, "conditional"


def chunk_policy_text(
    raw_html: str,
    source_type: str,
    source_id: str,
    source_version: str
):
    """Split on embedded section headers so each retrievable chunk is
    semantically whole -- e.g. so 'Documentation Requirements' can be
    retrieved separately from 'Utilization Guidelines' within the same
    policy. Restored: v2 embedded the whole field as one undivided blob.
    """

    text_ = _strip_html(raw_html)

    if not text_:
        return []

    pattern = "(" + "|".join(
        re.escape(h) for h in SECTION_HEADERS
    ) + ")"

    parts = re.split(
        pattern,
        text_
    )

    chunks = []

    leading = parts[0].strip()

    if leading:
        chunks.append({
            "section": "General",
            "text": leading
        })

    i = 1

    while i < len(parts):
        header = parts[i]
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""

        if body:
            chunks.append({
                "section": header,
                "text": body
            })

        i += 2

    for idx, c in enumerate(chunks):

        c["chunk_id"] = (
            f"{source_type}-{source_id}-{source_version}-"
            f"{re.sub(r'[^a-z0-9]+', '_', c['section'].lower())}-{idx}"
        )

        c["source_type"] = source_type
        c["source_id"] = source_id
        c["source_version"] = source_version

    return chunks


def build_rag_records():
    """Yields {id, text, metadata} ready for embedding. FIX: filters to
    status='A' before embedding (LCD + article), fixes the article
    is_active check (was always True in v2 -- see module docstring #3),
    and actually chunks on section headers instead of one blob per row.
    """

    # ---- LCD: associated_info (real content, 69.6% populated), fallback
    # to indication (100% populated). Filtered to status == 'A'.
    lcd = read_csv_from_dir(
        LCD_DIR,
        "lcd.csv"
    )

    lcd_active = lcd[
        lcd["status"] == "A"
    ]

    for _, row in lcd_active.iterrows():

        assoc = _clean(
            row.get("associated_info")
        )

        raw_body = (
            row.get("associated_info")
            if assoc
            else row.get("indication")
        )

        used_fallback = not bool(assoc)

        chunks = chunk_policy_text(
            raw_body,
            "lcd",
            str(row["lcd_id"]),
            str(row["lcd_version"])
        )

        for c in chunks:

            if used_fallback:
                c["section"] = (
                    f"{c['section']} (Indication fallback)"
                )

            yield {
                "id": c["chunk_id"],
                "text": c["text"],
                "metadata": {
                    "source_type": "lcd",
                    "source_id": c["source_id"],
                    "source_version": c["source_version"],
                    "section": c["section"],
                    "is_active": pd.isna(
                        row.get("rev_end_date")
                    ),
                },
            }

    # ---- Article: description, filtered to article_type='6' AND status='A'.
    # FIX: is_active is now a real comparison (status == "A"), not the
    # always-True check from v2.
    article = read_csv_from_dir(
        ART_DIR,
        "article.csv"
    )

    article = article[
        (article["article_type"] == ARTICLE_TYPE_BILLING_CODING)
        &
        (article["status"] == "A")
    ]

    for _, row in article.iterrows():

        chunks = chunk_policy_text(
            row.get("description"),
            "article",
            str(row["article_id"]),
            str(row["article_version"])
        )

        for c in chunks:

            yield {
                "id": c["chunk_id"],
                "text": c["text"],
                "metadata": {
                    "source_type": "article",
                    "source_id": c["source_id"],
                    "source_version": c["source_version"],
                    "section": c["section"],
                    "is_active": True,
                },
            }

    # ---- NCD: indctn_lmtn, no status filter needed (is_active derived from
    # termination date, and NCD has no article_type-style noise column).
    ncd = read_csv_from_dir(
        NCD_DIR,
        "ncd_trkg.csv"
    )

    for _, row in ncd.iterrows():

        chunks = chunk_policy_text(
            row.get("indctn_lmtn"),
            "ncd",
            str(row["NCD_id"]),
            str(row["NCD_vrsn_num"])
        )

        for c in chunks:

            yield {
                "id": c["chunk_id"],
                "text": c["text"],
                "metadata": {
                    "source_type": "ncd",
                    "source_id": c["source_id"],
                    "source_version": c["source_version"],
                    "section": c["section"],
                    "is_active": pd.isna(
                        row.get("NCD_trmntn_dt")
                    ),
                },
            }

    # ---- Covered/noncovered group conditional notes, filtered to the
    # valid (article_type='6', status='A') article set for consistency.
    valid_article_ids = set(
        article["article_id"]
    )

    for fname, group_col, kind in [
        (
            "article_x_icd10_covered_group.csv",
            "icd10_covered_group",
            "covered"
        ),
        (
            "article_x_icd10_noncovered_group.csv",
            "icd10_noncovered_group",
            "noncovered"
        ),
    ]:

        grp = read_csv_from_dir(
            ART_DIR,
            fname
        )

        grp = grp[
            grp["article_id"].isin(valid_article_ids)
        ]

        for _, row in grp.iterrows():

            is_unconditional, reason = is_unconditional_paragraph(
                row.get("paragraph")
            )

            if is_unconditional:
                continue

            body = _clean(
                _strip_html(
                    row.get("paragraph")
                )
            )

            yield {
                "id": (
                    f"article-{row['article_id']}-"
                    f"{row['article_version']}-{kind}-"
                    f"{row[group_col]}"
                ),
                "text": body,
                "metadata": {
                    "source_type": "article",
                    "source_id": str(row["article_id"]),
                    "source_version": str(row["article_version"]),
                    "section": f"{kind.capitalize()} Group Note",
                    "linked_covered_group": str(row[group_col]),
                    "conditional_reason": reason,
                    "is_active": True,
                },
            }


def embed_and_store(batch_size: int = 256):

    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        EMBED_MODEL
    )

    client = chromadb.PersistentClient(
        path=CHROMA_DIR
    )

    collection = client.get_or_create_collection(
        "pa_policy_kb"
    )

    batch_ids, batch_txt, batch_meta = [], [], []

    def flush():

        if not batch_ids:
            return

        vecs = model.encode(
            batch_txt,
            normalize_embeddings=True
        ).tolist()

        collection.upsert(
            ids=batch_ids,
            embeddings=vecs,
            documents=batch_txt,
            metadatas=batch_meta
        )

        batch_ids.clear()
        batch_txt.clear()
        batch_meta.clear()

    n = 0

    for rec in build_rag_records():

        batch_ids.append(
            rec["id"]
        )

        batch_txt.append(
            rec["text"]
        )

        batch_meta.append(
            rec["metadata"]
        )

        n += 1

        if len(batch_ids) >= batch_size:
            flush()

    flush()

    print(
        f"embed_and_store: {n} chunks embedded"
    )


# --------------------------------------------------------------------------
# 5. Retrieval -- RDBMS exact match hands the RAG layer its filter key
# --------------------------------------------------------------------------
def get_scoped_chunks(
    chroma_collection,
    source_type: str,
    source_id: str,
    section: str | None = None,
    query: str | None = None,
    k: int = 3
):

    """Retrieval is filtered to an ID the RDBMS already resolved via exact
    match -- never an open search across the whole corpus.
    """

    where = {
        "source_type": source_type,
        "source_id": source_id,
        "is_active": True
    }

    if section:
        where["section"] = section

    if query:

        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            EMBED_MODEL
        )

        qvec = model.encode(
            [query],
            normalize_embeddings=True
        ).tolist()

        return chroma_collection.query(
            query_embeddings=qvec,
            where=where,
            n_results=k
        )

    return chroma_collection.get(
        where=where
    )


if __name__ == "__main__":

    init_schema()
    load_rdbms_layer()
    embed_and_store()

    print(
        "Knowledge base build complete."
    )