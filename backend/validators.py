import re

def validate_hcpcs(code: str) -> bool:
    return bool(re.match(r'^[A-Z0-9]{5}$', code))

def validate_icd10(code: str) -> bool:
    return bool(re.match(r'^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$', code))

def validate_patient_id(pid: str) -> bool:
    return bool(re.match(r'^[a-f0-9\-]{36}$', pid))
