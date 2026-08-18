import os
import sys
import logging
from datetime import datetime
import pandas as pd
import joblib

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODELS_DIR, "approval_predictor.joblib")

_CACHED_MODEL_ARTIFACT = None
_CACHED_MTIME = 0

def _get_model_artifact():
    global _CACHED_MODEL_ARTIFACT, _CACHED_MTIME
    try:
        if not os.path.exists(MODEL_PATH):
            return None
        mtime = os.path.getmtime(MODEL_PATH)
        if _CACHED_MODEL_ARTIFACT is None or mtime > _CACHED_MTIME:
            _CACHED_MODEL_ARTIFACT = joblib.load(MODEL_PATH)
            _CACHED_MTIME = mtime
        return _CACHED_MODEL_ARTIFACT
    except Exception as e:
        logger.warning(f"Failed to load ML model artifact from {MODEL_PATH}: {e}")
        return None

def calculate_age(birthdate_str):
    if not birthdate_str:
        return 50
    try:
        b_date = datetime.strptime(str(birthdate_str)[:10], "%Y-%m-%d")
        today = datetime.now()
        return today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
    except Exception:
        return 50

def predict_approval_prob(request_data: dict) -> dict:
    """
    Predicts historical approval probability for a prior authorization request.
    This function is informational only and NEVER alters deterministic PA decisions.
    """
    artifact = _get_model_artifact()
    if not artifact or "pipeline" not in artifact:
        return {
            "predicted_approval_prob": None,
            "model_available": False,
            "is_synthetic_model": False,
            "reason": "Model artifact not found or invalid"
        }
    
    try:
        pipeline = artifact["pipeline"]
        metadata = artifact.get("metadata", {})
        
        birthdate = request_data.get("birthdate")
        patient_age = request_data.get("patient_age")
        if patient_age is None:
            patient_age = calculate_age(birthdate)
            
        rationale = request_data.get("clinical_rationale") or request_data.get("provider_rationale") or ""
        rationale_length = len(rationale)
        
        feature_dict = {
            "patient_age": [int(patient_age)],
            "gender": [str(request_data.get("gender") or "U")],
            "state": [str(request_data.get("state") or "Unknown")],
            "requested_hcpcs": [str(request_data.get("requested_hcpcs") or "Unknown")],
            "diagnosis_icd10": [str(request_data.get("diagnosis_icd10") or "Unknown")],
            "payer_name": [str(request_data.get("payer_name") or request_data.get("plan_payer_name") or "Unknown")],
            "urgency": [str(request_data.get("urgency") or "LOW")],
            "rationale_length": [int(rationale_length)]
        }
        
        input_df = pd.DataFrame(feature_dict)
        
        # Predict probability of class 1 (Approval)
        proba_array = pipeline.predict_proba(input_df)
        approval_prob = float(proba_array[0, 1])
        
        # Round to 4 decimal places (between 0.0000 and 1.0000)
        approval_prob = round(max(0.0, min(1.0, approval_prob)), 4)
        
        return {
            "predicted_approval_prob": approval_prob,
            "model_version": metadata.get("model_version", "v1.0-rf"),
            "model_available": True,
            "is_synthetic_model": bool(metadata.get("is_synthetic_model", True))
        }
    except Exception as e:
        logger.error(f"Error during ML prediction: {e}")
        return {
            "predicted_approval_prob": None,
            "model_available": False,
            "is_synthetic_model": False,
            "reason": f"Prediction error: {str(e)}"
        }
