"""
Builds the patient reference tables in MySQL. Same design as the SQLite
version: SNOMED history is resolved to HCPCS/ICD-10 at LOAD time (via the
resolved_snomed_* views, which read crosswalk_manual_override automatically),
so live queries during a PA request are plain exact-match lookups.

Run LAST, after load_rule_tables_mysql.py and build_crosswalk_mysql.py.
"""
import csv, sys, datetime
from pathlib import Path
from db_config import get_connection

csv.field_size_limit(sys.maxsize)
DATA = Path("/home/claude/data/synthea_sample_data_csv_nov2021/csv")


def load_csv(name):
    with open(DATA / name, encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def main():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SET foreign_key_checks = 0")

    # ---- patients ----
    cur.execute("TRUNCATE TABLE patients")
    patients = load_csv("patients.csv")
    cur.executemany(
        "INSERT INTO patients (patient_id, first_name, last_name, birthdate, gender, state) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        [(p["Id"], p["FIRST"], p["LAST"], p["BIRTHDATE"], p["GENDER"], p["STATE"]) for p in patients]
    )
    print(f"patients: {len(patients)} rows")

    # ---- current plan, resolved "as of" the dataset's own latest timestamp ----
    cur.execute("TRUNCATE TABLE patient_plan")
    transitions = load_csv("payer_transitions.csv")
    payers = {p["Id"]: p["NAME"] for p in load_csv("payers.csv")}

    def parse_date(s):
        return datetime.date.fromisoformat(s[:10]) if s else None

    all_dates = [parse_date(t["END_YEAR"]) for t in transitions if t["END_YEAR"]]
    all_dates += [parse_date(t["START_YEAR"]) for t in transitions if t["START_YEAR"]]
    AS_OF = max(d for d in all_dates if d is not None)
    print(f"Using dataset as-of date: {AS_OF}")

    latest = {}
    for t in transitions:
        end_dt = parse_date(t["END_YEAR"]) or datetime.date(9999, 1, 1)
        key = t["PATIENT"]
        if key not in latest or end_dt >= latest[key][0]:
            latest[key] = (end_dt, t)
    rows = []
    for patient_id, (end_dt, t) in latest.items():
        is_active = 1 if (end_dt.year == 9999 or end_dt >= AS_OF) else 0
        rows.append((patient_id, t["MEMBERID"], payers.get(t["PAYER"], t["PAYER"]),
                      t["START_YEAR"], t["END_YEAR"], is_active))
    cur.executemany(
        "INSERT INTO patient_plan (patient_id, member_id, payer_name, start_year, end_year, is_active) "
        "VALUES (%s,%s,%s,%s,%s,%s)", rows)
    print(f"patient_plan: {len(rows)} rows ({sum(r[5] for r in rows)} currently active)")

    # ---- procedure history, SNOMED resolved to HCPCS via the MySQL view ----
    cur.execute("SELECT snomed_code, hcpc_code, match_score FROM resolved_snomed_hcpcs")
    resolved_hcpc = {code: (hcpc, score) for code, hcpc, score in cur.fetchall()}

    cur.execute("TRUNCATE TABLE patient_procedure_history")
    procedures = load_csv("procedures.csv")
    rows = []
    for p in procedures:
        hcpc_code, hcpc_score = resolved_hcpc.get(p["CODE"], (None, 0.0))
        rows.append((p["PATIENT"], p["ENCOUNTER"], p["CODE"], p["DESCRIPTION"],
                      p["START"], p.get("REASONCODE", ""), hcpc_code, hcpc_score))
    cur.executemany(
        "INSERT INTO patient_procedure_history "
        "(patient_id, encounter_id, snomed_code, description, proc_date, reason_snomed_code, "
        "resolved_hcpc_code, resolved_hcpc_score) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows)
    print(f"patient_procedure_history: {len(rows)} rows")

    # ---- condition history, SNOMED resolved to ICD-10 via the MySQL view ----
    cur.execute("SELECT snomed_code, icd10_code, match_score FROM resolved_snomed_icd10")
    resolved_icd10 = {code: (icd, score) for code, icd, score in cur.fetchall()}

    cur.execute("TRUNCATE TABLE patient_condition_history")
    conditions = load_csv("conditions.csv")
    rows = []
    for c in conditions:
        icd10_code, icd10_score = resolved_icd10.get(c["CODE"], (None, 0.0))
        rows.append((c["PATIENT"], c["CODE"], c["DESCRIPTION"], c["START"], c["STOP"],
                      icd10_code, icd10_score))
    cur.executemany(
        "INSERT INTO patient_condition_history "
        "(patient_id, snomed_code, description, start_date, stop_date, "
        "resolved_icd10_code, resolved_icd10_score) VALUES (%s,%s,%s,%s,%s,%s,%s)", rows)
    print(f"patient_condition_history: {len(rows)} rows")

    # ---- careplans ----
    cur.execute("TRUNCATE TABLE patient_careplan_history")
    careplans = load_csv("careplans.csv")
    cur.executemany(
        "INSERT INTO patient_careplan_history "
        "(patient_id, description, reason_snomed_code, reason_description, start_date, stop_date) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        [(cp["PATIENT"], cp["DESCRIPTION"], cp.get("REASONCODE", ""),
          cp.get("REASONDESCRIPTION", ""), cp["START"], cp["STOP"]) for cp in careplans]
    )
    print(f"patient_careplan_history: {len(careplans)} rows")

    cur.execute("SET foreign_key_checks = 1")
    conn.commit()
    cur.close()
    conn.close()
    print("Patient DB built.")


def lookup_patient(patient_id: str, birthdate: str, conn):
    """The query the frontend runs after staff enters the two-field key."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM patients WHERE patient_id=%s AND birthdate=%s", (patient_id, birthdate))
    patient = cur.fetchone()
    if not patient:
        return None
    cur.execute("SELECT * FROM patient_plan WHERE patient_id=%s", (patient_id,))
    plan = cur.fetchone()
    cur.execute("SELECT * FROM patient_procedure_history WHERE patient_id=%s ORDER BY proc_date DESC", (patient_id,))
    procedures = cur.fetchall()
    cur.execute("SELECT * FROM patient_condition_history WHERE patient_id=%s ORDER BY start_date DESC", (patient_id,))
    conditions = cur.fetchall()
    cur.execute("SELECT * FROM patient_careplan_history WHERE patient_id=%s ORDER BY start_date DESC", (patient_id,))
    careplans = cur.fetchall()
    cur.close()
    return {"patient": patient, "plan": plan, "procedure_history": procedures,
            "condition_history": conditions, "careplan_history": careplans}


def check_prior_utilization(patient_id: str, requested_hcpc_code: str, conn):
    """Field #5 - plain exact-match query, no crosswalk at request time."""
    cur = conn.cursor()
    cur.execute(
        "SELECT proc_date FROM patient_procedure_history "
        "WHERE patient_id=%s AND resolved_hcpc_code=%s ORDER BY proc_date DESC",
        (patient_id, requested_hcpc_code)
    )
    rows = cur.fetchall()
    cur.close()
    return {"prior_count": len(rows), "most_recent_date": rows[0][0] if rows else None}


if __name__ == "__main__":
    main()