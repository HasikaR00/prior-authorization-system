import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from backend.db import get_system_db
from backend.auth import require_role
from backend.decision_engine import simplify_description
from backend.ml_predictor import predict_approval_prob

router = APIRouter(tags=["review"])

class InsurerConfirmRequest(BaseModel):
    final_status: str
    note: Optional[str] = ""

@router.get("/review-queue")
def get_review_queue(user_payload: dict = Depends(require_role("insurer"))):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            # Retrieve all PA requests for Insurer review & confirmation tracking
            cur.execute("""
                SELECT 
                    r.request_id,
                    r.patient_id,
                    r.requested_hcpcs,
                    r.diagnosis_icd10,
                    r.status AS system_suggestion,
                    r.insurer_final_status,
                    r.insurer_confirmed_by,
                    r.insurer_confirmed_at,
                    COALESCE(r.urgency, 'LOW') AS urgency,
                    r.submitted_at,
                    r.ordering_provider AS ordering_physician,
                    r.payer_name,
                    r.clinical_rationale,
                    p.first_name,
                    p.last_name,
                    p.birthdate,
                    p.gender,
                    p.state
                FROM pa_request r
                LEFT JOIN patients p ON r.patient_id = p.patient_id
                ORDER BY 
                    FIELD(COALESCE(r.urgency, 'LOW'), 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'),
                    r.submitted_at DESC
            """)
            queue = cur.fetchall()

            for item in queue:
                final_stat = item.get("insurer_final_status")
                item["display_status"] = final_stat if final_stat else "AWAITING_REVIEW"

                # Attach descriptions
                cur.execute("SELECT long_description, short_description FROM article_hcpc WHERE hcpc_code = %s LIMIT 1", (item["requested_hcpcs"],))
                h_row = cur.fetchone()
                raw_h = (h_row.get("long_description") or h_row.get("short_description") or "") if h_row else ""
                item["hcpc_description"] = simplify_description(raw_h) if raw_h else f"Procedure {item['requested_hcpcs']}"

                cur.execute("SELECT description FROM article_icd10_covered WHERE icd10_code = %s LIMIT 1", (item["diagnosis_icd10"],))
                i_row = cur.fetchone()
                raw_i = (i_row.get("description") or "") if i_row else ""
                item["icd10_description"] = simplify_description(raw_i) if raw_i else f"Diagnosis {item['diagnosis_icd10']}"

                # Secondary ML Triage Signal
                ml_res = predict_approval_prob(item)
                item["predicted_approval_prob"] = ml_res.get("predicted_approval_prob")
                item["ml_model_available"] = ml_res.get("model_available", False)
                item["ml_model_version"] = ml_res.get("model_version")
                item["is_synthetic_model"] = ml_res.get("is_synthetic_model", True)

            return queue
    finally:
        conn.close()

@router.post("/requests/{request_id}/confirm")
def confirm_request(
    request_id: str,
    body: InsurerConfirmRequest,
    user_payload: dict = Depends(require_role("insurer"))
):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pa_request WHERE request_id = %s", (request_id,))
            req_row = cur.fetchone()
            if not req_row:
                raise HTTPException(status_code=404, detail="Request not found")
                
            engine_status = req_row["status"]
            
            # If final_status differs from engine's original status, note is REQUIRED
            if body.final_status != engine_status and (not body.note or not body.note.strip()):
                raise HTTPException(
                    status_code=400, 
                    detail="Override note is mandatory when changing decision from engine status"
                )
                
            confirmed_by = user_payload["user_id"]
            confirmed_at = datetime.now()
            
            # Update pa_request confirmation fields
            cur.execute("""
                UPDATE pa_request
                SET insurer_confirmed_by = %s,
                    insurer_confirmed_at = %s,
                    insurer_final_status = %s,
                    insurer_override_note = %s
                WHERE request_id = %s
            """, (confirmed_by, confirmed_at, body.final_status, body.note, request_id))
            
            # Insert new row into pa_decision_log (never overwrite engine's log)
            reason_type = f"INSURER_CONFIRMED_{body.final_status}"
            if body.final_status != engine_status:
                reason_type = f"INSURER_OVERRIDE_{body.final_status}"
                
            cur.execute("""
                INSERT INTO pa_decision_log (
                    request_id, rule_source, matched_result, reason_type, reasoning_text, decided_by, decided_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (request_id, "insurer_override", body.final_status, reason_type, body.note or "Insurer confirmed engine decision", confirmed_by, confirmed_at))
            
            return {
                "message": "Decision confirmed successfully",
                "request_id": request_id,
                "insurer_final_status": body.final_status,
                "insurer_confirmed_by": confirmed_by
            }
    finally:
        conn.close()
