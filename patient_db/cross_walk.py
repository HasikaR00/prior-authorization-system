"""
Same word-overlap crosswalk matching as before (inverted index + Dice score),
just writing to MySQL instead of SQLite.

Run AFTER load_rule_tables_mysql.py (reads article_hcpc/article_icd10_covered/
article_icd10_noncovered as the reference vocabularies to match against).
Run BEFORE build_patient_db_mysql.py (which uses resolved_snomed_icd10/hcpcs).
"""
import csv, re, sys
from pathlib import Path
from db_config import get_connection

csv.field_size_limit(sys.maxsize)
DATA = Path("/home/claude/data")
CONFIDENCE_THRESHOLD = 0.5
STOPWORDS = {
    "of", "the", "and", "in", "to", "with", "without", "for", "on", "at",
    "unspecified", "other", "specified", "due", "not", "elsewhere", "classified",
    "type", "disorder", "procedure", "finding", "abnormality", "morphologic",
    "structure", "entire", "as"
}
WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text):
    text = re.sub(r"\([^)]*\)", " ", text.lower())
    return {w for w in WORD_RE.findall(text) if w not in STOPWORDS and len(w) > 2}


def dice(a, b):
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def load_distinct(path, code_col, desc_col):
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            code = row[code_col]
            if code and code not in out:
                out[code] = row[desc_col]
    return out


def load_distinct_from_mysql(cur, table, code_col, desc_col):
    cur.execute(f"SELECT DISTINCT {code_col}, {desc_col} FROM {table}")
    out = {}
    for code, desc in cur.fetchall():
        if code and code not in out:
            out[code] = desc
    return out


def build_index(ref):
    tokens = {code: tokenize(desc) for code, desc in ref.items()}
    index = {}
    for code, toks in tokens.items():
        for t in toks:
            index.setdefault(t, set()).add(code)
    return index, tokens


def best_match(query_desc, index, ref_tokens, ref_desc):
    q_tokens = tokenize(query_desc)
    candidates = set()
    for t in q_tokens:
        candidates |= index.get(t, set())
    if not candidates:
        return None, None, 0.0
    best_code, best_score = None, 0.0
    for code in candidates:
        score = dice(q_tokens, ref_tokens[code])
        if score > best_score:
            best_score, best_code = score, code
    return (best_code, ref_desc[best_code], best_score) if best_code else (None, None, 0.0)


def main():
    conn = get_connection()
    cur = conn.cursor()

    print("Loading SNOMED source vocabularies...")
    snomed_conditions = load_distinct(
        DATA / "synthea_sample_data_csv_nov2021/csv/conditions.csv", "CODE", "DESCRIPTION")
    snomed_procedures = load_distinct(
        DATA / "synthea_sample_data_csv_nov2021/csv/procedures.csv", "CODE", "DESCRIPTION")

    print("Loading CMS reference vocabularies from MySQL...")
    icd10_ref = load_distinct_from_mysql(cur, "article_icd10_covered", "icd10_code", "description")
    icd10_noncov_ref = load_distinct_from_mysql(cur, "article_icd10_noncovered", "icd10_code", "description")
    for code, desc in icd10_noncov_ref.items():
        icd10_ref.setdefault(code, desc)
    hcpc_ref = load_distinct_from_mysql(cur, "article_hcpc", "hcpc_code", "long_description")
    print(f"  {len(icd10_ref)} ICD-10 codes, {len(hcpc_ref)} HCPCS codes")

    icd10_index, icd10_tokens = build_index(icd10_ref)
    hcpc_index, hcpc_tokens = build_index(hcpc_ref)

    print("Matching SNOMED -> ICD-10-CM...")
    icd10_rows = []
    for code, desc in snomed_conditions.items():
        m_code, m_desc, score = best_match(desc, icd10_index, icd10_tokens, icd10_ref)
        icd10_rows.append((code, desc, m_code, m_desc, round(score, 3),
                            1 if (m_code is None or score < CONFIDENCE_THRESHOLD) else 0))

    print("Matching SNOMED -> HCPCS/CPT...")
    hcpc_rows = []
    for code, desc in snomed_procedures.items():
        m_code, m_desc, score = best_match(desc, hcpc_index, hcpc_tokens, hcpc_ref)
        hcpc_rows.append((code, desc, m_code, m_desc, round(score, 3),
                           1 if (m_code is None or score < CONFIDENCE_THRESHOLD) else 0))

    cur.execute("TRUNCATE TABLE crosswalk_snomed_icd10")
    cur.executemany(
        "INSERT INTO crosswalk_snomed_icd10 "
        "(snomed_code, snomed_description, icd10_code, icd10_description, match_score, needs_review) "
        "VALUES (%s,%s,%s,%s,%s,%s)", icd10_rows)

    cur.execute("TRUNCATE TABLE crosswalk_snomed_hcpcs")
    cur.executemany(
        "INSERT INTO crosswalk_snomed_hcpcs "
        "(snomed_code, snomed_description, hcpc_code, hcpc_description, match_score, needs_review) "
        "VALUES (%s,%s,%s,%s,%s,%s)", hcpc_rows)

    conn.commit()
    n_review_icd = sum(r[5] for r in icd10_rows)
    n_review_hcpc = sum(r[5] for r in hcpc_rows)
    print(f"crosswalk_snomed_icd10: {len(icd10_rows)} rows, {n_review_icd} need review")
    print(f"crosswalk_snomed_hcpcs: {len(hcpc_rows)} rows, {n_review_hcpc} need review")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()