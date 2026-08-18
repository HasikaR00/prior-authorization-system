import time
import re
import pymysql
import pymysql.cursors
from backend.decision_engine import DecisionEngine

CREATE_EVAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eval_run_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id VARCHAR(64),
    status VARCHAR(32),
    reason_type VARCHAR(64),
    llm_provider_used VARCHAR(32),
    engine_time_ms INT,
    llm_time_ms INT,
    total_time_ms INT,
    contradiction_detected BOOLEAN DEFAULT FALSE,
    run_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

BANNED_PHRASES_REGEX = re.compile(
    r"\b(has been approved|is approved|has been denied|is denied)\b",
    re.IGNORECASE
)

class EvaluatedDecisionEngine(DecisionEngine):
    """
    Non-invasive evaluation wrapper around DecisionEngine.
    Observes timing, provider usage, and contradiction flags without altering decision logic or return structures.
    """
    def __init__(self, db_config):
        super().__init__(db_config)
        self._ensure_eval_table()

    def _ensure_eval_table(self):
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                cur.execute(CREATE_EVAL_TABLE_SQL)
            conn.close()
        except Exception as e:
            print(f"[EVAL LOGGER] Table creation check warning: {e}")

    def evaluate(
        self,
        patient_id,
        requested_hcpcs,
        diagnosis_icd10,
        ordering_physician,
        signed_order_date,
        provider_rationale=None
    ):
        start_total = time.perf_counter()
        
        # Track timing inside decision_engine by wrapping internal calls or observing timestamps
        # We call original evaluate, measuring total execution
        t0 = time.perf_counter()
        result = super().evaluate(
            patient_id=patient_id,
            requested_hcpcs=requested_hcpcs,
            diagnosis_icd10=diagnosis_icd10,
            ordering_physician=ordering_physician,
            signed_order_date=signed_order_date,
            provider_rationale=provider_rationale
        )
        total_time_ms = int((time.perf_counter() - t0) * 1000)

        # Non-invasively parse outputs for evaluation metrics
        try:
            request_id = result.get("request_id", "")
            status = result.get("status", "")
            reason_type = result.get("reason_type", "")

            llm_exp = result.get("llm_explanation") or {}
            provider_used = "UNKNOWN"
            if isinstance(llm_exp, dict):
                provider_used = llm_exp.get("_provider", "UNKNOWN")

            # Check contradiction regex against all string fields in llm_explanation
            contradiction_detected = False
            if isinstance(llm_exp, dict):
                combined_text = " ".join([
                    str(v) for k, v in llm_exp.items() if isinstance(v, (str, list))
                ])
                if BANNED_PHRASES_REGEX.search(combined_text):
                    contradiction_detected = True

            # Estimate engine vs llm time breakdown (default approximation if internal timers not exposed)
            engine_time_ms = int(total_time_ms * 0.15) if total_time_ms > 0 else 0
            llm_time_ms = max(0, total_time_ms - engine_time_ms)

            # Log metric row to database
            self._log_eval_run(
                request_id=request_id,
                status=status,
                reason_type=reason_type,
                llm_provider_used=provider_used,
                engine_time_ms=engine_time_ms,
                llm_time_ms=llm_time_ms,
                total_time_ms=total_time_ms,
                contradiction_detected=contradiction_detected
            )
        except Exception as e:
            # Logger failures must NEVER break the core evaluate return value
            print(f"[EVAL LOGGER] Failed to record metrics: {e}")

        return result

    def _log_eval_run(
        self,
        request_id,
        status,
        reason_type,
        llm_provider_used,
        engine_time_ms,
        llm_time_ms,
        total_time_ms,
        contradiction_detected
    ):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO eval_run_log
                    (request_id, status, reason_type, llm_provider_used, engine_time_ms, llm_time_ms, total_time_ms, contradiction_detected)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        status,
                        reason_type,
                        str(llm_provider_used)[:32] if llm_provider_used else "UNKNOWN",
                        engine_time_ms,
                        llm_time_ms,
                        total_time_ms,
                        contradiction_detected
                    )
                )
        finally:
            conn.close()
