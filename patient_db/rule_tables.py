"""
Loads article_policy, article_hcpc, article_icd10_covered, article_icd10_noncovered
from the raw all_article CSVs into MySQL, filtered to status='A' (active) only.

Run AFTER schema_mysql.sql has created the tables.
Run BEFORE build_crosswalk_mysql.py (which reads article_hcpc/article_icd10_*
to match against).
"""
import csv, sys
from pathlib import Path
from db_config import get_connection

csv.field_size_limit(sys.maxsize)
DATA = Path("/home/claude/data")  # adjust to wherever you unzip the CMS files


def active_article_ids():
    ids = set()
    with open(DATA / "all_article/csv/article.csv", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if row["status"] == "A":
                ids.add((row["article_id"], row["article_version"]))
    return ids


def main():
    active = active_article_ids()
    print(f"{len(active)} active (article_id, article_version) pairs")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SET foreign_key_checks = 0")

    cur.execute("TRUNCATE TABLE article_policy")
    with open(DATA / "all_article/csv/article.csv", encoding="utf-8", errors="replace") as f:
        rows = [(r["article_id"], r["article_version"], r["title"], r["status"])
                for r in csv.DictReader(f) if r["status"] == "A"]
    cur.executemany("INSERT INTO article_policy (article_id, article_version, title, status) "
                     "VALUES (%s,%s,%s,%s)", rows)
    print(f"article_policy: {len(rows)} rows")

    cur.execute("TRUNCATE TABLE article_hcpc")
    with open(DATA / "all_article/csv/article_x_hcpc_code.csv", encoding="utf-8", errors="replace") as f:
        rows = [(r["article_id"], r["article_version"], r["hcpc_code_id"],
                 r["long_description"], r["short_description"])
                for r in csv.DictReader(f) if (r["article_id"], r["article_version"]) in active]
    cur.executemany("INSERT INTO article_hcpc "
                     "(article_id, article_version, hcpc_code, long_description, short_description) "
                     "VALUES (%s,%s,%s,%s,%s)", rows)
    print(f"article_hcpc: {len(rows)} rows")

    cur.execute("TRUNCATE TABLE article_icd10_covered")
    with open(DATA / "all_article/csv/article_x_icd10_covered.csv", encoding="utf-8", errors="replace") as f:
        rows = [(r["article_id"], r["article_version"], r["icd10_code_id"],
                 r["icd10_covered_group"], r["description"])
                for r in csv.DictReader(f) if (r["article_id"], r["article_version"]) in active]
    cur.executemany("INSERT INTO article_icd10_covered "
                     "(article_id, article_version, icd10_code, covered_group, description) "
                     "VALUES (%s,%s,%s,%s,%s)", rows)
    print(f"article_icd10_covered: {len(rows)} rows")

    cur.execute("TRUNCATE TABLE article_icd10_noncovered")
    with open(DATA / "all_article/csv/article_x_icd10_noncovered.csv", encoding="utf-8", errors="replace") as f:
        rows = [(r["article_id"], r["article_version"], r["icd10_code_id"],
                 r["icd10_noncovered_group"], r["description"])
                for r in csv.DictReader(f) if (r["article_id"], r["article_version"]) in active]
    cur.executemany("INSERT INTO article_icd10_noncovered "
                     "(article_id, article_version, icd10_code, noncovered_group, description) "
                     "VALUES (%s,%s,%s,%s,%s)", rows)
    print(f"article_icd10_noncovered: {len(rows)} rows")

    cur.execute("SET foreign_key_checks = 1")
    conn.commit()
    cur.close()
    conn.close()
    print("Rule tables loaded.")


if __name__ == "__main__":
    main()