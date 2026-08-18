"""
Prior Authorization KB - STRICT 5 LEVEL VERIFICATION
=====================================================

READ-ONLY VALIDATION

LEVEL 1:
    Original CSV -> MySQL
    -----------------------------------------------
    Verifies:
        HCPCS source
        ICD-10 covered source
        Article ID + version intersection
        Source -> MySQL consistency

LEVEL 2:
    HCPCS + ICD-10 -> MySQL exact Article resolution
    -----------------------------------------------
    Verifies:
        HCPCS exact matches
        ICD-10 covered exact matches
        ICD-10 non-covered matches
        Exact Article ID + version intersection

LEVEL 3:
    MySQL Article -> LCD/NCD -> Chroma
    -----------------------------------------------
    Verifies:
        Article exists in Chroma
        Linked LCDs exist in Chroma
        Linked NCDs exist in Chroma
        Metadata correctness
        Document usability
        Chunk ID uniqueness
        Global Chroma integrity

LEVEL 4:
    Chroma semantic retrieval
    -----------------------------------------------
    Uses:
        BAAI/bge-small-en-v1.5

    Verifies:
        Semantic retrieval
        Correct source_type
        Correct source_id
        Correct source_version
        Active source
        Non-empty evidence

LEVEL 5:
    Coverage-state validation
    -----------------------------------------------
    Determines:

        COVERED
        NON-COVERED
        NOT FOUND

    based on the exact HCPCS + ICD-10 relationship.

IMPORTANT:
    This script DOES NOT modify MySQL or Chroma.

Expected structure:

D:\\cts\\KB\\
    verify_kb.py
    ncd_csv\\
    current_lcd_csv\\
    current_article_csv\\
    chroma_store\\

Environment variable:

    PA_KB_MYSQL_URL

Example CMD:

    set PA_KB_MYSQL_URL=mysql+mysqlconnector://root:password@localhost:3306/pa_kb

Optional:

    set PA_KB_CHROMA_DIR=D:\\cts\\KB\\chroma_store
"""


# ============================================================
# IMPORTS
# ============================================================

import os
from pathlib import Path
from collections import Counter

import pandas as pd
from sqlalchemy import create_engine, text


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MYSQL_URL = os.environ.get("PA_KB_MYSQL_URL")

if not MYSQL_URL:

    raise RuntimeError(
        "\nPA_KB_MYSQL_URL is not set.\n\n"
        "Example in CMD:\n"
        "set PA_KB_MYSQL_URL=mysql+mysqlconnector://root:password@localhost:3306/pa_kb\n"
    )


CHROMA_DIR = os.environ.get(
    "PA_KB_CHROMA_DIR",
    str(BASE_DIR / "chroma_store")
)


COLLECTION_NAME = "pa_policy_kb"


# ------------------------------------------------------------
# IMPORTANT:
# This MUST be the same embedding model used when building
# the Chroma collection.
# ------------------------------------------------------------

EMBED_MODEL = "BAAI/bge-small-en-v1.5"


# ------------------------------------------------------------
# Document quality threshold
# ------------------------------------------------------------

MIN_DOCUMENT_LENGTH = 50


# ------------------------------------------------------------
# Source directories
# ------------------------------------------------------------

NCD_DIR = BASE_DIR / "ncd_csv"

LCD_DIR = BASE_DIR / "current_lcd_csv"

ARTICLE_DIR = BASE_DIR / "current_article_csv"


# ============================================================
# GLOBAL RESULT STATE
# ============================================================

RESULTS = {

    "level1": False,

    "level2": False,

    "level3_selected": False,

    "level3_global": True,

    "level4": False,

    "level5": False,

    "global_short_documents": 0,

    "global_duplicate_ids": 0,

    "global_invalid_metadata": 0,

}


# ============================================================
# PRINT HELPERS
# ============================================================

def line():

    print("-" * 100)


def title(value):

    print()
    print("=" * 100)
    print(value)
    print("=" * 100)


def section(value):

    print()
    line()
    print(value)
    line()


def success(message):

    print(f"[PASS] {message}")


def failure(message):

    print(f"[FAIL] {message}")


def warning(message):

    print(f"[WARN] {message}")


def info(message):

    print(f"[INFO] {message}")


# ============================================================
# DATABASE
# ============================================================

def get_engine():

    return create_engine(
        MYSQL_URL,
        pool_pre_ping=True
    )


# ============================================================
# CSV HELPER
# ============================================================

def read_csv(directory: Path, filename: str):

    path = directory / filename

    if not path.exists():

        raise FileNotFoundError(
            f"\nCSV not found:\n{path}"
        )

    return pd.read_csv(
        path,
        dtype=str,
        low_memory=False
    )


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def normalize_string(value):

    if value is None:

        return ""

    return str(value).strip()


def normalize_upper(value):

    return normalize_string(value).upper()


def make_pair(article_id, article_version):

    return (
        normalize_string(article_id),
        normalize_string(article_version)
    )


# ============================================================
# LEVEL 1
# CSV -> MYSQL
# ============================================================

def level_1_csv_to_mysql(hcpc_code, icd10_code):

    title(
        "LEVEL 1 - ORIGINAL CSV -> MYSQL"
    )

    engine = get_engine()

    # ========================================================
    # 1A ARTICLE SOURCE
    # ========================================================

    section(
        "[1A] Checking Article source CSV"
    )

    article = read_csv(
        ARTICLE_DIR,
        "article.csv"
    )

    required_columns = [
        "article_id",
        "article_version",
        "article_type",
        "status"
    ]

    missing = [
        c for c in required_columns
        if c not in article.columns
    ]

    if missing:

        raise RuntimeError(
            f"Article CSV missing columns: {missing}"
        )

    article["article_id"] = (
        article["article_id"]
        .astype(str)
        .str.strip()
    )

    article["article_version"] = (
        article["article_version"]
        .astype(str)
        .str.strip()
    )

    article["article_type"] = (
        article["article_type"]
        .astype(str)
        .str.strip()
    )

    article["status"] = (
        article["status"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    active_article = article[
        (article["article_type"] == "6") &
        (article["status"] == "A")
    ].copy()

    active_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for _, row in active_article.iterrows()
    }

    print(
        f"Article CSV total rows        : {len(article)}"
    )

    print(
        f"Active Article rows            : {len(active_article)}"
    )

    print(
        f"Active ID/version pairs        : {len(active_pairs)}"
    )

    success(
        "Active Article source loaded."
    )

    # ========================================================
    # 1B HCPCS
    # ========================================================

    section(
        "[1B] Checking Article HCPCS source CSV"
    )

    article_hcpc = read_csv(
        ARTICLE_DIR,
        "article_x_hcpc_code.csv"
    )

    article_hcpc["article_id"] = (
        article_hcpc["article_id"]
        .astype(str)
        .str.strip()
    )

    article_hcpc["article_version"] = (
        article_hcpc["article_version"]
        .astype(str)
        .str.strip()
    )

    article_hcpc["hcpc_code_id"] = (
        article_hcpc["hcpc_code_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    hcpc_code = normalize_upper(hcpc_code)

    source_hcpc = article_hcpc[
        (article_hcpc["hcpc_code_id"] == hcpc_code) &
        (
            article_hcpc.apply(
                lambda row:
                    make_pair(
                        row["article_id"],
                        row["article_version"]
                    ) in active_pairs,
                axis=1
            )
        )
    ].copy()

    print(
        f"HCPCS source rows             : {len(source_hcpc)}"
    )

    if source_hcpc.empty:

        failure(
            f"HCPCS {hcpc_code} was NOT found "
            f"in active Article source."
        )

    else:

        success(
            f"HCPCS {hcpc_code} exists in active Article source."
        )

        for _, row in source_hcpc.iterrows():

            print(
                f"  Article {row['article_id']} "
                f"v{row['article_version']}"
            )

    # ========================================================
    # 1C ICD-10 COVERED
    # ========================================================

    section(
        "[1C] Checking Article ICD-10 covered source CSV"
    )

    article_icd = read_csv(
        ARTICLE_DIR,
        "article_x_icd10_covered.csv"
    )

    article_icd["article_id"] = (
        article_icd["article_id"]
        .astype(str)
        .str.strip()
    )

    article_icd["article_version"] = (
        article_icd["article_version"]
        .astype(str)
        .str.strip()
    )

    article_icd["icd10_code_id"] = (
        article_icd["icd10_code_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    icd10_code = normalize_upper(icd10_code)

    source_icd = article_icd[
        (article_icd["icd10_code_id"] == icd10_code) &
        (
            article_icd.apply(
                lambda row:
                    make_pair(
                        row["article_id"],
                        row["article_version"]
                    ) in active_pairs,
                axis=1
            )
        )
    ].copy()

    print(
        f"ICD-10 source rows            : {len(source_icd)}"
    )

    if source_icd.empty:

        failure(
            f"ICD-10 {icd10_code} was NOT found "
            f"in active covered Article source."
        )

    else:

        success(
            f"ICD-10 {icd10_code} exists "
            f"in active covered Article source."
        )

        for _, row in source_icd.iterrows():

            print(
                f"  Article {row['article_id']} "
                f"v{row['article_version']}"
            )

    # ========================================================
    # 1D EXACT SOURCE INTERSECTION
    # ========================================================

    section(
        "[1D] Exact source intersection"
    )

    source_hcpc_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for _, row in source_hcpc.iterrows()
    }

    source_icd_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for _, row in source_icd.iterrows()
    }

    source_intersection = (
        source_hcpc_pairs &
        source_icd_pairs
    )

    print(
        f"Source Article ID/version pairs "
        f"matching BOTH: {len(source_intersection)}"
    )

    for pair in sorted(source_intersection):

        print(
            f"  MATCH -> Article {pair[0]} v{pair[1]}"
        )

    if source_intersection:

        success(
            "Source CSV contains an exact "
            "HCPCS + ICD-10 Article/version match."
        )

    else:

        failure(
            "No source Article/version contains "
            "both requested codes."
        )

    # ========================================================
    # 1E MYSQL COUNTS
    # ========================================================

    section(
        "[1E] MySQL table counts"
    )

    tables = [

        "ncd_policy",

        "lcd_policy",

        "article_policy",

        "lcd_article_bridge",

        "lcd_ncd_bridge",

        "article_ncd_bridge",

        "lcd_jurisdiction",

        "article_hcpc",

        "article_icd10_covered",

        "article_icd10_noncovered",

        "service_category_ref",

    ]

    with engine.connect() as conn:

        for table in tables:

            try:

                count = conn.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM `{table}`
                        """
                    )
                ).scalar_one()

                print(
                    f"{table:35s} {count:>10}"
                )

            except Exception as exc:

                print(
                    f"{table:35s} ERROR: {exc}"
                )

    # ========================================================
    # 1F SOURCE -> MYSQL
    # ========================================================

    section(
        "[1F] Comparing source Article/version pairs with MySQL"
    )

    with engine.connect() as conn:

        mysql_hcpc_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    ah.article_id,
                    ah.article_version
                FROM article_hcpc ah
                JOIN article_policy ap
                  ON ap.article_id = ah.article_id
                 AND ap.article_version = ah.article_version
                WHERE ah.hcpc_code_id = :hcpc
                  AND ap.status = 'A'
                """
            ),
            {
                "hcpc": hcpc_code
            }
        ).mappings().all()

        mysql_icd_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    ac.article_id,
                    ac.article_version
                FROM article_icd10_covered ac
                JOIN article_policy ap
                  ON ap.article_id = ac.article_id
                 AND ap.article_version = ac.article_version
                WHERE ac.icd10_code_id = :icd
                  AND ap.status = 'A'
                """
            ),
            {
                "icd": icd10_code
            }
        ).mappings().all()

    mysql_hcpc_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for row in mysql_hcpc_rows
    }

    mysql_icd_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for row in mysql_icd_rows
    }

    mysql_intersection = (
        mysql_hcpc_pairs &
        mysql_icd_pairs
    )

    print(
        f"MySQL HCPCS pairs : {len(mysql_hcpc_pairs)}"
    )

    print(
        f"MySQL ICD pairs   : {len(mysql_icd_pairs)}"
    )

    print(
        f"MySQL BOTH pairs  : {len(mysql_intersection)}"
    )

    missing_in_mysql = (
        source_intersection -
        mysql_intersection
    )

    extra_in_mysql = (
        mysql_intersection -
        source_intersection
    )

    if not missing_in_mysql:

        success(
            "Every source HCPCS+ICD Article/version pair "
            "exists in MySQL."
        )

    else:

        failure(
            "Some source Article/version pairs are missing "
            "from MySQL."
        )

        for pair in sorted(missing_in_mysql):

            print(
                f"  Missing -> Article {pair[0]} v{pair[1]}"
            )

    if not extra_in_mysql:

        success(
            "MySQL has no extra selected Article/version "
            "pair outside the source intersection."
        )

    else:

        failure(
            "MySQL contains extra selected "
            "Article/version pairs."
        )

        for pair in sorted(extra_in_mysql):

            print(
                f"  Extra -> Article {pair[0]} v{pair[1]}"
            )

    level1_pass = (
        bool(source_intersection)
        and not missing_in_mysql
        and not extra_in_mysql
    )

    RESULTS["level1"] = level1_pass

    if level1_pass:

        success(
            "LEVEL 1 strict source -> MySQL validation PASSED."
        )

    else:

        failure(
            "LEVEL 1 strict source -> MySQL validation FAILED."
        )

    return source_intersection


# ============================================================
# LEVEL 2
# MYSQL EXACT MATCH
# ============================================================

def level_2_exact_match(hcpc_code, icd10_code):

    title(
        "LEVEL 2 - MYSQL EXACT HCPCS + ICD-10 MATCH"
    )

    engine = get_engine()

    with engine.connect() as conn:

        # ====================================================
        # HCPCS
        # ====================================================

        hcpc_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    ap.article_id,
                    ap.article_version,
                    ap.title,
                    ap.status,
                    ah.hcpc_code_id
                FROM article_policy ap
                JOIN article_hcpc ah
                  ON ah.article_id = ap.article_id
                 AND ah.article_version = ap.article_version
                WHERE ah.hcpc_code_id = :hcpc
                  AND ap.status = 'A'
                ORDER BY ap.article_id
                """
            ),
            {
                "hcpc": hcpc_code
            }
        ).mappings().all()

        # ====================================================
        # ICD COVERED
        # ====================================================

        icd_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    ap.article_id,
                    ap.article_version,
                    ap.title,
                    ap.status,
                    ac.icd10_code_id
                FROM article_policy ap
                JOIN article_icd10_covered ac
                  ON ac.article_id = ap.article_id
                 AND ac.article_version = ap.article_version
                WHERE ac.icd10_code_id = :icd
                  AND ap.status = 'A'
                ORDER BY ap.article_id
                """
            ),
            {
                "icd": icd10_code
            }
        ).mappings().all()

        # ====================================================
        # ICD NON-COVERED
        # ====================================================

        noncovered_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    ap.article_id,
                    ap.article_version,
                    ap.title,
                    ap.status,
                    an.icd10_code_id
                FROM article_policy ap
                JOIN article_icd10_noncovered an
                  ON an.article_id = ap.article_id
                 AND an.article_version = ap.article_version
                WHERE an.icd10_code_id = :icd
                  AND ap.status = 'A'
                ORDER BY ap.article_id
                """
            ),
            {
                "icd": icd10_code
            }
        ).mappings().all()

    # ========================================================
    # DISPLAY
    # ========================================================

    section(
        "HCPCS exact matches"
    )

    if not hcpc_rows:

        print("NONE")

    else:

        for row in hcpc_rows:

            print(
                f"  Article {row['article_id']} "
                f"v{row['article_version']} "
                f"| {row['title']}"
            )

    section(
        "ICD-10 COVERED exact matches"
    )

    if not icd_rows:

        print("NONE")

    else:

        for row in icd_rows:

            print(
                f"  Article {row['article_id']} "
                f"v{row['article_version']} "
                f"| {row['title']}"
            )

    section(
        "ICD-10 NON-COVERED exact matches"
    )

    if not noncovered_rows:

        print("NONE")

    else:

        for row in noncovered_rows:

            print(
                f"  Article {row['article_id']} "
                f"v{row['article_version']} "
                f"| {row['title']}"
            )

    # ========================================================
    # INTERSECTION
    # ========================================================

    hcpc_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for row in hcpc_rows
    }

    covered_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for row in icd_rows
    }

    noncovered_pairs = {
        make_pair(
            row["article_id"],
            row["article_version"]
        )
        for row in noncovered_rows
    }

    covered_intersection = (
        hcpc_pairs &
        covered_pairs
    )

    noncovered_intersection = (
        hcpc_pairs &
        noncovered_pairs
    )

    print()
    print(
        "Combined exact match:"
    )

    print(
        f"  HCPCS pairs       : {len(hcpc_pairs)}"
    )

    print(
        f"  Covered ICD pairs : {len(covered_pairs)}"
    )

    print(
        f"  Noncovered ICD pairs : {len(noncovered_pairs)}"
    )

    print(
        f"  BOTH covered      : {len(covered_intersection)}"
    )

    print(
        f"  BOTH non-covered  : {len(noncovered_intersection)}"
    )

    # ========================================================
    # IMPORTANT:
    # Covered takes precedence only if the same Article/version
    # relationship exists in covered.
    #
    # If the exact Article/version is in non-covered only,
    # classify as NON-COVERED.
    # ========================================================

    if covered_intersection:

        coverage_state = "COVERED"

        matched_pairs = covered_intersection

    elif noncovered_intersection:

        coverage_state = "NON-COVERED"

        matched_pairs = noncovered_intersection

    else:

        coverage_state = "NOT FOUND"

        matched_pairs = set()

    print()
    print(
        f"Coverage state: {coverage_state}"
    )

    # ========================================================
    # POLICY INFORMATION
    # ========================================================

    policies = []

    if matched_pairs:

        with engine.connect() as conn:

            for article_id, article_version in sorted(
                matched_pairs
            ):

                row = conn.execute(
                    text(
                        """
                        SELECT
                            article_id,
                            article_version,
                            title,
                            article_type,
                            status
                        FROM article_policy
                        WHERE article_id = :article_id
                          AND article_version = :article_version
                          AND status = 'A'
                        """
                    ),
                    {
                        "article_id": int(article_id),
                        "article_version": int(article_version)
                    }
                ).mappings().first()

                if row:

                    policy = dict(row)

                    policy["coverage_state"] = coverage_state

                    policies.append(policy)

                    print()
                    print(
                        f"ARTICLE ID      : "
                        f"{policy['article_id']}"
                    )

                    print(
                        f"VERSION         : "
                        f"{policy['article_version']}"
                    )

                    print(
                        f"TITLE           : "
                        f"{policy['title']}"
                    )

                    print(
                        f"ARTICLE TYPE    : "
                        f"{policy['article_type']}"
                    )

                    print(
                        f"STATUS          : "
                        f"{policy['status']}"
                    )

                    print(
                        f"COVERAGE STATE  : "
                        f"{policy['coverage_state']}"
                    )

    # ========================================================
    # STRICT LEVEL 2
    # ========================================================

    level2_pass = (
        len(covered_intersection) > 0
        or len(noncovered_intersection) > 0
        or (
            not hcpc_pairs
            and not covered_pairs
            and not noncovered_pairs
        )
    )

    RESULTS["level2"] = level2_pass

    if covered_intersection:

        success(
            "Exact HCPCS + COVERED ICD-10 Article/version "
            "resolution succeeded."
        )

    elif noncovered_intersection:

        warning(
            "Exact HCPCS + ICD-10 relationship exists, "
            "but it is NON-COVERED."
        )

    else:

        info(
            "No exact HCPCS + ICD-10 Article/version "
            "relationship found."
        )

    return policies, coverage_state


# ============================================================
# LINKED LCD / NCD
# ============================================================

def get_linked_policies(
    article_id,
    article_version
):

    engine = get_engine()

    result = {

        "lcds": [],

        "ncds": []

    }

    with engine.connect() as conn:

        # ====================================================
        # ARTICLE -> LCD
        # ====================================================

        lcd_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    lab.lcd_id,
                    lab.lcd_version,
                    lp.title,
                    lp.status
                FROM lcd_article_bridge lab
                JOIN lcd_policy lp
                  ON lp.lcd_id = lab.lcd_id
                 AND lp.lcd_version = lab.lcd_version
                WHERE lab.article_id = :article_id
                  AND lab.article_version = :article_version
                """
            ),
            {
                "article_id": article_id,
                "article_version": article_version
            }
        ).mappings().all()

        # ====================================================
        # ARTICLE -> NCD
        # ====================================================

        ncd_rows = conn.execute(
            text(
                """
                SELECT DISTINCT
                    anb.ncd_id,
                    anb.ncd_version,
                    np.mnl_sect_title,
                    np.effective_date,
                    np.termination_date
                FROM article_ncd_bridge anb
                JOIN ncd_policy np
                  ON np.ncd_id = anb.ncd_id
                 AND np.ncd_version = anb.ncd_version
                WHERE anb.article_id = :article_id
                  AND anb.article_version = :article_version
                """
            ),
            {
                "article_id": article_id,
                "article_version": article_version
            }
        ).mappings().all()

    result["lcds"] = [
        dict(x)
        for x in lcd_rows
    ]

    result["ncds"] = [
        dict(x)
        for x in ncd_rows
    ]

    return result


# ============================================================
# CHROMA HELPERS
# ============================================================

def get_chroma_collection():

    import chromadb

    client = chromadb.PersistentClient(
        path=CHROMA_DIR
    )

    collections = client.list_collections()

    names = [
        c.name
        for c in collections
    ]

    print(
        "Chroma collections:"
    )

    for name in names:

        print(
            f"  {name}"
        )

    if COLLECTION_NAME not in names:

        raise RuntimeError(
            f"Chroma collection '{COLLECTION_NAME}' "
            f"does not exist."
        )

    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    return client, collection


# ============================================================
# CHROMA SOURCE CHECK
# ============================================================

def chroma_source_check(
    collection,
    source_type,
    source_id,
    source_version=None
):

    conditions = [

        {
            "source_type": source_type
        },

        {
            "source_id": str(source_id)
        },

        {
            "is_active": True
        }

    ]

    if source_version is not None:

        conditions.append(
            {
                "source_version": str(
                    source_version
                )
            }
        )

    result = collection.get(

        where={
            "$and": conditions
        },

        limit=100000
    )

    return result


# ============================================================
# LEVEL 3
# MYSQL -> CHROMA
# ============================================================

def level_3_mysql_to_chroma(
    policies
):

    title(
        "LEVEL 3 - MYSQL POLICY ID -> CHROMA"
    )

    if not policies:

        failure(
            "There are no exact-match policies "
            "to validate in Chroma."
        )

        return [], None

    try:

        _, collection = get_chroma_collection()

    except Exception as exc:

        failure(
            f"Unable to open Chroma: {exc}"
        )

        return [], None

    print()
    print(
        f"Chroma collection count : "
        f"{collection.count()}"
    )

    if collection.count() == 0:

        failure(
            "Chroma collection exists but is empty."
        )

        return [], collection

    valid_sources = []

    selected_policy_ok = True

    # ========================================================
    # CHECK SELECTED ARTICLES
    # ========================================================

    for policy in policies:

        article_id = str(
            policy["article_id"]
        )

        article_version = str(
            policy["article_version"]
        )

        section(
            f"Checking Article {article_id} "
            f"v{article_version}"
        )

        result = chroma_source_check(

            collection,

            "article",

            article_id,

            article_version

        )

        ids = result.get(
            "ids",
            []
        )

        metadatas = result.get(
            "metadatas",
            []
        )

        documents = result.get(
            "documents",
            []
        )

        print(
            f"Article Chroma chunks : "
            f"{len(ids)}"
        )

        if not ids:

            failure(
                f"Article {article_id} v{article_version} "
                f"does NOT exist in Chroma."
            )

            selected_policy_ok = False

            continue

        success(
            f"Article {article_id} v{article_version} "
            f"exists in Chroma."
        )

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        metadata_ok = True

        for index, metadata in enumerate(
            metadatas
        ):

            print()

            print(
                f"Chunk {index + 1}"
            )

            print(
                f"  ID            : "
                f"{ids[index]}"
            )

            print(
                f"  source_type   : "
                f"{metadata.get('source_type')}"
            )

            print(
                f"  source_id     : "
                f"{metadata.get('source_id')}"
            )

            print(
                f"  source_version: "
                f"{metadata.get('source_version')}"
            )

            print(
                f"  section       : "
                f"{metadata.get('section')}"
            )

            print(
                f"  is_active     : "
                f"{metadata.get('is_active')}"
            )

            document = (
                documents[index]
                if index < len(documents)
                else ""
            )

            print(
                f"  document_len  : "
                f"{len(document)}"
            )

            if (
                str(metadata.get("source_type"))
                != "article"
            ):

                metadata_ok = False

            if (
                str(metadata.get("source_id"))
                != article_id
            ):

                metadata_ok = False

            if (
                str(metadata.get("source_version"))
                != article_version
            ):

                metadata_ok = False

            if (
                metadata.get("is_active")
                is not True
            ):

                metadata_ok = False

            if len(document.strip()) < MIN_DOCUMENT_LENGTH:

                metadata_ok = False

        if metadata_ok:

            success(
                f"All Article {article_id} chunks "
                f"have correct metadata and usable text."
            )

        else:

            failure(
                f"Article {article_id} has metadata/text problems."
            )

            selected_policy_ok = False

        # ----------------------------------------------------
        # Unique chunk IDs
        # ----------------------------------------------------

        if len(ids) == len(set(ids)):

            success(
                f"Article {article_id} chunk IDs are unique."
            )

        else:

            failure(
                f"Duplicate chunk IDs found for Article "
                f"{article_id}."
            )

            selected_policy_ok = False

        valid_sources.append(

            {
                "source_type": "article",

                "source_id": article_id,

                "source_version": article_version

            }

        )

        # ====================================================
        # LINKED LCD / NCD
        # ====================================================

        links = get_linked_policies(

            int(article_id),

            int(article_version)

        )

        # ----------------------------------------------------
        # LCD
        # ----------------------------------------------------

        print()
        print(
            "Linked LCDs:"
        )

        if not links["lcds"]:

            print(
                "  NONE"
            )

        else:

            for lcd in links["lcds"]:

                lcd_id = str(
                    lcd["lcd_id"]
                )

                lcd_version = str(
                    lcd["lcd_version"]
                )

                print(
                    f"  LCD {lcd_id} "
                    f"v{lcd_version} "
                    f"| {lcd['title']}"
                )

                lcd_result = chroma_source_check(

                    collection,

                    "lcd",

                    lcd_id,

                    lcd_version

                )

                lcd_ids = lcd_result.get(
                    "ids",
                    []
                )

                if lcd_ids:

                    success(
                        f"LCD {lcd_id} v{lcd_version} "
                        f"exists in Chroma."
                    )

                    valid_sources.append(

                        {
                            "source_type": "lcd",

                            "source_id": lcd_id,

                            "source_version": lcd_version

                        }

                    )

                else:

                    failure(
                        f"LCD {lcd_id} v{lcd_version} "
                        f"is in MySQL but not in Chroma."
                    )

                    selected_policy_ok = False

        # ----------------------------------------------------
        # NCD
        # ----------------------------------------------------

        print()
        print(
            "Linked NCDs:"
        )

        if not links["ncds"]:

            print(
                "  NONE"
            )

        else:

            for ncd in links["ncds"]:

                ncd_id = str(
                    ncd["ncd_id"]
                )

                ncd_version = str(
                    ncd["ncd_version"]
                )

                print(
                    f"  NCD {ncd_id} "
                    f"v{ncd_version} "
                    f"| {ncd['mnl_sect_title']}"
                )

                ncd_result = chroma_source_check(

                    collection,

                    "ncd",

                    ncd_id,

                    ncd_version

                )

                ncd_ids = ncd_result.get(
                    "ids",
                    []
                )

                if ncd_ids:

                    success(
                        f"NCD {ncd_id} v{ncd_version} "
                        f"exists in Chroma."
                    )

                    valid_sources.append(

                        {
                            "source_type": "ncd",

                            "source_id": ncd_id,

                            "source_version": ncd_version

                        }

                    )

                else:

                    failure(
                        f"NCD {ncd_id} v{ncd_version} "
                        f"is in MySQL but not in Chroma."
                    )

                    selected_policy_ok = False

    # ========================================================
    # GLOBAL CHROMA INTEGRITY
    # ========================================================

    section(
        "[3G] GLOBAL CHROMA COLLECTION INTEGRITY"
    )

    try:

        all_records = collection.get(
            limit=1000000,
            include=[
                "metadatas",
                "documents"
            ]
        )

        all_ids = all_records.get(
            "ids",
            []
        )

        all_metadatas = all_records.get(
            "metadatas",
            []
        )

        all_documents = all_records.get(
            "documents",
            []
        )

        print(
            f"Chroma records inspected : "
            f"{len(all_ids)}"
        )

        # ----------------------------------------------------
        # Duplicate IDs
        # ----------------------------------------------------

        counts = Counter(all_ids)

        duplicate_ids = [
            key
            for key, count in counts.items()
            if count > 1
        ]

        RESULTS[
            "global_duplicate_ids"
        ] = len(duplicate_ids)

        print(
            f"Duplicate chunk IDs       : "
            f"{len(duplicate_ids)}"
        )

        if duplicate_ids:

            failure(
                "Duplicate Chroma chunk IDs found."
            )

        else:

            success(
                "No duplicate Chroma chunk IDs found."
            )

        # ----------------------------------------------------
        # Metadata integrity
        # ----------------------------------------------------

        invalid_metadata = []

        required_metadata = [

            "source_type",

            "source_id",

            "source_version",

            "section",

            "is_active"

        ]

        for index, metadata in enumerate(
            all_metadatas
        ):

            bad = False

            for field in required_metadata:

                if field not in metadata:

                    bad = True

            if bad:

                invalid_metadata.append(
                    index
                )

        RESULTS[
            "global_invalid_metadata"
        ] = len(invalid_metadata)

        print(
            f"Invalid metadata records   : "
            f"{len(invalid_metadata)}"
        )

        if invalid_metadata:

            failure(
                "Some Chroma records have invalid metadata."
            )

        else:

            success(
                "All Chroma records contain required metadata fields."
            )

        # ----------------------------------------------------
        # Empty documents
        # ----------------------------------------------------

        short_documents = []

        for index, document in enumerate(
            all_documents
        ):

            if (
                document is None
                or len(str(document).strip())
                < MIN_DOCUMENT_LENGTH
            ):

                short_documents.append(
                    index
                )

        RESULTS[
            "global_short_documents"
        ] = len(short_documents)

        print(
            f"Empty/short documents      : "
            f"{len(short_documents)}"
        )

        if short_documents:

            warning(
                f"{len(short_documents)} Chroma records "
                f"have empty/too-short documents."
            )

            print(
                "\nFirst 20 affected records:"
            )

            for index in short_documents[:20]:

                metadata = (
                    all_metadatas[index]
                    if index < len(all_metadatas)
                    else {}
                )

                print(
                    f"  source_type={metadata.get('source_type')} "
                    f"| source_id={metadata.get('source_id')} "
                    f"| version={metadata.get('source_version')} "
                    f"| section={metadata.get('section')}"
                )

            print()
            warning(
                "These are GLOBAL KB warnings. "
                "They do not automatically invalidate the "
                "selected Article/NCD policy."
            )

        else:

            success(
                "No empty/too-short documents found."
            )

        # ----------------------------------------------------
        # GLOBAL STATUS
        # ----------------------------------------------------

        if duplicate_ids or invalid_metadata:

            RESULTS["level3_global"] = False

            failure(
                "Global Chroma integrity has structural problems."
            )

        elif short_documents:

            RESULTS["level3_global"] = True

            warning(
                "Global Chroma has document-quality warnings, "
                "but no duplicate IDs or invalid metadata."
            )

        else:

            RESULTS["level3_global"] = True

            success(
                "Global Chroma integrity PASSED."
            )

    except Exception as exc:

        RESULTS["level3_global"] = False

        failure(
            f"Global Chroma inspection failed: {exc}"
        )

    RESULTS[
        "level3_selected"
    ] = selected_policy_ok

    # --------------------------------------------------------
    # FINAL LEVEL 3
    # --------------------------------------------------------

    print()

    if selected_policy_ok:

        success(
            "SELECTED POLICY CHROMA VALIDATION PASSED."
        )

    else:

        failure(
            "SELECTED POLICY CHROMA VALIDATION FAILED."
        )

    print()

    print(
        "Selected policy status : "
        f"{'PASS' if selected_policy_ok else 'FAIL'}"
    )

    print(
        "Global KB status       : "
        f"{'PASS' if RESULTS['level3_global'] else 'FAIL'}"
    )

    if (
        RESULTS["level3_global"]
        and RESULTS["global_short_documents"] > 0
    ):

        warning(
            "Global KB contains short documents, "
            "but selected policy sources are valid."
        )

    return valid_sources, collection


# ============================================================
# LEVEL 4
# SEMANTIC RETRIEVAL
# ============================================================

def level_4_semantic_retrieval(
    valid_sources,
    collection
):

    title(
        "LEVEL 4 - CHROMA SEMANTIC RETRIEVAL"
    )

    if not valid_sources:

        failure(
            "No verified Chroma sources available."
        )

        return

    if collection is None:

        failure(
            "No Chroma collection available."
        )

        return

    try:

        from sentence_transformers import SentenceTransformer

    except ImportError:

        failure(
            "sentence-transformers is not installed."
        )

        return

    # ========================================================
    # QUERY
    # ========================================================

    print()

    query = input(
        "Enter semantic policy question "
        "(press ENTER for default):\n> "
    ).strip()

    if not query:

        query = (
            "What are the coverage requirements, "
            "medical necessity requirements, and "
            "documentation requirements for this service?"
        )

        print()
        print(
            f"Using default query:\n{query}"
        )

    # ========================================================
    # LOAD EMBEDDING MODEL
    # ========================================================

    print()

    print(
        f"Embedding model: {EMBED_MODEL}"
    )

    print(
        "Loading embedding model..."
    )

    try:

        model = SentenceTransformer(
            EMBED_MODEL
        )

        success(
            "Embedding model loaded."
        )

    except Exception as exc:

        failure(
            f"Embedding model failed to load: {exc}"
        )

        return

    # ========================================================
    # CREATE QUERY VECTOR
    # ========================================================

    query_vector = model.encode(
        [query],
        normalize_embeddings=True
    ).tolist()

    # ========================================================
    # SEARCH EACH VERIFIED SOURCE
    # ========================================================

    total_results = 0

    retrieval_ok = True

    verified_source_keys = {

        (
            source["source_type"],

            str(source["source_id"]),

            str(source["source_version"])

        )

        for source in valid_sources

    }

    for source in valid_sources:

        source_type = source[
            "source_type"
        ]

        source_id = str(
            source["source_id"]
        )

        source_version = str(
            source["source_version"]
        )

        section(
            f"SEMANTIC SEARCH - "
            f"{source_type} {source_id} v{source_version}"
        )

        try:

            result = collection.query(

                query_embeddings=query_vector,

                where={
                    "$and": [

                        {
                            "source_type":
                            source_type
                        },

                        {
                            "source_id":
                            source_id
                        },

                        {
                            "source_version":
                            source_version
                        },

                        {
                            "is_active":
                            True
                        }

                    ]
                },

                n_results=3

            )

        except Exception as exc:

            failure(
                f"Semantic search failed: {exc}"
            )

            retrieval_ok = False

            continue

        ids = result.get(
            "ids",
            [[]]
        )[0]

        documents = result.get(
            "documents",
            [[]]
        )[0]

        metadatas = result.get(
            "metadatas",
            [[]]
        )[0]

        distances = result.get(
            "distances",
            [[]]
        )[0]

        if not ids:

            failure(
                f"No semantic results for "
                f"{source_type} {source_id} "
                f"v{source_version}."
            )

            retrieval_ok = False

            continue

        total_results += len(ids)

        success(
            f"Retrieved {len(ids)} chunk(s) "
            f"from the correct policy source."
        )

        # ====================================================
        # VALIDATE RESULTS
        # ====================================================

        for i in range(
            len(ids)
        ):

            metadata = (
                metadatas[i]
                if i < len(metadatas)
                else {}
            )

            document = (
                documents[i]
                if i < len(documents)
                else ""
            )

            distance = (
                distances[i]
                if i < len(distances)
                else None
            )

            print()

            print(
                f"RESULT #{i + 1}"
            )

            print(
                f"Chunk ID   : {ids[i]}"
            )

            print(
                f"Distance   : {distance}"
            )

            print(
                f"Source     : "
                f"{metadata.get('source_type')}"
            )

            print(
                f"Source ID  : "
                f"{metadata.get('source_id')}"
            )

            print(
                f"Version    : "
                f"{metadata.get('source_version')}"
            )

            print(
                f"Section    : "
                f"{metadata.get('section')}"
            )

            print(
                f"Active     : "
                f"{metadata.get('is_active')}"
            )

            # ------------------------------------------------
            # SOURCE CHECK
            # ------------------------------------------------

            actual_key = (

                str(
                    metadata.get(
                        "source_type"
                    )
                ),

                str(
                    metadata.get(
                        "source_id"
                    )
                ),

                str(
                    metadata.get(
                        "source_version"
                    )
                )

            )

            if actual_key not in verified_source_keys:

                failure(
                    "Semantic result came from "
                    "an unverified source."
                )

                retrieval_ok = False

            # ------------------------------------------------
            # ACTIVE
            # ------------------------------------------------

            if metadata.get(
                "is_active"
            ) is not True:

                failure(
                    "Semantic result is not active."
                )

                retrieval_ok = False

            # ------------------------------------------------
            # DOCUMENT
            # ------------------------------------------------

            if (
                not document
                or len(document.strip())
                < MIN_DOCUMENT_LENGTH
            ):

                failure(
                    "Semantic result contains "
                    "empty/too-short evidence."
                )

                retrieval_ok = False

            # ------------------------------------------------
            # DISPLAY DOCUMENT
            # ------------------------------------------------

            print()

            print(
                "Retrieved policy evidence:"
            )

            print(
                "-" * 100
            )

            print(
                document[:3000]
            )

            if len(document) > 3000:

                print(
                    "\n...[text truncated]..."
                )

            print(
                "-" * 100
            )

    print()

    print(
        f"Total semantic evidence chunks retrieved: "
        f"{total_results}"
    )

    RESULTS[
        "level4"
    ] = (
        retrieval_ok
        and total_results > 0
    )

    if RESULTS["level4"]:

        success(
            "LEVEL 4 semantic retrieval PASSED."
        )

    else:

        failure(
            "LEVEL 4 semantic retrieval FAILED."
        )


# ============================================================
# LEVEL 5
# COVERAGE STATE
# ============================================================

def level_5_coverage_state(
    hcpc_code,
    icd10_code,
    coverage_state,
    policies
):

    title(
        "LEVEL 5 - COVERAGE STATE VALIDATION"
    )

    print(
        f"HCPCS : {hcpc_code}"
    )

    print(
        f"ICD10 : {icd10_code}"
    )

    print()

    print(
        "Determined coverage state:"
    )

    print(
        f"    {coverage_state}"
    )

    # ========================================================
    # COVERED
    # ========================================================

    if coverage_state == "COVERED":

        if policies:

            success(
                "COVERED state has an exact "
                "HCPCS + ICD-10 Article/version."
            )

            for policy in policies:

                print()

                print(
                    f"  Article {policy['article_id']} "
                    f"v{policy['article_version']}"
                )

                print(
                    f"  {policy['title']}"
                )

            RESULTS[
                "level5"
            ] = True

            return

    # ========================================================
    # NON-COVERED
    # ========================================================

    if coverage_state == "NON-COVERED":

        warning(
            "The exact HCPCS + ICD-10 relationship "
            "was found in the NON-COVERED table."
        )

        RESULTS[
            "level5"
        ] = True

        return

    # ========================================================
    # NOT FOUND
    # ========================================================

    if coverage_state == "NOT FOUND":

        warning(
            "No exact HCPCS + ICD-10 relationship "
            "was found."
        )

        RESULTS[
            "level5"
        ] = True

        return

    RESULTS[
        "level5"
    ] = False

    failure(
        "Unknown coverage state."
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

def final_summary():

    title(
        "FINAL STRICT KB VALIDATION"
    )

    print(
        f"LEVEL 1 - CSV -> MySQL       : "
        f"{'PASS' if RESULTS['level1'] else 'FAIL'}"
    )

    print(
        f"LEVEL 2 - Exact resolution    : "
        f"{'PASS' if RESULTS['level2'] else 'FAIL'}"
    )

    print(
        f"LEVEL 3 - Selected policies   : "
        f"{'PASS' if RESULTS['level3_selected'] else 'FAIL'}"
    )

    print(
        f"LEVEL 3 - Global Chroma       : "
        f"{'PASS' if RESULTS['level3_global'] else 'FAIL'}"
    )

    print(
        f"LEVEL 4 - Semantic retrieval  : "
        f"{'PASS' if RESULTS['level4'] else 'FAIL'}"
    )

    print(
        f"LEVEL 5 - Coverage state      : "
        f"{'PASS' if RESULTS['level5'] else 'FAIL'}"
    )

    print()

    print(
        "Global Chroma statistics:"
    )

    print(
        f"  Duplicate IDs       : "
        f"{RESULTS['global_duplicate_ids']}"
    )

    print(
        f"  Invalid metadata    : "
        f"{RESULTS['global_invalid_metadata']}"
    )

    print(
        f"  Empty/short docs    : "
        f"{RESULTS['global_short_documents']}"
    )

    print()

    # ========================================================
    # DECISION
    # ========================================================

    critical_levels_pass = (

        RESULTS["level1"]

        and RESULTS["level2"]

        and RESULTS["level3_selected"]

        and RESULTS["level4"]

        and RESULTS["level5"]

    )

    if critical_levels_pass:

        success(
            "SELECTED POLICY VALIDATION PASSED."
        )

        print()

        if RESULTS["global_short_documents"] > 0:

            warning(
                "GLOBAL CHROMA HAS DOCUMENT-QUALITY WARNINGS."
            )

            warning(
                "These warnings should be investigated, "
                "but the selected policy chain is valid."
            )

        else:

            success(
                "GLOBAL CHROMA INTEGRITY ALSO PASSED."
            )

        print()

        print(
            "The verified policy evidence can proceed "
            "to patient-data decision testing."
        )

    else:

        failure(
            "SELECTED POLICY VALIDATION FAILED."
        )

        print()

        print(
            "Do NOT proceed to patient decision testing "
            "until the failed selected-policy level is fixed."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    title(
        "PRIOR AUTHORIZATION KB - "
        "STRICT 5 LEVEL VALIDATION"
    )

    print(
        "READ-ONLY TEST"
    )

    print(
        "No MySQL or Chroma data will be modified."
    )

    print()

    print(
        f"MySQL configured : "
        f"{'YES' if MYSQL_URL else 'NO'}"
    )

    print(
        f"Chroma directory : "
        f"{CHROMA_DIR}"
    )

    print(
        f"Chroma collection: "
        f"{COLLECTION_NAME}"
    )

    print(
        f"Embedding model  : "
        f"{EMBED_MODEL}"
    )

    print(
        f"Article directory: "
        f"{ARTICLE_DIR}"
    )

    print(
        f"LCD directory    : "
        f"{LCD_DIR}"
    )

    print(
        f"NCD directory    : "
        f"{NCD_DIR}"
    )

    # ========================================================
    # INPUT
    # ========================================================

    title(
        "TEST INPUT"
    )

    print(
        "Use an HCPCS + ICD-10 combination "
        "that exists in your Article source CSV."
    )

    print()

    hcpc_code = input(
        "Enter HCPCS/CPT code: "
    ).strip().upper()

    icd10_code = input(
        "Enter ICD-10 code: "
    ).strip().upper()

    if not hcpc_code:

        raise ValueError(
            "HCPCS/CPT code is required."
        )

    if not icd10_code:

        raise ValueError(
            "ICD-10 code is required."
        )

    print()

    print(
        f"HCPCS : {hcpc_code}"
    )

    print(
        f"ICD10 : {icd10_code}"
    )

    # ========================================================
    # LEVEL 1
    # ========================================================

    level_1_csv_to_mysql(
        hcpc_code,
        icd10_code
    )

    # ========================================================
    # LEVEL 2
    # ========================================================

    policies, coverage_state = (
        level_2_exact_match(
            hcpc_code,
            icd10_code
        )
    )

    # ========================================================
    # LEVEL 3
    # ========================================================

    valid_sources, collection = (
        level_3_mysql_to_chroma(
            policies
        )
    )

    # ========================================================
    # LEVEL 4
    # ========================================================

    if valid_sources:

        level_4_semantic_retrieval(
            valid_sources,
            collection
        )

    else:

        failure(
            "LEVEL 4 skipped because no verified "
            "Chroma sources exist."
        )

        RESULTS[
            "level4"
        ] = False

    # ========================================================
    # LEVEL 5
    # ========================================================

    level_5_coverage_state(
        hcpc_code,
        icd10_code,
        coverage_state,
        policies
    )

    # ========================================================
    # FINAL
    # ========================================================

    final_summary()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()