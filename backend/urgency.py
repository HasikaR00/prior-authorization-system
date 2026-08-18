def compute_urgency(encounter_class: str, decision_status: str, prior_utilization_count: int, diagnosis_icd10: str = "") -> str:
    """
    Real-World Clinical Prior Authorization Urgency Criteria:
    - CRITICAL (Urgent/Emergency): Immediate life/limb threat or Emergency Dept encounter, 
      or acute severe neuro/vascular diagnoses (e.g. stroke, hemorrhage, trauma starting with I60-I63, S06).
    - HIGH (Expedited): Time-sensitive diagnostic gap, non-covered initial diagnosis requiring expedited appeal,
      or inpatient encounter class.
    - MEDIUM (Standard Expedited): Patient with prior clinical utilization history (>0 prior procedures/therapies).
    - LOW (Elective/Routine): Ambulatory/outpatient elective request with no prior utilization history.
    """
    icd_prefix = diagnosis_icd10.strip().upper()[:3] if diagnosis_icd10 else ""
    critical_icd_prefixes = {"I60", "I61", "I62", "I63", "S06", "R57", "G45"}

    if encounter_class == "emergency" or icd_prefix in critical_icd_prefixes:
        return "CRITICAL"
    if decision_status in ["NONCOVERED_DIAGNOSIS", "INFO_REQUESTED"] or encounter_class == "inpatient":
        return "HIGH"
    if prior_utilization_count > 0:
        return "MEDIUM"
    return "LOW"
