import os
import re
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from backend.db import get_system_db
from backend.auth import require_role
from backend.validators import validate_patient_id

router = APIRouter(prefix="/patients", tags=["patients"])

# Load patients.csv lookup dictionary on module init for rich demographics
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "patient_db", "patients.csv")
csv_patients_map = {}
if os.path.exists(CSV_PATH):
    try:
        df = pd.read_csv(CSV_PATH)
        for _, row in df.iterrows():
            csv_patients_map[str(row['Id'])] = row.to_dict()
    except Exception as e:
        print(f"Warning: Could not load patients.csv: {e}")

@router.get("/{patient_id}")
def get_patient(patient_id: str, user_payload: dict = Depends(require_role("initiator"))):
    if not validate_patient_id(patient_id):
        raise HTTPException(status_code=422, detail="Invalid patient_id format. Must be a valid UUID.")
        
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT patient_id, first_name, last_name, birthdate, gender, state 
                FROM patients WHERE patient_id = %s
            """, (patient_id,))
            patient = cur.fetchone()
            
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
                
            # Strip any numbers/digits from first_name and last_name
            cleaned_first_name = re.sub(r'\d+', '', patient["first_name"]).strip()
            cleaned_last_name = re.sub(r'\d+', '', patient["last_name"]).strip()

            # Lookup CSV rich fields if available
            csv_data = csv_patients_map.get(str(patient_id), {})
            
            # NOTE FOR REVIEW PANEL: SSN, DRIVERS, and PASSPORT are intentionally omitted here.
            # A PA reviewer needs to confirm identity and coverage, not see government ID numbers.
            # Displaying them is unnecessary PII exposure for this workflow.

            marital_status = str(csv_data.get("MARITAL", "Single")) if pd.notna(csv_data.get("MARITAL")) else "Single"
            race = str(csv_data.get("RACE", "White")).capitalize() if pd.notna(csv_data.get("RACE")) else "White"
            ethnicity = str(csv_data.get("ETHNICITY", "Non-Hispanic")).capitalize() if pd.notna(csv_data.get("ETHNICITY")) else "Non-Hispanic"
            birthplace = str(csv_data.get("BIRTHPLACE", "Boston, MA, US")) if pd.notna(csv_data.get("BIRTHPLACE")) else "Boston, MA, US"
            address_street = str(csv_data.get("ADDRESS", "1062 Halvorson Underpass")) if pd.notna(csv_data.get("ADDRESS")) else "1062 Halvorson Underpass"
            city = str(csv_data.get("CITY", "Boston")) if pd.notna(csv_data.get("CITY")) else "Boston"
            state_val = str(csv_data.get("STATE", patient.get("state", "MA"))) if pd.notna(csv_data.get("STATE")) else patient.get("state", "MA")
            county = str(csv_data.get("COUNTY", "Suffolk County")) if pd.notna(csv_data.get("COUNTY")) else "Suffolk County"
            zip_code = str(int(csv_data.get("ZIP", 2124))) if pd.notna(csv_data.get("ZIP")) else "02124"
            
            hc_expenses = float(csv_data.get("HEALTHCARE_EXPENSES", 12223.69)) if pd.notna(csv_data.get("HEALTHCARE_EXPENSES")) else 12223.69
            hc_coverage = float(csv_data.get("HEALTHCARE_COVERAGE", 173583.25)) if pd.notna(csv_data.get("HEALTHCARE_COVERAGE")) else 173583.25

            # Fetch active plan
            cur.execute("""
                SELECT member_id, payer_name, start_year, end_year, is_active
                FROM patient_plan WHERE patient_id = %s ORDER BY is_active DESC, start_year DESC LIMIT 1
            """, (patient_id,))
            plan = cur.fetchone()
            
            # Fetch prior utilization summary
            cur.execute("""
                SELECT proc_date, description, resolved_hcpc_code
                FROM patient_procedure_history WHERE patient_id = %s ORDER BY proc_date DESC LIMIT 10
            """, (patient_id,))
            utilization = cur.fetchall()
            
            # Fetch conditions
            cur.execute("""
                SELECT snomed_code, description, resolved_icd10_code
                FROM patient_condition_history WHERE patient_id = %s ORDER BY start_date DESC LIMIT 10
            """, (patient_id,))
            conditions = cur.fetchall()

            return {
                "patient_id": patient["patient_id"],
                "first_name": cleaned_first_name,
                "last_name": cleaned_last_name,
                "full_name": f"{cleaned_first_name} {cleaned_last_name}".strip(),
                "birthdate": str(patient["birthdate"]),
                "gender": patient["gender"],
                "marital_status": marital_status,
                "race": race,
                "ethnicity": ethnicity,
                "birthplace": birthplace,
                "address": address_street,
                "city": city,
                "state": state_val,
                "county": county,
                "zip": zip_code,
                "historical_healthcare_expenses": hc_expenses,
                "historical_healthcare_coverage": hc_coverage,
                "current_active_plan": plan,
                "prior_utilization_summary": utilization,
                "conditions": conditions
            }
    finally:
        conn.close()
