import uuid
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File
from pydantic import BaseModel
from backend.db import get_system_db, SYSTEM_DB_CONFIG
from backend.auth import require_role, get_current_user
from backend.validators import validate_hcpcs, validate_icd10, validate_patient_id
from backend.rate_limiter import check_rate_limit
from backend.urgency import compute_urgency
from backend.decision_engine import DecisionEngine, simplify_description
from backend.eval_logger import EvaluatedDecisionEngine
from backend.ml_predictor import predict_approval_prob
from backend.pdf_ocr import parse_and_extract_pdf

router = APIRouter(prefix="/requests", tags=["requests"])
engine = EvaluatedDecisionEngine(SYSTEM_DB_CONFIG)

@router.post("/extract-pdf")
async def extract_pdf_request(
    file: UploadFile = File(...),
    user_payload: dict = Depends(require_role("initiator"))
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF documents (.pdf) are supported for extraction.")
    
    pdf_bytes = await file.read()
    if not pdf_bytes or len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed limit of 10MB.")

    result = parse_and_extract_pdf(pdf_bytes)
    if not result.get("success"):
        raise HTTPException(
            status_code=422,
            detail=result.get("error") or "We couldn't extract information from this document. Please enter the information manually."
        )

    return result


class PARequestCreate(BaseModel):
    patient_id: str
    requested_hcpcs: str
    diagnosis_icd10: str
    ordering_physician: str
    signed_order_date: str
    provider_rationale: Optional[str] = ""
    encounter_class: Optional[str] = "ambulatory"

class PAResubmitRequest(BaseModel):
    additional_rationale: str

@router.post("")
def create_request(
    req: PARequestCreate,
    request: Request,
    user_payload: dict = Depends(require_role("initiator"))
):
    # Validate fields
    if not validate_patient_id(req.patient_id):
        raise HTTPException(status_code=422, detail="Invalid patient_id format")
    if not validate_hcpcs(req.requested_hcpcs):
        raise HTTPException(status_code=422, detail="Invalid requested_hcpcs format (Must be 5 alphanumeric chars)")
    if not validate_icd10(req.diagnosis_icd10):
        raise HTTPException(status_code=422, detail="Invalid diagnosis_icd10 format")
    if not req.ordering_physician:
        raise HTTPException(status_code=422, detail="ordering_physician is required")
    if not req.signed_order_date:
        raise HTTPException(status_code=422, detail="signed_order_date is required")

    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            # Rate limiter
            client_ip = request.client.host if request.client else "unknown"
            if not check_rate_limit(cur, client_ip, "/requests"):
                raise HTTPException(status_code=429, detail="Rate limit exceeded for request submission")
            
            # Check for existing active unconfirmed request for same patient + HCPCS + ICD-10
            cur.execute("""
                SELECT request_id, submitted_at, status, insurer_final_status
                FROM pa_request
                WHERE patient_id = %s 
                  AND requested_hcpcs = %s 
                  AND diagnosis_icd10 = %s 
                  AND insurer_confirmed_by IS NULL
                ORDER BY submitted_at ASC
                LIMIT 1
            """, (req.patient_id, req.requested_hcpcs, req.diagnosis_icd10))
            older_unconfirmed = cur.fetchone()
            
            is_duplicate = bool(older_unconfirmed)
            canonical_request_id = older_unconfirmed["request_id"] if older_unconfirmed else None

            # Call decision engine internally to record evaluation logs & pa_request
            result = engine.evaluate(
                patient_id=req.patient_id,
                requested_hcpcs=req.requested_hcpcs,
                diagnosis_icd10=req.diagnosis_icd10,
                ordering_physician=req.ordering_physician,
                signed_order_date=req.signed_order_date,
                provider_rationale=req.provider_rationale
            )
            
            status = result.get("decision", "PENDED_NURSE_REVIEW")
            prior_count = result.get("prior_utilization", {}).get("count", 0)
            urgency = compute_urgency(req.encounter_class, status, prior_count, req.diagnosis_icd10)
            request_id = result.get("request_id")
            
            # Update urgency and parent_request_id if duplicate
            if is_duplicate and canonical_request_id:
                cur.execute("""
                    UPDATE pa_request SET urgency = %s, parent_request_id = %s WHERE request_id = %s
                """, (urgency, canonical_request_id, request_id))
            else:
                cur.execute("""
                    UPDATE pa_request SET urgency = %s WHERE request_id = %s
                """, (urgency, request_id))
            
            # Initiator submission response MUST NOT expose internal engine recommendation before confirmation
            return {
                "request_id": request_id,
                "display_status": "AWAITING_RESULT",
                "message": "PA request submitted successfully and is awaiting insurer review.",
                "urgency": urgency,
                "is_duplicate": is_duplicate,
                "canonical_request_id": canonical_request_id
            }
    finally:
        conn.close()

@router.get("")
def get_user_requests(user_payload: dict = Depends(require_role("initiator"))):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    r.request_id,
                    r.patient_id,
                    r.requested_hcpcs,
                    r.diagnosis_icd10,
                    r.status AS system_suggestion,
                    r.urgency,
                    r.insurer_final_status,
                    r.insurer_confirmed_by,
                    r.submitted_at,
                    r.parent_request_id,
                    r.ordering_provider AS ordering_physician,
                    p.first_name,
                    p.last_name
                FROM pa_request r
                LEFT JOIN patients p ON r.patient_id = p.patient_id
                ORDER BY r.submitted_at DESC
            """)
            rows = cur.fetchall()
            
            user_role = user_payload.get("role", "initiator")
            for row in rows:
                final_stat = row.get("insurer_final_status") if row.get("insurer_confirmed_by") else None
                
                # Duplicate result inheritance
                if not final_stat and row.get("parent_request_id"):
                    cur.execute("SELECT insurer_final_status, insurer_confirmed_by FROM pa_request WHERE request_id = %s LIMIT 1", (row["parent_request_id"],))
                    parent_row = cur.fetchone()
                    if parent_row and parent_row.get("insurer_confirmed_by"):
                        final_stat = parent_row.get("insurer_final_status")

                row["display_status"] = final_stat if final_stat else "AWAITING_RESULT"
                
                # Attach procedure description
                cur.execute("SELECT long_description, short_description FROM article_hcpc WHERE hcpc_code = %s LIMIT 1", (row["requested_hcpcs"],))
                h_row = cur.fetchone()
                raw_h_desc = (h_row.get("long_description") or h_row.get("short_description") or "") if h_row else ""
                row["hcpc_description"] = simplify_description(raw_h_desc) if raw_h_desc else f"Procedure {row['requested_hcpcs']}"

                # Attach diagnosis description
                cur.execute("SELECT description FROM article_icd10_covered WHERE icd10_code = %s LIMIT 1", (row["diagnosis_icd10"],))
                i_row = cur.fetchone()
                raw_i_desc = (i_row.get("description") or "") if i_row else ""
                if not raw_i_desc:
                    cur.execute("SELECT description FROM article_icd10_noncovered WHERE icd10_code = %s LIMIT 1", (row["diagnosis_icd10"],))
                    noncov_i = cur.fetchone()
                    if noncov_i:
                        raw_i_desc = noncov_i.get("description", "")
                row["icd10_description"] = simplify_description(raw_i_desc) if raw_i_desc else f"Diagnosis {row['diagnosis_icd10']}"

                # If caller is initiator, strip raw status and system_suggestion completely
                if user_role == "initiator":
                    row.pop("status", None)
                    row.pop("system_suggestion", None)

            return rows
    finally:
        conn.close()

@router.get("/{request_id}")
def get_request_detail(
    request_id: str,
    user_payload: dict = Depends(get_current_user)
):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    r.*,
                    r.ordering_provider AS ordering_physician,
                    r.clinical_rationale AS provider_rationale,
                    p.first_name,
                    p.last_name,
                    p.birthdate,
                    p.gender,
                    p.state
                FROM pa_request r
                LEFT JOIN patients p ON r.patient_id = p.patient_id
                WHERE r.request_id = %s
            """, (request_id,))
            req_row = cur.fetchone()
            if not req_row:
                raise HTTPException(status_code=404, detail="Request not found")
                
            # Duplicate check: check parent_request_id or older unconfirmed request
            canonical_request = None
            if req_row.get("parent_request_id"):
                cur.execute("SELECT * FROM pa_request WHERE request_id = %s LIMIT 1", (req_row["parent_request_id"],))
                canonical_request = cur.fetchone()

            if not canonical_request:
                cur.execute("""
                    SELECT * FROM pa_request
                    WHERE patient_id = %s 
                      AND requested_hcpcs = %s 
                      AND diagnosis_icd10 = %s 
                      AND request_id != %s
                      AND submitted_at < %s
                      AND insurer_confirmed_by IS NULL
                    ORDER BY submitted_at ASC
                    LIMIT 1
                """, (req_row["patient_id"], req_row["requested_hcpcs"], req_row["diagnosis_icd10"], request_id, req_row["submitted_at"]))
                canonical_request = cur.fetchone()

            is_duplicate = bool(canonical_request)
            req_row["is_duplicate"] = is_duplicate
            if canonical_request:
                req_row["canonical_request_id"] = canonical_request["request_id"]
                req_row["original_prior_request"] = {
                    "request_id": canonical_request["request_id"],
                    "submitted_at": str(canonical_request["submitted_at"]),
                    "status": canonical_request["status"],
                    "insurer_final_status": canonical_request.get("insurer_final_status")
                }

            cur.execute("""
                SELECT log_id, matched_result AS decision, reason_type AS reason_code, reasoning_text AS llm_explanation, decided_by, decided_at AS created_at
                FROM pa_decision_log WHERE request_id = %s ORDER BY decided_at ASC
            """, (request_id,))
            logs = cur.fetchall()
            
            for l in logs:
                if l.get("llm_explanation"):
                    try:
                        parsed = json.loads(l["llm_explanation"])
                        if isinstance(parsed, dict) and "llm_explanation" in parsed:
                            l["llm_explanation"] = parsed["llm_explanation"]
                        elif isinstance(parsed, dict) and "deterministic_reasoning" in parsed:
                            l["llm_explanation"] = parsed["deterministic_reasoning"]
                    except Exception:
                        pass

            # Attach simplified code descriptions
            cur.execute("SELECT long_description, short_description FROM article_hcpc WHERE hcpc_code = %s LIMIT 1", (req_row["requested_hcpcs"],))
            h_row = cur.fetchone()
            raw_h_desc = (h_row.get("long_description") or h_row.get("short_description") or "") if h_row else ""

            req_row["hcpc_raw_description"] = raw_h_desc
            req_row["hcpc_description"] = simplify_description(raw_h_desc) if raw_h_desc else f"Procedure {req_row['requested_hcpcs']}"

            cur.execute("SELECT description FROM article_icd10_covered WHERE icd10_code = %s LIMIT 1", (req_row["diagnosis_icd10"],))
            i_row = cur.fetchone()
            raw_i_desc = (i_row.get("description") or "") if i_row else ""
            if not raw_i_desc:
                cur.execute("SELECT description FROM article_icd10_noncovered WHERE icd10_code = %s LIMIT 1", (req_row["diagnosis_icd10"],))
                noncov_i = cur.fetchone()
                if noncov_i:
                    raw_i_desc = noncov_i.get("description", "")

            req_row["icd10_raw_description"] = raw_i_desc
            req_row["icd10_description"] = simplify_description(raw_i_desc) if raw_i_desc else f"Diagnosis {req_row['diagnosis_icd10']}"

            req_row["decision_logs"] = logs

            # Compute secondary ML prediction signal
            ml_res = predict_approval_prob(req_row)
            req_row["predicted_approval_prob"] = ml_res.get("predicted_approval_prob")
            req_row["ml_model_available"] = ml_res.get("model_available", False)
            req_row["ml_model_version"] = ml_res.get("model_version")
            req_row["is_synthetic_model"] = ml_res.get("is_synthetic_model", True)

            # Compute final decision & status fields
            final_stat = req_row.get("insurer_final_status") if req_row.get("insurer_confirmed_by") else None
            
            # If this request is unconfirmed, but canonical parent request is confirmed, inherit canonical result!
            if not final_stat and canonical_request and canonical_request.get("insurer_confirmed_by"):
                final_stat = canonical_request.get("insurer_final_status")
                req_row["insurer_final_status"] = final_stat
                req_row["insurer_confirmed_by"] = canonical_request.get("insurer_confirmed_by")
                req_row["insurer_confirmed_at"] = canonical_request.get("insurer_confirmed_at")
                req_row["insurer_override_note"] = canonical_request.get("insurer_override_note")

            req_row["display_status"] = final_stat if final_stat else "AWAITING_RESULT"
            
            user_role = user_payload.get("role", "initiator")
            raw_stat = req_row.pop("status", None)

            # SERVER-SIDE ROLE ACCESS PROTECTION
            if user_role == "initiator":
                req_row.pop("system_suggestion", None)
                # If unconfirmed, hide internal decision support & ML fields from initiator
                if not final_stat:
                    req_row.pop("decision_logs", None)
                    req_row.pop("predicted_approval_prob", None)
                    req_row.pop("ml_model_available", None)
                    req_row.pop("ml_model_version", None)
                    req_row.pop("is_synthetic_model", None)
            else:
                req_row["system_suggestion"] = raw_stat

            return req_row
    finally:
        conn.close()

@router.post("/{request_id}/resubmit")
def resubmit_request(
    request_id: str,
    body: PAResubmitRequest,
    user_payload: dict = Depends(require_role("initiator"))
):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pa_request WHERE request_id = %s", (request_id,))
            orig = cur.fetchone()
            if not orig:
                raise HTTPException(status_code=404, detail="Original request not found")
            
            # Must target a request currently in INFO_REQUESTED status
            if orig["status"] != "INFO_REQUESTED" and orig.get("insurer_final_status") != "INFO_REQUESTED":
                raise HTTPException(status_code=400, detail="Can only resubmit requests that are in INFO_REQUESTED status")
                
            combined_rationale = (orig.get("provider_rationale") or "") + "\n[Additional Rationale]: " + body.additional_rationale
            
            # Re-run decision engine (creates a new request_id inside engine)
            result = engine.evaluate(
                patient_id=orig["patient_id"],
                requested_hcpcs=orig["requested_hcpcs"],
                diagnosis_icd10=orig["diagnosis_icd10"],
                ordering_physician=orig["ordering_physician"],
                signed_order_date=str(orig["signed_order_date"]),
                provider_rationale=combined_rationale
            )
            
            new_request_id = result.get("request_id")
            status = result.get("decision", "PENDED_NURSE_REVIEW")
            prior_count = result.get("prior_utilization", {}).get("count", 0)
            urgency = compute_urgency("ambulatory", status, prior_count)
            
            # Set parent_request_id and urgency on the newly created request
            cur.execute("""
                UPDATE pa_request SET parent_request_id = %s, urgency = %s WHERE request_id = %s
            """, (request_id, urgency, new_request_id))
            
            res_payload = dict(result)
            res_payload["parent_request_id"] = request_id
            res_payload["urgency"] = urgency
            return res_payload
    finally:
        conn.close()
