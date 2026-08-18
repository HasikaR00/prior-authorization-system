"""
=============================================================
SYNTHEA -> PRIOR AUTHORIZATION PATIENT DATABASE LOADER
=============================================================

Purpose:
    Load extracted Synthea CSV files into the existing
    pa_system MySQL database.

SOURCE CSV FILES:
    patients.csv
    conditions.csv
    procedures.csv
    careplans.csv
    payer_transitions.csv
    payers.csv

TARGET MYSQL TABLES:
    patients
    patient_plan
    patient_condition_history
    patient_procedure_history
    patient_careplan_history

IMPORTANT:
    - No LOAD DATA LOCAL INFILE
    - No ZIP extraction required
    - Uses pandas + mysql-connector
    - Uses existing MySQL crosswalk views
    - SNOMED -> ICD-10 resolved through:
          resolved_snomed_icd10
    - SNOMED -> HCPCS resolved through:
          resolved_snomed_hcpcs

FOLDER STRUCTURE:

    patient_db/
        load_patient_data.py
        patients.csv
        conditions.csv
        procedures.csv
        careplans.csv
        payer_transitions.csv
        payers.csv

=============================================================
"""

import os
import re
import sys
from datetime import datetime

import pandas as pd
import mysql.connector


# ============================================================
# CONFIGURATION
# ============================================================

# Automatically use the folder containing this Python script.
CSV_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

# MySQL
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "HASIKA10$s"
MYSQL_DATABASE = "pa_system"

# Number of patients to load
MAX_PATIENTS = 100

# ============================================================
# TESTING CONFIGURATION
# ============================================================

# Your PA prototype testing date.
REFERENCE_DATE = pd.Timestamp(
    "2026-08-15",
    tz="UTC"
)

# ------------------------------------------------------------
# IMPORTANT:
#
# True:
#   The latest insurance record for each selected patient
#   is treated as ACTIVE.
#
# This is useful because Synthea sample datasets often contain
# historical insurance dates such as 2021-2022, while your
# prototype is being tested in 2026.
#
# False:
#   Insurance eligibility is calculated honestly against
#   REFERENCE_DATE.
#
# For your current prototype testing:
#       TRUE
#
# For production:
#       FALSE
# ------------------------------------------------------------

FORCE_LATEST_PLAN_ACTIVE_FOR_TESTING = True


# ============================================================
# DATABASE RESET
# ============================================================

# True:
#   Remove existing patient population and reload selected
#   patients from CSV.
#
# WARNING:
#   This also deletes pa_request and pa_decision_log because
#   those records depend on patients.
#
# False:
#   Existing data is preserved and new records are upserted.
#
# Recommended while building/testing:
#       True
# ============================================================

RESET_DATABASE_PATIENT_DATA = True


# ============================================================
# REQUIRED CSV FILES
# ============================================================

REQUIRED_FILES = [
    "patients.csv",
    "conditions.csv",
    "procedures.csv",
    "careplans.csv",
    "payer_transitions.csv",
    "payers.csv"
]


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def clean_string(value):
    """
    Convert NaN/None/empty values to None.
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value.lower() in {
        "nan",
        "none",
        "null"
    }:
        return None

    return value


def clean_code(value):
    """
    Clean SNOMED / ICD-10 / HCPCS style codes.

    Example:
        87433001
        87433001.0
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    # Remove accidental .0
    if re.fullmatch(
        r"\d+\.0",
        value
    ):
        value = value[:-2]

    return value


def clean_date(value):
    """
    Keep Synthea date/timestamp as a string because
    destination schema uses VARCHAR fields.
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


# ============================================================
# CHECK CSV FILES
# ============================================================

def check_csv_files():

    print("\n")
    print("=" * 75)
    print("CHECKING CSV FILES")
    print("=" * 75)

    print("Python script directory:")
    print(CSV_DIR)

    missing = []

    for filename in REQUIRED_FILES:

        path = os.path.join(
            CSV_DIR,
            filename
        )

        if os.path.exists(path):

            size_mb = (
                os.path.getsize(path)
                / (1024 * 1024)
            )

            print(
                f"[OK] {filename:<25} "
                f"{size_mb:.2f} MB"
            )

        else:

            print(
                f"[MISSING] {filename}"
            )

            missing.append(filename)

    if missing:

        raise FileNotFoundError(
            "\nMissing required CSV files:\n"
            + "\n".join(
                f"  - {x}"
                for x in missing
            )
            + "\n\nMake sure all CSV files are in the "
              "same folder as this Python script."
        )

    print("\nAll required CSV files found.")


# ============================================================
# READ CSV
# ============================================================

def read_csv(filename):

    path = os.path.join(
        CSV_DIR,
        filename
    )

    print(
        f"\nReading: {filename}"
    )

    df = pd.read_csv(
        path,
        low_memory=False
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Columns: {len(df.columns)}"
    )

    return df


# ============================================================
# LOAD ALL SOURCE DATA
# ============================================================

def load_source_data():

    print("\n")
    print("=" * 75)
    print("LOADING SYNTHEA SOURCE DATA")
    print("=" * 75)

    patients = read_csv(
        "patients.csv"
    )

    conditions = read_csv(
        "conditions.csv"
    )

    procedures = read_csv(
        "procedures.csv"
    )

    careplans = read_csv(
        "careplans.csv"
    )

    payer_transitions = read_csv(
        "payer_transitions.csv"
    )

    payers = read_csv(
        "payers.csv"
    )

    print("\n")
    print("-" * 75)
    print("SOURCE DATA SUMMARY")
    print("-" * 75)

    print(
        f"Patients              : {len(patients):,}"
    )

    print(
        f"Conditions            : {len(conditions):,}"
    )

    print(
        f"Procedures            : {len(procedures):,}"
    )

    print(
        f"Careplans             : {len(careplans):,}"
    )

    print(
        f"Payer transitions     : {len(payer_transitions):,}"
    )

    print(
        f"Payers                : {len(payers):,}"
    )

    return (
        patients,
        conditions,
        procedures,
        careplans,
        payer_transitions,
        payers
    )


# ============================================================
# MYSQL CONNECTION
# ============================================================

def get_connection():

    print("\n")
    print("=" * 75)
    print("CONNECTING TO MYSQL")
    print("=" * 75)

    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False
    )

    print(
        f"Connected to database: {MYSQL_DATABASE}"
    )

    return conn


# ============================================================
# RESET DATABASE PATIENT DATA
# ============================================================

def reset_database(conn):

    if not RESET_DATABASE_PATIENT_DATA:

        print(
            "\nDatabase reset is DISABLED."
        )

        return

    print("\n")
    print("=" * 75)
    print("RESETTING OLD PATIENT DATA")
    print("=" * 75)

    cursor = conn.cursor()

    try:

        # ----------------------------------------------------
        # Foreign-key dependency order
        # ----------------------------------------------------

        print(
            "Deleting PA decision logs..."
        )

        cursor.execute("""
            DELETE FROM pa_decision_log
        """)

        print(
            "Deleting PA requests..."
        )

        cursor.execute("""
            DELETE FROM pa_request
        """)

        print(
            "Deleting careplan history..."
        )

        cursor.execute("""
            DELETE FROM patient_careplan_history
        """)

        print(
            "Deleting procedure history..."
        )

        cursor.execute("""
            DELETE FROM patient_procedure_history
        """)

        print(
            "Deleting condition history..."
        )

        cursor.execute("""
            DELETE FROM patient_condition_history
        """)

        print(
            "Deleting patient plans..."
        )

        cursor.execute("""
            DELETE FROM patient_plan
        """)

        print(
            "Deleting patients..."
        )

        cursor.execute("""
            DELETE FROM patients
        """)

        conn.commit()

        print(
            "\nOld patient population removed successfully."
        )

    except Exception as e:

        conn.rollback()

        print(
            "\nERROR while resetting database:"
        )

        print(e)

        raise

    finally:

        cursor.close()


# ============================================================
# SELECT PATIENTS
# ============================================================

def select_patients(
    patients,
    conditions,
    procedures,
    careplans
):

    print("\n")
    print("=" * 75)
    print(
        f"SELECTING {MAX_PATIENTS} MOST RECENTLY ACTIVE PATIENTS"
    )
    print("=" * 75)

    patients["Id"] = (
        patients["Id"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Convert dates
    # --------------------------------------------------------

    conditions["_date"] = pd.to_datetime(
        conditions["START"],
        errors="coerce",
        utc=True
    )

    procedures["_date"] = pd.to_datetime(
        procedures["START"],
        errors="coerce",
        utc=True
    )

    careplans["_date"] = pd.to_datetime(
        careplans["START"],
        errors="coerce",
        utc=True
    )

    # --------------------------------------------------------
    # Latest condition activity
    # --------------------------------------------------------

    condition_latest = (
        conditions
        .groupby("PATIENT")["_date"]
        .max()
    )

    # --------------------------------------------------------
    # Latest procedure activity
    # --------------------------------------------------------

    procedure_latest = (
        procedures
        .groupby("PATIENT")["_date"]
        .max()
    )

    # --------------------------------------------------------
    # Latest careplan activity
    # --------------------------------------------------------

    careplan_latest = (
        careplans
        .groupby("PATIENT")["_date"]
        .max()
    )

    # --------------------------------------------------------
    # Combine activity
    # --------------------------------------------------------

    activity = pd.concat(
        [
            condition_latest,
            procedure_latest,
            careplan_latest
        ],
        axis=1
    )

    activity["latest_activity"] = (
        activity.max(axis=1)
    )

    activity = activity.sort_values(
        "latest_activity",
        ascending=False
    )

    # --------------------------------------------------------
    # Select top N
    # --------------------------------------------------------

    selected_ids = set(
        activity
        .head(MAX_PATIENTS)
        .index
        .astype(str)
    )

    selected_patients = patients[
        patients["Id"].isin(
            selected_ids
        )
    ].copy()

    print(
        f"\nSelected patients: "
        f"{len(selected_patients)}"
    )

    return (
        selected_patients,
        selected_ids
    )


# ============================================================
# INSERT PATIENTS
# ============================================================

def insert_patients(
    cursor,
    patients
):

    print("\n")
    print("=" * 75)
    print("LOADING patients")
    print("=" * 75)

    sql = """
        INSERT INTO patients
        (
            patient_id,
            first_name,
            last_name,
            birthdate,
            gender,
            state
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON DUPLICATE KEY UPDATE
            first_name = VALUES(first_name),
            last_name = VALUES(last_name),
            birthdate = VALUES(birthdate),
            gender = VALUES(gender),
            state = VALUES(state)
    """

    rows = []

    for _, r in patients.iterrows():

        rows.append(
            (
                clean_string(r["Id"]),
                clean_string(r["FIRST"]),
                clean_string(r["LAST"]),
                clean_date(r["BIRTHDATE"]),
                clean_string(r["GENDER"]),
                clean_string(r["STATE"])
            )
        )

    if rows:

        cursor.executemany(
            sql,
            rows
        )

    print(
        f"Patients inserted/updated: "
        f"{len(rows)}"
    )


# ============================================================
# INSERT CONDITION HISTORY
# ============================================================

def insert_conditions(
    cursor,
    conditions,
    selected_ids
):

    print("\n")
    print("=" * 75)
    print("LOADING patient_condition_history")
    print("=" * 75)

    df = conditions[
        conditions["PATIENT"]
        .astype(str)
        .isin(selected_ids)
    ].copy()

    # --------------------------------------------------------
    # Only SNOMED records
    # --------------------------------------------------------

    if "SYSTEM" in df.columns:

        df = df[
            df["SYSTEM"]
            .fillna("")
            .astype(str)
            .str.contains(
                "snomed",
                case=False,
                na=False
            )
        ]

    print(
        f"Condition rows selected: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------
    # Get existing crosswalk
    # --------------------------------------------------------

    print(
        "\nLoading SNOMED -> ICD-10 crosswalk..."
    )

    cursor.execute("""
        SELECT
            snomed_code,
            icd10_code,
            match_score
        FROM resolved_snomed_icd10
    """)

    crosswalk = cursor.fetchall()

    icd_map = {}

    for row in crosswalk:

        snomed = clean_code(
            row[0]
        )

        if snomed:

            icd_map[snomed] = (
                clean_code(row[1]),
                row[2]
            )

    print(
        f"Crosswalk mappings available: "
        f"{len(icd_map):,}"
    )

    # --------------------------------------------------------
    # Insert
    # --------------------------------------------------------

    sql = """
        INSERT INTO patient_condition_history
        (
            patient_id,
            snomed_code,
            description,
            start_date,
            stop_date,
            resolved_icd10_code,
            resolved_icd10_score
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    rows = []

    mapped = 0
    unmapped = 0

    for _, r in df.iterrows():

        patient_id = clean_string(
            r["PATIENT"]
        )

        snomed_code = clean_code(
            r["CODE"]
        )

        mapping = icd_map.get(
            snomed_code
        )

        if mapping:

            resolved_icd10 = mapping[0]
            score = mapping[1]

            mapped += 1

        else:

            resolved_icd10 = None
            score = None

            unmapped += 1

        rows.append(
            (
                patient_id,
                snomed_code,
                clean_string(
                    r["DESCRIPTION"]
                ),
                clean_date(
                    r["START"]
                ),
                clean_date(
                    r["STOP"]
                ),
                resolved_icd10,
                score
            )
        )

    if rows:

        cursor.executemany(
            sql,
            rows
        )

    print(
        f"\nCondition records inserted : "
        f"{len(rows):,}"
    )

    print(
        f"ICD-10 mappings found       : "
        f"{mapped:,}"
    )

    print(
        f"ICD-10 mappings missing     : "
        f"{unmapped:,}"
    )


# ============================================================
# INSERT PROCEDURE HISTORY
# ============================================================

def insert_procedures(
    cursor,
    procedures,
    selected_ids
):

    print("\n")
    print("=" * 75)
    print("LOADING patient_procedure_history")
    print("=" * 75)

    df = procedures[
        procedures["PATIENT"]
        .astype(str)
        .isin(selected_ids)
    ].copy()

    # --------------------------------------------------------
    # Only SNOMED procedures
    # --------------------------------------------------------

    if "SYSTEM" in df.columns:

        df = df[
            df["SYSTEM"]
            .fillna("")
            .astype(str)
            .str.contains(
                "snomed",
                case=False,
                na=False
            )
        ]

    print(
        f"Procedure rows selected: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------
    # Load HCPCS crosswalk
    # --------------------------------------------------------

    print(
        "\nLoading SNOMED -> HCPCS crosswalk..."
    )

    cursor.execute("""
        SELECT
            snomed_code,
            hcpc_code,
            match_score
        FROM resolved_snomed_hcpcs
    """)

    crosswalk = cursor.fetchall()

    hcpc_map = {}

    for row in crosswalk:

        snomed = clean_code(
            row[0]
        )

        if snomed:

            hcpc_map[snomed] = (
                clean_code(row[1]),
                row[2]
            )

    print(
        f"Crosswalk mappings available: "
        f"{len(hcpc_map):,}"
    )

    # --------------------------------------------------------
    # Insert
    # --------------------------------------------------------

    sql = """
        INSERT INTO patient_procedure_history
        (
            patient_id,
            encounter_id,
            snomed_code,
            description,
            proc_date,
            reason_snomed_code,
            resolved_hcpc_code,
            resolved_hcpc_score
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    rows = []

    mapped = 0
    unmapped = 0

    for _, r in df.iterrows():

        patient_id = clean_string(
            r["PATIENT"]
        )

        snomed_code = clean_code(
            r["CODE"]
        )

        mapping = hcpc_map.get(
            snomed_code
        )

        if mapping:

            resolved_hcpc = mapping[0]
            score = mapping[1]

            mapped += 1

        else:

            resolved_hcpc = None
            score = None

            unmapped += 1

        rows.append(
            (
                patient_id,
                clean_string(
                    r["ENCOUNTER"]
                ),
                snomed_code,
                clean_string(
                    r["DESCRIPTION"]
                ),
                clean_date(
                    r["START"]
                ),
                clean_code(
                    r["REASONCODE"]
                ),
                resolved_hcpc,
                score
            )
        )

    if rows:

        cursor.executemany(
            sql,
            rows
        )

    print(
        f"\nProcedure records inserted : "
        f"{len(rows):,}"
    )

    print(
        f"HCPCS mappings found        : "
        f"{mapped:,}"
    )

    print(
        f"HCPCS mappings missing      : "
        f"{unmapped:,}"
    )


# ============================================================
# INSERT CAREPLAN HISTORY
# ============================================================

def insert_careplans(
    cursor,
    careplans,
    selected_ids
):

    print("\n")
    print("=" * 75)
    print("LOADING patient_careplan_history")
    print("=" * 75)

    df = careplans[
        careplans["PATIENT"]
        .astype(str)
        .isin(selected_ids)
    ].copy()

    print(
        f"Careplan rows selected: "
        f"{len(df):,}"
    )

    sql = """
        INSERT INTO patient_careplan_history
        (
            patient_id,
            description,
            reason_snomed_code,
            reason_description,
            start_date,
            stop_date
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
    """

    rows = []

    for _, r in df.iterrows():

        rows.append(
            (
                clean_string(
                    r["PATIENT"]
                ),
                clean_string(
                    r["DESCRIPTION"]
                ),
                clean_code(
                    r["REASONCODE"]
                ),
                clean_string(
                    r["REASONDESCRIPTION"]
                ),
                clean_date(
                    r["START"]
                ),
                clean_date(
                    r["STOP"]
                )
            )
        )

    if rows:

        cursor.executemany(
            sql,
            rows
        )

    print(
        f"Careplan records inserted: "
        f"{len(rows):,}"
    )


# ============================================================
# INSERT PATIENT PLAN
# ============================================================

def insert_patient_plans(
    cursor,
    payer_transitions,
    payers,
    selected_ids
):

    print("\n")
    print("=" * 75)
    print("LOADING patient_plan")
    print("=" * 75)

    pt = payer_transitions[
        payer_transitions["PATIENT"]
        .astype(str)
        .isin(selected_ids)
    ].copy()

    # --------------------------------------------------------
    # Convert dates
    # --------------------------------------------------------

    pt["_START"] = pd.to_datetime(
        pt["START_DATE"],
        errors="coerce",
        utc=True
    )

    pt["_END"] = pd.to_datetime(
        pt["END_DATE"],
        errors="coerce",
        utc=True
    )

    # --------------------------------------------------------
    # Sort by latest insurance record
    # --------------------------------------------------------

    pt = (
        pt
        .sort_values(
            ["PATIENT", "_END"]
        )
        .groupby(
            "PATIENT",
            as_index=False
        )
        .tail(1)
    )

    # --------------------------------------------------------
    # Payer ID -> payer name
    # --------------------------------------------------------

    payer_map = {}

    for _, r in payers.iterrows():

        payer_id = clean_string(
            r["Id"]
        )

        payer_name = clean_string(
            r["NAME"]
        )

        if payer_id:

            payer_map[payer_id] = payer_name

    # --------------------------------------------------------
    # SQL
    # --------------------------------------------------------

    sql = """
        INSERT INTO patient_plan
        (
            patient_id,
            member_id,
            payer_name,
            start_year,
            end_year,
            is_active
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        )
        ON DUPLICATE KEY UPDATE
            member_id = VALUES(member_id),
            payer_name = VALUES(payer_name),
            start_year = VALUES(start_year),
            end_year = VALUES(end_year),
            is_active = VALUES(is_active)
    """

    rows = []

    active_count = 0
    inactive_count = 0

    for _, r in pt.iterrows():

        patient_id = clean_string(
            r["PATIENT"]
        )

        member_id = clean_string(
            r["MEMBERID"]
        )

        payer_id = clean_string(
            r["PAYER"]
        )

        payer_name = payer_map.get(
            payer_id,
            "NO_INSURANCE"
        )

        start_date = clean_date(
            r["START_DATE"]
        )

        end_date = clean_date(
            r["END_DATE"]
        )

        end_timestamp = r["_END"]

        # ----------------------------------------------------
        # TESTING MODE
        # ----------------------------------------------------

        if FORCE_LATEST_PLAN_ACTIVE_FOR_TESTING:

            is_active = 1
            active_count += 1

        else:

            if (
                pd.notna(end_timestamp)
                and end_timestamp >= REFERENCE_DATE
            ):

                is_active = 1
                active_count += 1

            else:

                is_active = 0
                inactive_count += 1

        rows.append(
            (
                patient_id,
                member_id,
                payer_name,
                start_date,
                end_date,
                is_active
            )
        )

    if rows:

        cursor.executemany(
            sql,
            rows
        )

    print(
        f"\nPatient plans inserted/updated: "
        f"{len(rows):,}"
    )

    print(
        f"Active plans                   : "
        f"{active_count:,}"
    )

    print(
        f"Inactive plans                 : "
        f"{inactive_count:,}"
    )

    if FORCE_LATEST_PLAN_ACTIVE_FOR_TESTING:

        print(
            "\n*** TESTING MODE ENABLED ***"
        )

        print(
            "Latest insurance plan for each "
            "selected patient is marked ACTIVE."
        )

        print(
            "Do NOT use this mode for production."
        )


# ============================================================
# DATABASE VERIFICATION
# ============================================================

def verify_database(cursor):

    print("\n")
    print("=" * 75)
    print("DATABASE VERIFICATION")
    print("=" * 75)

    queries = [

        (
            "Patients",
            """
            SELECT COUNT(*)
            FROM patients
            """
        ),

        (
            "Patient plans",
            """
            SELECT COUNT(*)
            FROM patient_plan
            """
        ),

        (
            "Condition history",
            """
            SELECT COUNT(*)
            FROM patient_condition_history
            """
        ),

        (
            "Procedure history",
            """
            SELECT COUNT(*)
            FROM patient_procedure_history
            """
        ),

        (
            "Careplan history",
            """
            SELECT COUNT(*)
            FROM patient_careplan_history
            """
        ),

        (
            "Conditions with ICD-10",
            """
            SELECT COUNT(*)
            FROM patient_condition_history
            WHERE resolved_icd10_code IS NOT NULL
            """
        ),

        (
            "Procedures with HCPCS",
            """
            SELECT COUNT(*)
            FROM patient_procedure_history
            WHERE resolved_hcpc_code IS NOT NULL
            """
        ),

        (
            "Active insurance",
            """
            SELECT COUNT(*)
            FROM patient_plan
            WHERE is_active = 1
            """
        ),

        (
            "Inactive insurance",
            """
            SELECT COUNT(*)
            FROM patient_plan
            WHERE is_active = 0
            """
        )
    ]

    for name, query in queries:

        cursor.execute(query)

        result = cursor.fetchone()[0]

        print(
            f"{name:<35}: {result:,}"
        )


# ============================================================
# SHOW ACTIVE TEST PATIENTS
# ============================================================

def show_test_patients(cursor):

    print("\n")
    print("=" * 75)
    print("PATIENTS AVAILABLE FOR DECISION.PY TESTING")
    print("=" * 75)

    cursor.execute("""
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            pp.member_id,
            pp.payer_name,
            pp.start_year,
            pp.end_year,
            pp.is_active
        FROM patients p
        JOIN patient_plan pp
            ON pp.patient_id = p.patient_id
        WHERE pp.is_active = 1
        ORDER BY p.patient_id
        LIMIT 20
    """)

    rows = cursor.fetchall()

    if not rows:

        print(
            "\nNo active patients found."
        )

        return

    print(
        "\nACTIVE PATIENTS:"
    )

    print("-" * 120)

    for row in rows:

        print(
            f"Patient ID : {row[0]}\n"
            f"Name       : {row[1]} {row[2]}\n"
            f"Member ID  : {row[3]}\n"
            f"Payer      : {row[4]}\n"
            f"Start      : {row[5]}\n"
            f"End        : {row[6]}\n"
            f"Active     : {row[7]}"
        )

        print("-" * 120)


# ============================================================
# SHOW CLINICAL EXAMPLES
# ============================================================

def show_clinical_examples(cursor):

    print("\n")
    print("=" * 75)
    print("CLINICAL DATA AVAILABLE FOR TESTING")
    print("=" * 75)

    # --------------------------------------------------------
    # Conditions
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            c.snomed_code,
            c.description,
            c.resolved_icd10_code,
            c.resolved_icd10_score
        FROM patients p
        JOIN patient_condition_history c
            ON c.patient_id = p.patient_id
        WHERE c.resolved_icd10_code IS NOT NULL
        ORDER BY
            c.resolved_icd10_score DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    print(
        "\nCONDITIONS WITH ICD-10 MAPPING:"
    )

    print("-" * 100)

    for row in rows:

        print(
            f"Patient={row[0]} | "
            f"SNOMED={row[3]} | "
            f"{row[4]} | "
            f"ICD10={row[5]} | "
            f"Score={row[6]}"
        )

    # --------------------------------------------------------
    # Procedures
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            p.patient_id,
            ph.snomed_code,
            ph.description,
            ph.resolved_hcpc_code,
            ph.resolved_hcpc_score
        FROM patients p
        JOIN patient_procedure_history ph
            ON ph.patient_id = p.patient_id
        WHERE ph.resolved_hcpc_code IS NOT NULL
        ORDER BY
            ph.resolved_hcpc_score DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    print(
        "\nPROCEDURES WITH HCPCS MAPPING:"
    )

    print("-" * 100)

    for row in rows:

        print(
            f"Patient={row[0]} | "
            f"SNOMED={row[1]} | "
            f"{row[2]} | "
            f"HCPCS={row[3]} | "
            f"Score={row[4]}"
        )


# ============================================================
# SHOW PATIENT SUMMARY
# ============================================================

def show_patient_summary(cursor):

    print("\n")
    print("=" * 75)
    print("PATIENT SUMMARY FOR PA ENGINE")
    print("=" * 75)

    cursor.execute("""
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            pp.payer_name,
            pp.is_active,

            (
                SELECT COUNT(*)
                FROM patient_condition_history c
                WHERE c.patient_id = p.patient_id
            ) AS condition_count,

            (
                SELECT COUNT(*)
                FROM patient_procedure_history ph
                WHERE ph.patient_id = p.patient_id
            ) AS procedure_count,

            (
                SELECT COUNT(*)
                FROM patient_careplan_history cp
                WHERE cp.patient_id = p.patient_id
            ) AS careplan_count

        FROM patients p

        LEFT JOIN patient_plan pp
            ON pp.patient_id = p.patient_id

        ORDER BY p.patient_id

        LIMIT 20
    """)

    rows = cursor.fetchall()

    for row in rows:

        print(
            f"\nPatient ID       : {row[0]}"
        )

        print(
            f"Name             : {row[1]} {row[2]}"
        )

        print(
            f"Payer            : {row[3]}"
        )

        print(
            f"Insurance Active : {row[4]}"
        )

        print(
            f"Conditions       : {row[5]}"
        )

        print(
            f"Procedures       : {row[6]}"
        )

        print(
            f"Careplans        : {row[7]}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")

    print("=" * 75)

    print(
        " SYNTHEA -> PRIOR AUTHORIZATION PATIENT DATABASE LOADER"
    )

    print("=" * 75)

    print(
        "\nCSV source directory:"
    )

    print(
        CSV_DIR
    )

    conn = None
    cursor = None

    try:

        # ----------------------------------------------------
        # 1. Check files
        # ----------------------------------------------------

        check_csv_files()

        # ----------------------------------------------------
        # 2. Read source CSVs
        # ----------------------------------------------------

        (
            patients,
            conditions,
            procedures,
            careplans,
            payer_transitions,
            payers
        ) = load_source_data()

        # ----------------------------------------------------
        # 3. Select recent 100 patients
        # ----------------------------------------------------

        (
            selected_patients,
            selected_ids
        ) = select_patients(
            patients,
            conditions,
            procedures,
            careplans
        )

        # ----------------------------------------------------
        # 4. Connect MySQL
        # ----------------------------------------------------

        conn = get_connection()

        cursor = conn.cursor()

        # ----------------------------------------------------
        # 5. Reset old data
        # ----------------------------------------------------

        reset_database(
            conn
        )

        # ----------------------------------------------------
        # 6. Insert patients
        # ----------------------------------------------------

        insert_patients(
            cursor,
            selected_patients
        )

        # ----------------------------------------------------
        # 7. Insert conditions
        # ----------------------------------------------------

        insert_conditions(
            cursor,
            conditions,
            selected_ids
        )

        # ----------------------------------------------------
        # 8. Insert procedures
        # ----------------------------------------------------

        insert_procedures(
            cursor,
            procedures,
            selected_ids
        )

        # ----------------------------------------------------
        # 9. Insert careplans
        # ----------------------------------------------------

        insert_careplans(
            cursor,
            careplans,
            selected_ids
        )

        # ----------------------------------------------------
        # 10. Insert insurance
        # ----------------------------------------------------

        insert_patient_plans(
            cursor,
            payer_transitions,
            payers,
            selected_ids
        )

        # ----------------------------------------------------
        # 11. Commit
        # ----------------------------------------------------

        print("\n")
        print("=" * 75)
        print("COMMITTING DATABASE TRANSACTION")
        print("=" * 75)

        conn.commit()

        print(
            "Transaction committed successfully."
        )

        # ----------------------------------------------------
        # 12. Verify
        # ----------------------------------------------------

        verify_database(
            cursor
        )

        # ----------------------------------------------------
        # 13. Show test patients
        # ----------------------------------------------------

        show_test_patients(
            cursor
        )

        # ----------------------------------------------------
        # 14. Show clinical examples
        # ----------------------------------------------------

        show_clinical_examples(
            cursor
        )

        # ----------------------------------------------------
        # 15. Summary
        # ----------------------------------------------------

        show_patient_summary(
            cursor
        )

        print("\n")
        print("=" * 75)
        print("PATIENT DATABASE LOAD COMPLETED SUCCESSFULLY")
        print("=" * 75)

    except Exception as e:

        if conn:

            conn.rollback()

        print("\n")
        print("=" * 75)
        print("ERROR - TRANSACTION ROLLED BACK")
        print("=" * 75)

        print(
            str(e)
        )

        raise

    finally:

        if cursor:

            cursor.close()

        if conn:

            conn.close()

        print(
            "\nMySQL connection closed."
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()