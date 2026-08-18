"""
============================================================
PRIOR AUTHORIZATION DECISION ENGINE
============================================================

ARCHITECTURE
------------

                PA REQUEST
                    |
                    v
                MYSQL
                    |
                    v
          DETERMINISTIC ENGINE
                    |
                    v
          DETERMINISTIC RESULT
                    |
                    v
          POLICY / PATIENT EVIDENCE
                    |
                    v
              LLM EXPLANATION
                    |
          +---------+---------+
          |         |         |
          v         v         v
       OpenAI    Gemini     Groq
          |         |         |
          +---------+---------+
                    |
                    v
          LOCAL JSON VALIDATION
                    |
                    v
            FINAL PA RESPONSE

IMPORTANT
---------

LLM NEVER determines:

    APPROVED
    PENDED_NURSE_REVIEW
    INFO_REQUESTED
    NOT_REQUIRED
    RETRACTED

The deterministic MySQL decision is authoritative.

The LLM only explains the result.
"""

import os
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import pymysql
import pymysql.cursors

from dotenv import load_dotenv


# ============================================================
# OPTIONAL LLM SDKs
# ============================================================

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


# ============================================================
# DECISION CONSTANTS
# ============================================================

APPROVED = "APPROVED"
PENDED = "PENDED_NURSE_REVIEW"
INFO = "INFO_REQUESTED"
NOT_REQUIRED = "NOT_REQUIRED"
RETRACTED = "RETRACTED"

VALID_DECISIONS = {
    APPROVED,
    PENDED,
    INFO,
    NOT_REQUIRED,
    RETRACTED
}


# ============================================================
# MODEL CONFIGURATION
# ============================================================

PRIMARY_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5"
)

# Use a currently available Gemini model.
# Change this in .env if needed.
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.3-70b-versatile"
)

GROQ_MODEL_FALLBACK = os.getenv(
    "GROQ_MODEL_FALLBACK",
    "llama3-70b-8192"
)


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_CONFIG = {
    "host": os.getenv(
        "DB_HOST",
        "localhost"
    ),

    "port": int(
        os.getenv(
            "DB_PORT",
            "3306"
        )
    ),

    "user": os.getenv(
        "DB_USER"
    ),

    "password": os.getenv(
        "DB_PASSWORD"
    ),

    "database": os.getenv(
        "DB_NAME",
        "pa_system"
    ),

    "charset": "utf8mb4"
}


# ============================================================
# CHROMA
# ============================================================

CHROMA_ENABLED = os.getenv(
    "CHROMA_ENABLED",
    "false"
).lower() == "true"

CHROMA_DIR = os.getenv(
    "CHROMA_DIR",
    ""
)

CHROMA_COLLECTION = os.getenv(
    "CHROMA_COLLECTION",
    "pa_policy_kb"
)

CHROMA_TOP_K = int(
    os.getenv(
        "CHROMA_TOP_K",
        "3"
    )
)


# ============================================================
# JARGON GLOSSARY & SIMPLIFICATION
# ============================================================

JARGON_GLOSSARY = {
    "unspecified": "general / not specified",
    "NOS": "not otherwise specified",
    "NEC": "not elsewhere classified",
    "w/o contrast": "without contrast dye",
    "w/ contrast": "with contrast dye",
    "w/o": "without",
    "w/": "with",
    "bilateral": "on both sides",
    "unilateral": "on one side",
    "intravenous": "into a vein",
    "subcutaneous": "under the skin",
    "intramuscular": "into muscle",
    "arthroscopy": "joint scope procedure",
    "endoscopy": "internal scope inspection",
    "tomography": "detailed imaging scan",
    "radiography": "X-ray imaging",
    "magnetic resonance": "MRI scanning",
    "electrocardiogram": "heart rhythm test",
    "echocardiogram": "heart ultrasound scan"
}

def simplify_description(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = str(raw_text)
    import re
    for term, plain in JARGON_GLOSSARY.items():
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text = pattern.sub(plain, text)
    return text


# ============================================================
# LLM OUTPUT FIELDS
# ============================================================

LLM_REQUIRED_FIELDS = [
    "plain_summary",
    "key_findings",
    "decision_summary",
    "deterministic_decision_basis",
    "policy_evidence",
    "patient_clinical_evidence",
    "evidence_relationship",
    "coverage_interpretation",
    "missing_information",
    "risk_review_flags",
    "human_review_note"
]


# ============================================================
# LLM SYSTEM PROMPT
# ============================================================

LLM_SYSTEM_PROMPT = """
You are an expert healthcare prior authorization clinical review assistant providing clear, objective, executive-ready clinical summaries for payer clinical reviewers.

Writing & Style Guidelines:
- Write in clean, professional, everyday clinical language at an 8th-grade reading level.
- Use bold lead-ins for key points (e.g. "**Coverage Alignment:**", "**Conditionality Evaluation:**", "**Prior Utilization:**").
- NEVER use raw technical code numbers (such as SNOMED numerical codes or internal crosswalk IDs) in the main prose text. Use plain English medical descriptions instead.
- State findings directly based strictly on the supplied data payload.

============================================================
ABSOLUTE LANGUAGE RULES (STRICT NON-DEFINITIVE / NO COMPLETED ACTION)
============================================================

1. You are providing a RECOMMENDATION ONLY. The human reviewer makes the final determination.
2. NEVER use past-tense or completed-action phrasing for a decision that has not been confirmed by a human reviewer.
3. BANNED PHRASES — DO NOT USE ANY OF THE FOLLOWING:
   - "has been approved"
   - "has been denied"
   - "is approved"
   - "is denied"
   - "approved for service"
   - "denied for service"
4. MANDATORY PHRASING TO USE INSTEAD:
   - For positive criteria matches: "is recommended for approval, pending reviewer confirmation"
   - For negative criteria matches: "does not currently meet coverage criteria, pending reviewer confirmation"
   - For missing documentation: "requires additional clinical information before a recommendation can be finalized, pending reviewer confirmation"

============================================================
CONTENT AND STRUCTURE INSTRUCTIONS
============================================================

Your response must follow this exact, non-repetitive single structure where each section adds NEW information:

1. plain_summary (2-3 sentences max):
   - The ONLY place the core conclusion is stated in full.
   - Must explicitly use hedged recommendation phrasing (e.g. "is recommended for approval, pending reviewer confirmation").

2. key_findings (ORDERED EVIDENCE CHAIN - Array of strings):
   - Bullet 1 (Coverage & Conditionality): Must state whether the diagnosis matches an unconditional or conditional covered group.
     * IF unconditional (is_unconditional is True): State: "This diagnosis is covered without additional conditions (Group [N], unconditional match)."
     * IF conditional (is_unconditional is False): State: "This diagnosis is covered subject to the following documented condition: [condition text]. This condition [was / was not] satisfied based on the available patient evidence, because [reason]."
   - Bullet 2 (Clinical Records Alignment): State how patient clinical history and active care plans align with requested care.
   - Bullet 3 (Prior Utilization): MUST explicitly state prior utilization from payload:
     * IF requested_service_count is 0: State: "No prior instances of this service were found in the patient's history."
     * IF requested_service_count > 0: State: "This service was previously performed [N] time(s), most recently on [date]. This was factored into the review."

3. human_review_note:
   - Must add NEW guidance or specific nuance for the reviewer to watch for (e.g., "Verify physical order signature on file" or "Check conservative trial duration").
   - MUST NOT restate the plain_summary a second time.

============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON with these exact fields:

{
  "plain_summary": "A 2-3 sentence executive summary containing the recommendation and primary reason, using hedged phrasing.",
  "key_findings": [
    "**Coverage & Conditionality:** Explicit unconditional/conditional coverage match sentence.",
    "**Clinical Evidence:** Patient condition and record alignment sentence.",
    "**Prior Utilization:** Explicit sentence stating 0 or N prior instances in history."
  ],
  "decision_summary": "A formal clinical recommendation summary for medical reviewers.",
  "deterministic_decision_basis": "Summary of policy rules evaluated.",
  "policy_evidence": ["Key policy rules evaluated"],
  "patient_clinical_evidence": ["Patient history and clinical records evaluated"],
  "evidence_relationship": ["How patient record aligns with coverage policy"],
  "coverage_interpretation": "Direct summary of coverage status under policy guidelines using recommendation phrasing.",
  "missing_information": ["Any missing documents or clinical details"],
  "risk_review_flags": ["Items needing reviewer verification"],
  "human_review_note": "New actionable guidance note for the reviewer taking action."
}

Do not add extra fields.
"""


# ============================================================
# ENGINE
# ============================================================

class DecisionEngine:

    def __init__(self, db_config):

        self.db_config = db_config

        self.openai_client = None
        self.gemini_client = None
        self.groq_client = None

        self.provider_errors = []

        self._initialize_llm_clients()


    # ========================================================
    # INITIALIZE PROVIDERS
    # ========================================================

    def _initialize_llm_clients(self):

        openai_key = os.getenv(
            "OPENAI_API_KEY"
        )

        gemini_key = os.getenv(
            "GEMINI_API_KEY"
        )

        groq_key = os.getenv(
            "GROQ_API_KEY"
        )


        # ----------------------------------------------------
        # OPENAI
        # ----------------------------------------------------

        if openai_key and OpenAI is not None:

            try:

                self.openai_client = OpenAI(
                    api_key=openai_key
                )

            except Exception:

                self.openai_client = None


        # ----------------------------------------------------
        # GEMINI
        # ----------------------------------------------------

        if gemini_key and genai is not None:

            try:

                self.gemini_client = genai.Client(
                    api_key=gemini_key
                )

            except Exception:

                self.gemini_client = None


        # ----------------------------------------------------
        # GROQ
        # ----------------------------------------------------

        if groq_key and Groq is not None:

            try:

                self.groq_client = Groq(
                    api_key=groq_key
                )

            except Exception:

                self.groq_client = None


    # ========================================================
    # DATABASE
    # ========================================================

    def _conn(self):

        return pymysql.connect(
            **self.db_config,
            cursorclass=pymysql.cursors.DictCursor
        )


    # ========================================================
    # PATIENT
    # ========================================================

    def _check_patient(self, cur, patient_id):

        cur.execute(
            """
            SELECT
                patient_id,
                first_name,
                last_name,
                birthdate,
                gender,
                state
            FROM patients
            WHERE patient_id = %s
            """,
            (patient_id,)
        )

        row = cur.fetchone()

        if not row:

            return {
                "found": False,
                "reason": "Patient ID not found",
                "patient": None
            }

        return {
            "found": True,
            "patient": row
        }


    # ========================================================
    # ELIGIBILITY
    # ========================================================

    def _check_eligibility(self, cur, patient_id):

        cur.execute(
            """
            SELECT
                member_id,
                payer_name,
                start_year,
                end_year,
                is_active
            FROM patient_plan
            WHERE patient_id = %s
            ORDER BY
                is_active DESC,
                start_year DESC
            """,
            (patient_id,)
        )

        rows = cur.fetchall()

        if not rows:

            return {
                "eligible": False,
                "reason": "No insurance plan found",
                "plan": None,
                "previous_plans": []
            }


        active_plan = None
        previous_plans = []


        for row in rows:

            if row["is_active"] and active_plan is None:

                active_plan = row

            else:

                previous_plans.append(row)


        if active_plan is None:

            return {
                "eligible": False,
                "reason": "No active insurance plan found",
                "plan": rows[0],
                "previous_plans": rows
            }


        return {

            "eligible": True,

            "member_id":
                active_plan["member_id"],

            "payer_name":
                active_plan["payer_name"],

            "plan":
                active_plan,

            "previous_plans":
                previous_plans
        }


    # ========================================================
    # REQUIRED FIELDS
    # ========================================================

    def _validate_request_fields(
        self,
        requested_hcpcs,
        diagnosis_icd10,
        ordering_physician,
        signed_order_date
    ):

        missing = []


        if not requested_hcpcs:
            missing.append("Requested HCPCS/CPT")


        if not diagnosis_icd10:
            missing.append("Diagnosis ICD-10")


        if not ordering_physician:
            missing.append("Ordering physician")


        if not signed_order_date:
            missing.append("Signed/dated order")


        return {

            "complete":
                len(missing) == 0,

            "missing":
                missing
        }


    # ========================================================
    # CONDITIONS
    # ========================================================

    def _get_patient_conditions(
        self,
        cur,
        patient_id
    ):

        cur.execute(
            """
            SELECT
                snomed_code,
                description,
                start_date,
                stop_date,
                resolved_icd10_code,
                resolved_icd10_score
            FROM patient_condition_history
            WHERE patient_id = %s
            ORDER BY start_date DESC
            """,
            (patient_id,)
        )

        return cur.fetchall()


    # ========================================================
    # CARE PLANS
    # ========================================================

    def _get_patient_careplans(
        self,
        cur,
        patient_id
    ):

        cur.execute(
            """
            SELECT
                description,
                reason_snomed_code,
                reason_description,
                start_date,
                stop_date
            FROM patient_careplan_history
            WHERE patient_id = %s
            ORDER BY start_date DESC
            """,
            (patient_id,)
        )

        return cur.fetchall()


    # ========================================================
    # UTILIZATION
    # ========================================================

    def _get_prior_utilization(
        self,
        cur,
        patient_id,
        requested_hcpcs
    ):

        cur.execute(
            """
            SELECT
                proc_date,
                description,
                resolved_hcpc_code,
                resolved_hcpc_score
            FROM patient_procedure_history
            WHERE patient_id = %s
              AND resolved_hcpc_code = %s
            ORDER BY proc_date DESC
            """,
            (
                patient_id,
                requested_hcpcs
            )
        )

        rows = cur.fetchall()

        return {
            "count": len(rows),
            "instances": rows
        }


    # ========================================================
    # ALL UTILIZATION
    # ========================================================

    def _get_all_utilization(
        self,
        cur,
        patient_id
    ):

        cur.execute(
            """
            SELECT
                proc_date,
                description,
                resolved_hcpc_code,
                resolved_hcpc_score
            FROM patient_procedure_history
            WHERE patient_id = %s
            ORDER BY proc_date DESC
            """,
            (patient_id,)
        )

        return cur.fetchall()


    # ========================================================
    # FIND ARTICLES
    # ========================================================

    def _find_articles_for_hcpcs(
        self,
        cur,
        hcpcs_code
    ):

        cur.execute(
            """
            SELECT DISTINCT
                article_id,
                article_version
            FROM pa_kb.article_hcpc
            WHERE hcpc_code_id = %s
            """,
            (hcpcs_code,)
        )

        rows = cur.fetchall()
        if not rows:
            try:
                cur.execute(
                    """
                    SELECT DISTINCT
                        article_id,
                        article_version
                    FROM article_hcpc
                    WHERE hcpc_code = %s OR hcpc_code_id = %s
                    """,
                    (hcpcs_code, hcpcs_code)
                )
                rows = cur.fetchall()
            except Exception:
                pass

        return rows


    # ========================================================
    # ARTICLE & POLICY LINEAGE HELPERS
    # ========================================================

    def _get_article(
        self,
        cur,
        article_id,
        article_version
    ):

        cur.execute(
            """
            SELECT
                article_id,
                article_version,
                title,
                status
            FROM pa_kb.article_policy
            WHERE article_id = %s
              AND article_version = %s
            """,
            (
                article_id,
                article_version
            )
        )
        row = cur.fetchone()
        if not row:
            try:
                cur.execute(
                    """
                    SELECT
                        article_id,
                        article_version,
                        title,
                        status
                    FROM article_policy
                    WHERE article_id = %s
                      AND article_version = %s
                    """,
                    (article_id, article_version)
                )
                row = cur.fetchone()
            except Exception:
                pass
        return row


    def _is_date_effective(self, service_date_str, eff_date, end_date):
        """
        Validates if service_date_str falls within [eff_date, end_date].
        Returns True if effective, False otherwise.
        """
        if not service_date_str:
            return True  # If no date is supplied, caller handles missing date check
            
        try:
            if isinstance(service_date_str, str):
                svc_dt = datetime.strptime(service_date_str[:10], "%Y-%m-%d").date()
            elif isinstance(service_date_str, datetime):
                svc_dt = service_date_str.date()
            else:
                svc_dt = service_date_str

            if eff_date:
                eff_dt = eff_date if not isinstance(eff_date, datetime) else eff_date.date()
                if svc_dt < eff_dt:
                    return False

            if end_date:
                end_dt = end_date if not isinstance(end_date, datetime) else end_date.date()
                if svc_dt > end_dt:
                    return False

            return True
        except Exception:
            return True


    def _resolve_lcd(self, cur, article_id, article_version, service_date=None):
        """
        Stage B: Resolve Article -> LCD using lcd_article_bridge and lcd_policy.
        """
        cur.execute(
            """
            SELECT
                b.lcd_id,
                b.lcd_version,
                p.title,
                p.status,
                p.rev_eff_date,
                p.rev_end_date,
                p.is_active
            FROM pa_kb.lcd_article_bridge b
            JOIN pa_kb.lcd_policy p ON b.lcd_id = p.lcd_id AND b.lcd_version = p.lcd_version
            WHERE b.article_id = %s
              AND b.article_version = %s
            """,
            (article_id, article_version)
        )
        lcd_rows = cur.fetchall()

        if not lcd_rows:
            return {
                "present": False,
                "lcd_records": [],
                "policy_path": "ARTICLE_ONLY"
            }

        resolved_lcds = []
        for r in lcd_rows:
            is_active_val = bool(r.get("is_active")) if r.get("is_active") is not None else (r.get("status") == "A")
            is_eff = self._is_date_effective(service_date, r.get("rev_eff_date"), r.get("rev_end_date"))
            resolved_lcds.append({
                "lcd_id": r["lcd_id"],
                "lcd_version": r["lcd_version"],
                "title": r["title"],
                "status": r["status"],
                "is_active": is_active_val,
                "rev_eff_date": r.get("rev_eff_date"),
                "rev_end_date": r.get("rev_end_date"),
                "is_effective": is_eff
            })

        return {
            "present": True,
            "lcd_records": resolved_lcds,
            "policy_path": "ARTICLE_LCD"
        }


    def _resolve_jurisdiction(self, cur, lcd_id, lcd_version, patient_state=None):
        """
        Stage C: Resolve LCD -> Jurisdiction using lcd_jurisdiction.
        Uses patient.state as a prototype jurisdiction proxy/signal.
        """
        cur.execute(
            """
            SELECT DISTINCT state_abbrev
            FROM pa_kb.lcd_jurisdiction
            WHERE lcd_id = %s
              AND lcd_version = %s
            """,
            (lcd_id, lcd_version)
        )
        rows = cur.fetchall()
        policy_states = [r["state_abbrev"] for r in rows if r.get("state_abbrev")]

        if not policy_states:
            return {
                "status": "NOT_AVAILABLE",
                "patient_state": patient_state,
                "policy_states": []
            }

        if not patient_state:
            return {
                "status": "UNDETERMINED",
                "patient_state": None,
                "policy_states": policy_states
            }

        if patient_state.strip().upper() in [s.upper() for s in policy_states]:
            return {
                "status": "MATCHED",
                "patient_state": patient_state,
                "policy_states": policy_states
            }
        else:
            return {
                "status": "MISMATCH",
                "patient_state": patient_state,
                "policy_states": policy_states
            }


    def _resolve_ncd(self, cur, article_id, article_version, lcd_records=None, service_date=None):
        """
        Stage D: Resolve NCD independently through lcd_ncd_bridge & article_ncd_bridge.
        Deduplicates by (ncd_id, ncd_version).
        """
        ncd_map = {}

        # 1. Check article_ncd_bridge
        cur.execute(
            """
            SELECT
                b.ncd_id,
                b.ncd_version,
                p.mnl_sect_title,
                p.effective_date,
                p.termination_date,
                p.is_active
            FROM pa_kb.article_ncd_bridge b
            JOIN pa_kb.ncd_policy p ON b.ncd_id = p.ncd_id AND b.ncd_version = p.ncd_version
            WHERE b.article_id = %s
              AND b.article_version = %s
            """,
            (article_id, article_version)
        )
        for r in cur.fetchall():
            key = (r["ncd_id"], r["ncd_version"])
            ncd_map[key] = {
                "ncd_id": r["ncd_id"],
                "ncd_version": r["ncd_version"],
                "title": r.get("mnl_sect_title", ""),
                "effective_date": r.get("effective_date"),
                "termination_date": r.get("termination_date"),
                "is_active": bool(r.get("is_active")) if r.get("is_active") is not None else True,
                "source": ["ARTICLE_NCD_BRIDGE"]
            }

        # 2. Check lcd_ncd_bridge for each LCD
        if lcd_records:
            for lcd in lcd_records:
                cur.execute(
                    """
                    SELECT
                        b.ncd_id,
                        b.ncd_version,
                        p.mnl_sect_title,
                        p.effective_date,
                        p.termination_date,
                        p.is_active
                    FROM pa_kb.lcd_ncd_bridge b
                    JOIN pa_kb.ncd_policy p ON b.ncd_id = p.ncd_id AND b.ncd_version = p.ncd_version
                    WHERE b.lcd_id = %s
                      AND b.lcd_version = %s
                    """,
                    (lcd["lcd_id"], lcd["lcd_version"])
                )
                for r in cur.fetchall():
                    key = (r["ncd_id"], r["ncd_version"])
                    if key in ncd_map:
                        if "LCD_NCD_BRIDGE" not in ncd_map[key]["source"]:
                            ncd_map[key]["source"].append("LCD_NCD_BRIDGE")
                    else:
                        ncd_map[key] = {
                            "ncd_id": r["ncd_id"],
                            "ncd_version": r["ncd_version"],
                            "title": r.get("mnl_sect_title", ""),
                            "effective_date": r.get("effective_date"),
                            "termination_date": r.get("termination_date"),
                            "is_active": bool(r.get("is_active")) if r.get("is_active") is not None else True,
                            "source": ["LCD_NCD_BRIDGE"]
                        }

        if not ncd_map:
            return {
                "status": "NOT_PRESENT",
                "ncd_records": []
            }

        resolved_ncds = []
        for ncd in ncd_map.values():
            is_eff = self._is_date_effective(service_date, ncd.get("effective_date"), ncd.get("termination_date"))
            ncd["is_effective"] = is_eff
            resolved_ncds.append(ncd)

        return {
            "status": "PRESENT",
            "ncd_records": resolved_ncds
        }


    # ========================================================
    # COVERED ICD
    # ========================================================

    def _find_covered_icd(
        self,
        cur,
        article_id,
        article_version,
        icd10_code
    ):

        cur.execute(
            """
            SELECT
                c.article_id,
                c.article_version,
                c.icd10_code_id AS icd10_code,
                c.icd10_covered_group AS covered_group,
                c.description,
                CASE WHEN g.paragraph IS NULL OR g.paragraph = '' THEN TRUE ELSE FALSE END AS is_unconditional,
                g.paragraph AS group_text
            FROM pa_kb.article_icd10_covered c
            LEFT JOIN pa_kb.article_icd10_covered_group g
                   ON c.article_id = g.article_id
                  AND c.article_version = g.article_version
                  AND c.icd10_covered_group = g.icd10_covered_group
            WHERE c.article_id = %s
              AND c.article_version = %s
              AND c.icd10_code_id = %s
            """,
            (
                article_id,
                article_version,
                icd10_code
            )
        )

        return cur.fetchone()


    # ========================================================
    # NON-COVERED ICD
    # ========================================================

    def _find_noncovered_icd(
        self,
        cur,
        article_id,
        article_version,
        icd10_code
    ):

        cur.execute(
            """
            SELECT
                article_id,
                article_version,
                icd10_code_id AS icd10_code,
                icd10_noncovered_group AS noncovered_group,
                description
            FROM pa_kb.article_icd10_noncovered
            WHERE article_id = %s
              AND article_version = %s
              AND icd10_code_id = %s
            """,
            (
                article_id,
                article_version,
                icd10_code
            )
        )

        return cur.fetchone()


    # ========================================================
    # POLICY RESOLUTION (STAGED)
    # ========================================================

    def _resolve_policy(
        self,
        cur,
        hcpcs,
        icd10,
        patient_state=None,
        service_date=None
    ):

        articles = self._find_articles_for_hcpcs(
            cur,
            hcpcs
        )

        if not articles:
            return {
                "result": "NO_ARTICLE",
                "matches": []
            }

        matches = []

        for article in articles:
            article_id = article["article_id"]
            article_version = article["article_version"]

            policy = self._get_article(
                cur,
                article_id,
                article_version
            )

            if not policy:
                continue

            if policy["status"] != "A":
                continue

            covered = self._find_covered_icd(
                cur,
                article_id,
                article_version,
                icd10
            )

            noncovered = self._find_noncovered_icd(
                cur,
                article_id,
                article_version,
                icd10
            )

            # Stage B: Resolve LCD
            lcd_info = self._resolve_lcd(cur, article_id, article_version, service_date)

            # Stage C: Resolve Jurisdiction for each LCD if present
            jurisdiction_info = {
                "status": "NOT_AVAILABLE",
                "patient_state": patient_state,
                "policy_states": []
            }
            if lcd_info["present"] and lcd_info["lcd_records"]:
                # Evaluate jurisdiction for the primary/first LCD record
                first_lcd = lcd_info["lcd_records"][0]
                jurisdiction_info = self._resolve_jurisdiction(
                    cur,
                    first_lcd["lcd_id"],
                    first_lcd["lcd_version"],
                    patient_state
                )

            # Stage D: Resolve NCD
            ncd_info = self._resolve_ncd(
                cur,
                article_id,
                article_version,
                lcd_info.get("lcd_records"),
                service_date
            )

            matches.append({
                "article_id": article_id,
                "article_version": article_version,
                "article_title": policy["title"],
                "status": policy["status"],
                "covered": covered,
                "noncovered": noncovered,
                "lcd": lcd_info,
                "jurisdiction": jurisdiction_info,
                "ncd": ncd_info
            })

        return {
            "result": "FOUND" if matches else "NO_MATCH",
            "matches": matches
        }


    # ========================================================
    # PA REQUIREMENT
    # ========================================================

    def _check_pa_requirement(
        self,
        cur,
        payer_name,
        hcpcs
    ):

        try:

            cur.execute(
                """
                SELECT
                    requires_pa,
                    source,
                    notes
                FROM pa_requirement_rule
                WHERE hcpc_code = %s
                  AND (
                        payer_name = %s
                        OR payer_name IS NULL
                  )
                  AND (
                        effective_start IS NULL
                        OR effective_start <= CURDATE()
                  )
                  AND (
                        effective_end IS NULL
                        OR effective_end >= CURDATE()
                  )
                ORDER BY
                    payer_name IS NULL,
                    id DESC
                LIMIT 1
                """,
                (
                    hcpcs,
                    payer_name
                )
            )

            return cur.fetchone()

        except Exception:

            return None


    # ========================================================
    # CLINICAL EVIDENCE
    # ========================================================

    def _build_clinical_evidence(
        self,
        cur,
        patient_id,
        diagnosis_icd10
    ):

        conditions = self._get_patient_conditions(
            cur,
            patient_id
        )

        careplans = self._get_patient_careplans(
            cur,
            patient_id
        )


        matching_conditions = [

            row

            for row in conditions

            if row["resolved_icd10_code"]
            == diagnosis_icd10

        ]


        return {

            "conditions":
                conditions,

            "matching_conditions":
                matching_conditions,

            "careplans":
                careplans,

            "history_found":
                bool(
                    conditions
                    or careplans
                ),

            "diagnosis_history_found":
                bool(
                    matching_conditions
                )
        }


    # ========================================================
    # CHROMA
    # ========================================================

    def _retrieve_chroma_evidence(
        self,
        hcpcs,
        icd10
    ):

        if not CHROMA_ENABLED:
            return []


        if not CHROMA_DIR:
            return []


        try:

            import chromadb


            client = chromadb.PersistentClient(
                path=CHROMA_DIR
            )


            collection = client.get_collection(
                name=CHROMA_COLLECTION
            )


            query = (
                f"HCPCS {hcpcs} "
                f"ICD-10 {icd10} "
                "prior authorization coverage policy"
            )


            results = collection.query(

                query_texts=[query],

                n_results=CHROMA_TOP_K
            )


            documents = results.get(
                "documents",
                [[]]
            )


            metadatas = results.get(
                "metadatas",
                [[]]
            )


            if not documents:
                return []


            evidence = []


            for index, document in enumerate(
                documents[0]
            ):

                metadata = {}


                if metadatas and metadatas[0]:

                    if index < len(
                        metadatas[0]
                    ):

                        metadata = metadatas[0][index]


                evidence.append({

                    "document":
                        document,

                    "metadata":
                        metadata
                })


            return evidence


        except Exception:

            # Chroma failure must never stop
            # the deterministic engine.

            return []


    # ========================================================
    # COMPACT OBJECT
    # ========================================================

    def _compact(
        self,
        value,
        max_chars=2500
    ):

        try:

            text = json.dumps(
                value,
                default=str
            )

        except Exception:

            text = str(value)

        # Strip raw HTML tags to prevent token inflation
        if "<" in text and ">" in text:
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            try:
                value = json.loads(text)
            except Exception:
                pass

        if len(text) <= max_chars:
            return value


        return text[:max_chars] + "...[truncated]"


    # ========================================================
    # BUILD COMPACT LLM PAYLOAD
    # ========================================================

    def _build_llm_payload(
        self,
        deterministic_result,
        request,
        patient,
        eligibility,
        clinical,
        utilization,
        all_utilization,
        policy,
        pa_requirement,
        chroma_evidence
    ):

        """
        IMPORTANT:

        Do not send the entire database object to the LLM.

        This avoids:

            - Groq TPM errors
            - unnecessarily large prompts
            - irrelevant patient history
            - excessive token usage

        The payload is structured explicitly.
        """

        return {

            "task":
                "Explain the already-determined PA decision.",

            "authority": {

                "deterministic_engine":
                    "MYSQL",

                "llm_role":
                    "EXPLANATION_ONLY",

                "llm_may_change_decision":
                    False
            },


            "decision": {

                "status":
                    deterministic_result["status"],

                "reason_type":
                    deterministic_result["reason_type"],

                "deterministic_reasoning":
                    deterministic_result["reasoning"]
            },


            "request": {

                "patient_id":
                    request["patient_id"],

                "requested_hcpcs":
                    request["requested_hcpcs"],

                "diagnosis_icd10":
                    request["diagnosis_icd10"],

                "ordering_physician":
                    request["ordering_physician"],

                "signed_order_date":
                    request["signed_order_date"],

                "provider_rationale":
                    request["provider_rationale"]
            },


            "patient": self._compact(
                patient,
                1800
            ),


            "eligibility": self._compact(
                eligibility,
                1800
            ),


            "clinical_evidence": {

                "history_found":
                    clinical.get(
                        "history_found",
                        False
                    ),

                "diagnosis_history_found":
                    clinical.get(
                        "diagnosis_history_found",
                        False
                    ),

                "matching_conditions":
                    self._compact(
                        clinical.get(
                            "matching_conditions",
                            []
                        ),
                        2200
                    ),

                "careplans":
                    self._compact(
                        clinical.get(
                            "careplans",
                            []
                        ),
                        1800
                    )
            },


            "utilization": {

                "requested_service_count":
                    utilization.get(
                        "count",
                        0
                    ),

                "requested_service_instances":
                    self._compact(
                        utilization.get(
                            "instances",
                            []
                        ),
                        1500
                    ),

                "all_patient_utilization":
                    self._compact(
                        all_utilization,
                        1800
                    )
            },


            "policy_mysql":
                self._compact(
                    policy,
                    4000
                ),


            "pa_requirement":
                self._compact(
                    pa_requirement,
                    1000
                ),


            "policy_chroma":
                self._compact(
                    chroma_evidence,
                    4500
                )
        }


    # ========================================================
    # OPENAI
    # ========================================================

    def _call_openai(
        self,
        payload
    ):

        if not self.openai_client:

            raise RuntimeError(
                "OpenAI client unavailable"
            )


        response = self.openai_client.responses.create(

            model=PRIMARY_MODEL,

            instructions=
                LLM_SYSTEM_PROMPT,

            input=json.dumps(
                payload,
                default=str
            ),

            text={
                "format": {
                    "type":
                        "json_object"
                }
            },

            store=False
        )


        text = response.output_text


        if not text:

            raise RuntimeError(
                "OpenAI returned empty response"
            )


        return json.loads(text)


    # ========================================================
    # GEMINI
    # ========================================================

    def _call_gemini(
        self,
        payload
    ):

        if not self.gemini_client:

            raise RuntimeError(
                "Gemini client unavailable"
            )


        """
        IMPORTANT:

        Do NOT send:

            additionalProperties

        Do NOT send the old strict schema.

        Gemini receives a clean JSON-output request.

        The structure is described in the prompt and then
        validated locally.
        """


        prompt = (

            LLM_SYSTEM_PROMPT

            + "\n\n"

            + "INPUT PAYLOAD:\n"

            + json.dumps(
                payload,
                indent=2,
                default=str
            )

        )


        response = (
            self.gemini_client
            .models
            .generate_content(

                model=GEMINI_MODEL,

                contents=prompt,

                config={

                    "response_mime_type":
                        "application/json",

                    "temperature":
                        0
                }
            )
        )


        if not response.text:

            raise RuntimeError(
                "Gemini returned empty response"
            )


        return json.loads(
            response.text
        )


    # ========================================================
    # GROQ
    # ========================================================

    # ========================================================
    # GROQ (MODEL A)
    # ========================================================

    def _call_groq(
        self,
        payload
    ):
        return self._call_groq_model(payload, GROQ_MODEL, "Groq Model A")

    # ========================================================
    # GROQ (MODEL B FALLBACK)
    # ========================================================

    def _call_groq_fallback(
        self,
        payload
    ):
        return self._call_groq_model(payload, GROQ_MODEL_FALLBACK, "Groq Model B")

    def _call_groq_model(
        self,
        payload,
        model_name,
        label
    ):
        if not self.groq_client:
            raise RuntimeError(
                f"{label} client unavailable"
            )

        response = (
            self.groq_client
            .chat
            .completions
            .create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": LLM_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            payload,
                            default=str
                        )
                    }
                ],
                temperature=0,
                max_tokens=2500,
                response_format={
                    "type": "json_object"
                }
            )
        )

        text = (
            response
            .choices[0]
            .message
            .content
        )

        if not text:
            raise RuntimeError(
                f"{label} returned empty response"
            )

        return json.loads(text)


    # ========================================================
    # VALIDATE LLM JSON
    # ========================================================

    def _validate_llm_output(
        self,
        output,
        deterministic_status,
        deterministic_reason
    ):

        if not isinstance(
            output,
            dict
        ):
            raise ValueError(
                "LLM output is not a JSON object"
            )

        # ----------------------------------------------------
        # Required fields
        # ----------------------------------------------------

        for field in LLM_REQUIRED_FIELDS:
            if field not in output:
                raise ValueError(
                    f"Missing LLM field: {field}"
                )

        # ----------------------------------------------------
        # List fields
        # ----------------------------------------------------

        list_fields = [
            "policy_evidence",
            "patient_clinical_evidence",
            "evidence_relationship",
            "missing_information",
            "risk_review_flags"
        ]

        for field in list_fields:
            if not isinstance(
                output[field],
                list
            ):
                raise ValueError(
                    f"{field} must be a list"
                )

        # ----------------------------------------------------
        # String fields
        # ----------------------------------------------------

        string_fields = [
            "plain_summary",
            "decision_summary",
            "deterministic_decision_basis",
            "coverage_interpretation",
            "human_review_note"
        ]

        for field in string_fields:
            if not isinstance(
                output[field],
                str
            ):
                raise ValueError(
                    f"{field} must be a string"
                )

        # ----------------------------------------------------
        # CONTRADICTION CHECK
        # ----------------------------------------------------

        combined = " ".join([
            output["plain_summary"],
            output["decision_summary"],
            output["deterministic_decision_basis"],
            output["coverage_interpretation"],
            output["human_review_note"]
        ]).upper()

        if deterministic_status == APPROVED:
            if (
                "DENIED" in combined
                or "NOT COVERED" in combined
            ):
                raise ValueError(
                    "LLM contradicted APPROVED"
                )

        elif deterministic_status == PENDED:
            if (
                "AUTOMATICALLY APPROVE" in combined
            ):
                raise ValueError(
                    "LLM contradicted PENDED"
                )

        elif deterministic_status == INFO:
            if (
                "AUTOMATICALLY APPROVE" in combined
            ):
                raise ValueError(
                    "LLM contradicted INFO_REQUESTED"
                )

        elif deterministic_status == NOT_REQUIRED:
            if (
                "DENIED" in combined
                or "PENDED" in combined
            ):
                raise ValueError(
                    "LLM contradicted NOT_REQUIRED"
                )

        output["_authoritative_status"] = (
            deterministic_status
        )

        output["_authoritative_reason"] = (
            deterministic_reason
        )

        return output


    # ========================================================
    # TEMPLATE-BASED GUARANTEED FALLBACK
    # ========================================================

    def _build_template_explanation(
        self,
        status,
        reason_type,
        reasoning,
        payload
    ):
        """
        Guaranteed zero-API-call fallback explanation generator.
        Builds a structured JSON payload directly from decision evidence.
        """
        hcpcs = payload.get("request", {}).get("requested_hcpcs", "")
        icd10 = payload.get("request", {}).get("diagnosis_icd10", "")
        util_count = payload.get("utilization", {}).get("requested_service_count", 0)
        util_instances = payload.get("utilization", {}).get("requested_service_instances", [])

        if util_count == 0:
            util_bullet = "**Prior Utilization:** No prior instances of this service were found in the patient's history."
        else:
            last_date = util_instances[0].get("proc_date", "recent record") if isinstance(util_instances, list) and len(util_instances) > 0 and isinstance(util_instances[0], dict) else "recent record"
            util_bullet = f"**Prior Utilization:** This service was previously performed {util_count} time(s), most recently on {last_date}. This was factored into the review."

        policy_data = payload.get("policy_mysql", {})
        covered_info = ""
        if isinstance(policy_data, dict) and policy_data.get("matches"):
            matches = policy_data.get("matches", [])
            if len(matches) > 0 and matches[0].get("covered"):
                cov = matches[0]["covered"]
                grp = cov.get("covered_group", 1)
                is_uncond = cov.get("is_unconditional", True)
                grp_txt = cov.get("group_text", "")
                if is_uncond:
                    covered_info = f"**Coverage & Conditionality:** This diagnosis is covered without additional conditions (Group {grp}, unconditional match)."
                else:
                    covered_info = f"**Coverage & Conditionality:** This diagnosis is covered subject to the following documented condition: {grp_txt or 'Clinical criteria requirements'}. Evaluation indicates review is pending manual verification."

        if not covered_info:
            covered_info = f"**Coverage & Conditionality:** Diagnosis {icd10} evaluated against coverage policy rules for service {hcpcs}."

        if status == APPROVED and reason_type == "CRITERIA_MET":
            plain_summary = f"This request for service {hcpcs} with diagnosis {icd10} is recommended for approval, pending reviewer confirmation. The requested care meets policy coverage criteria based on available records."
            coverage_interp = f"Requested service {hcpcs} for diagnosis {icd10} aligns with active coverage policy criteria, pending reviewer confirmation."
            human_note = "Verify physician signature and ordering date on physical chart before confirming final approval."
            missing_info = []
            risk_flags = []

        elif status == INFO and reason_type == "NONCOVERED_DIAGNOSIS":
            plain_summary = f"This request does not currently meet standard coverage criteria, pending reviewer confirmation. Diagnosis code {icd10} is listed as non-covered under baseline guidelines for service {hcpcs}."
            coverage_interp = f"Diagnosis {icd10} is specified as non-covered under baseline policy guidelines for service {hcpcs}."
            human_note = "Review clinical justification for non-covered diagnosis exception or request peer-to-peer consultation."
            missing_info = ["Detailed physician clinical justification for diagnosis exception"]
            risk_flags = ["NON_COVERED_DIAGNOSIS_RULE"]

        elif status == INFO and reason_type == "MISSING_CLINICAL_RATIONALE":
            plain_summary = f"This request requires additional clinical information before a recommendation can be finalized, pending reviewer confirmation. While service {hcpcs} matches diagnosis {icd10}, clinical rationale notes were omitted."
            coverage_interp = "Service matches coverage policy, but clinical rationale documentation is required before finalization."
            human_note = "Obtain provider progress notes and clinical rationale for chart record."
            missing_info = ["Provider clinical rationale and progress notes"]
            risk_flags = ["MISSING_CLINICAL_DOCUMENTATION"]

        elif status == INFO and reason_type == "NO_PATIENT_HISTORY":
            plain_summary = f"This request requires additional clinical information before a recommendation can be finalized, pending reviewer confirmation. Service {hcpcs} matches diagnosis {icd10}, but no prior clinical history was located."
            coverage_interp = "Policy criteria match, but historical clinical records are required for confirmation."
            human_note = "Request external medical history records from ordering facility."
            missing_info = ["Patient medical history and care plan records"]
            risk_flags = ["NO_HISTORICAL_RECORD"]

        elif status == PENDED and reason_type == "REPEAT_UTILIZATION":
            plain_summary = f"This request is recommended for manual review, pending reviewer confirmation. Repeat service utilization was detected for service {hcpcs}."
            coverage_interp = "Repeat service utilization detected. Verification of frequency criteria required."
            human_note = "Check frequency limit rules against historical service dates."
            missing_info = []
            risk_flags = ["REPEAT_UTILIZATION_FLAG"]

        elif status == PENDED and reason_type in ("RULE_NOT_FOUND", "NO_ACTIVE_POLICY_MATCH"):
            plain_summary = f"This request is recommended for manual policy review, pending reviewer confirmation. No active automated policy rule was matched for service {hcpcs} and diagnosis {icd10}."
            coverage_interp = "No active coverage rule match found in knowledgebase."
            human_note = "Consult specialty clinical guidelines to evaluate medical necessity."
            missing_info = []
            risk_flags = ["MANUAL_POLICY_REVIEW_REQUIRED"]

        elif status == NOT_REQUIRED:
            plain_summary = f"Prior authorization is not required for service {hcpcs} under current payer guidelines. The service is exempt from formal authorization requirements."
            coverage_interp = "Service exempt from prior authorization requirements."
            human_note = "Waive authorization requirement."
            missing_info = []
            risk_flags = []

        else:
            plain_summary = f"This request is recommended for reviewer review, pending reviewer confirmation. {reasoning}"
            coverage_interp = f"Decision status: {status}. Evaluated based on active policy criteria."
            human_note = "Review clinical documentation against payer coverage guidelines."
            missing_info = []
            risk_flags = []

        return {
            "plain_summary": plain_summary,
            "key_findings": [
                covered_info,
                "**Clinical Evidence:** Patient records evaluated against active coverage policy.",
                util_bullet
            ],
            "decision_summary": reasoning,
            "deterministic_decision_basis": reasoning,
            "policy_evidence": [
                f"Policy evaluation rule: {reason_type}",
                f"Requested HCPCS: {hcpcs}, Diagnosis: {icd10}"
            ],
            "patient_clinical_evidence": [
                "Evaluated using available patient clinical condition and procedure records."
            ],
            "evidence_relationship": [
                "Recommendation built directly from structured policy rules and patient records."
            ],
            "coverage_interpretation": coverage_interp,
            "missing_information": missing_info,
            "risk_review_flags": risk_flags,
            "human_review_note": human_note,
            "_authoritative_status": status,
            "_authoritative_reason": reason_type,
            "_provider": "TEMPLATE_FALLBACK"
        }


    # ========================================================
    # PROVIDER FALLBACK
    # ========================================================

    def _generate_llm_explanation(
        self,
        payload
    ):

        providers = [
            (
                "Groq (Model A)",
                self._call_groq
            ),
            (
                "Groq (Model B Fallback)",
                self._call_groq_fallback
            ),
            (
                "Gemini",
                self._call_gemini
            ),
            (
                "OpenAI",
                self._call_openai
            )
        ]

        errors = []

        for provider_name, provider_function in providers:
            try:
                result = provider_function(
                    payload
                )

                if not isinstance(
                    result,
                    dict
                ):
                    raise ValueError(
                        "Provider returned non-object JSON"
                    )

                result = self._validate_llm_output(
                    result,
                    payload["decision"]["status"],
                    payload["decision"]["reason_type"]
                )

                result["_provider"] = provider_name
                print(
                    f"[LLM] SUCCESS -> {provider_name}"
                )
                return result

            except Exception as exc:
                error = {
                    "provider": provider_name,
                    "error": f"{type(exc).__name__}: {str(exc)}"
                }
                errors.append(error)
                continue

        # ====================================================
        # ALL LLM PROVIDERS FAILED -> GUARANTEED TEMPLATE FALLBACK
        # ====================================================

        print("[LLM] All LLM providers failed. Using structured template fallback.")
        fallback_result = self._build_template_explanation(
            payload["decision"]["status"],
            payload["decision"]["reason_type"],
            payload["decision"]["deterministic_reasoning"],
            payload
        )
        fallback_result["_errors"] = errors
        return fallback_result


    # ========================================================
    # BUILD RESULT
    # ========================================================

    def _build_result(
        self,
        request_id,
        status,
        reason_type,
        reasoning,
        llm_explanation=None
    ):

        return {

            "request_id":
                request_id,

            "status":
                status,

            "reason_type":
                reason_type,

            "reasoning":
                reasoning,

            "requires_human_review":
                status not in (
                    APPROVED,
                    NOT_REQUIRED
                ),

            "llm_explanation":
                llm_explanation
        }


    # ========================================================
    # FINALIZE
    # ========================================================

    def _finalize(
        self,
        cur,
        conn,
        request_id,
        request,
        patient,
        eligibility,
        clinical,
        utilization,
        all_utilization,
        policy,
        pa_requirement,
        status,
        reason_type,
        reasoning,
        chroma_evidence=None
    ):

        preliminary = self._build_result(

            request_id,

            status,

            reason_type,

            reasoning
        )


        # ----------------------------------------------------
        # LLM
        # ----------------------------------------------------

        payload = self._build_llm_payload(

            preliminary,

            request,

            patient,

            eligibility,

            clinical,

            utilization,

            all_utilization,

            policy,

            pa_requirement,

            chroma_evidence or []
        )


        llm_explanation = (
            self._generate_llm_explanation(
                payload
            )
        )


        # ----------------------------------------------------
        # DATABASE WRITE
        # ----------------------------------------------------

        now = datetime.utcnow()


        plan = (
            eligibility.get(
                "plan"
            )
            or {}
        )


        cur.execute(
            """
            INSERT INTO pa_request
            (
                request_id,
                patient_id,
                member_id,
                payer_name,
                requested_hcpcs,
                diagnosis_icd10,
                ordering_provider,
                clinical_rationale,
                status,
                submitted_at,
                plan_member_id,
                plan_payer_name,
                plan_start_year,
                plan_end_year,
                plan_active_at_submission
            )
            VALUES
            (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (

                request_id,

                request["patient_id"],

                eligibility.get(
                    "member_id"
                ),

                eligibility.get(
                    "payer_name"
                ),

                request["requested_hcpcs"],

                request["diagnosis_icd10"],

                request["ordering_physician"],

                request["provider_rationale"],

                status,

                now,

                plan.get(
                    "member_id"
                ),

                plan.get(
                    "payer_name"
                ),

                plan.get(
                    "start_year"
                ),

                plan.get(
                    "end_year"
                ),

                plan.get(
                    "is_active"
                )
            )
        )


        decision_log_payload = {

            "deterministic_reasoning":
                reasoning,

            "llm_explanation":
                llm_explanation
        }


        cur.execute(
            """
            INSERT INTO pa_decision_log
            (
                request_id,
                rule_source,
                matched_result,
                reason_type,
                reasoning_text,
                decided_by,
                decided_at
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
            """,
            (

                request_id,

                "mysql_decision_engine",

                status,

                reason_type,

                json.dumps(
                    decision_log_payload,
                    default=str
                ),

                (
                    "system"
                    if status in (
                        APPROVED,
                        NOT_REQUIRED
                    )
                    else
                    "pending_human_review"
                ),

                now
            )
        )


        conn.commit()


        return self._build_result(

            request_id,

            status,

            reason_type,

            reasoning,

            llm_explanation
        )


    # ========================================================
    # EVALUATE
    # ========================================================

    def evaluate(
        self,
        patient_id,
        requested_hcpcs,
        diagnosis_icd10,
        ordering_physician,
        signed_order_date,
        provider_rationale=None
    ):

        request_id = str(
            uuid.uuid4()
        )


        request = {

            "patient_id":
                patient_id,

            "requested_hcpcs":
                requested_hcpcs,

            "diagnosis_icd10":
                diagnosis_icd10,

            "ordering_physician":
                ordering_physician,

            "signed_order_date":
                signed_order_date,

            "provider_rationale":
                provider_rationale
        }


        conn = self._conn()


        try:

            with conn.cursor() as cur:

                # =================================================
                # 1. PATIENT
                # =================================================

                patient_result = (
                    self._check_patient(
                        cur,
                        patient_id
                    )
                )


                if not patient_result["found"]:

                    reasoning = (
                        "Patient ID was not found "
                        "in the patient database. "
                        "The request cannot be evaluated "
                        "until the patient record is verified."
                    )


                    return self._finalize(

                        cur,
                        conn,
                        request_id,
                        request,

                        patient=None,

                        eligibility={
                            "eligible": False,
                            "reason":
                                "Patient ID not found"
                        },

                        clinical={},

                        utilization={},

                        all_utilization=[],

                        policy={
                            "result":
                                "NOT_EVALUATED"
                        },

                        pa_requirement=None,

                        status=INFO,

                        reason_type=
                            "PATIENT_NOT_FOUND",

                        reasoning=reasoning,

                        chroma_evidence=[]
                    )


                patient = patient_result[
                    "patient"
                ]


                # =================================================
                # 2. ELIGIBILITY
                # =================================================

                eligibility = (
                    self._check_eligibility(
                        cur,
                        patient_id
                    )
                )


                if not eligibility["eligible"]:

                    reasoning = (

                        eligibility["reason"]

                        + ". Additional eligibility "
                          "information is required before "
                          "the PA request can be processed."
                    )


                    return self._finalize(

                        cur,
                        conn,
                        request_id,
                        request,

                        patient,

                        eligibility,

                        clinical={},

                        utilization={},

                        all_utilization=[],

                        policy={
                            "result":
                                "NOT_EVALUATED"
                        },

                        pa_requirement=None,

                        status=INFO,

                        reason_type=
                            "ELIGIBILITY_FAILED",

                        reasoning=reasoning,

                        chroma_evidence=[]
                    )


                # =================================================
                # 3. REQUIRED FIELDS
                # =================================================

                fields = (
                    self._validate_request_fields(

                        requested_hcpcs,

                        diagnosis_icd10,

                        ordering_physician,

                        signed_order_date
                    )
                )


                if not fields["complete"]:

                    reasoning = (

                        "The request is missing required "
                        "prior authorization fields: "

                        + ", ".join(
                            fields["missing"]
                        )

                        + "."
                    )


                    return self._finalize(

                        cur,
                        conn,
                        request_id,
                        request,

                        patient,

                        eligibility,

                        clinical={},

                        utilization={},

                        all_utilization=[],

                        policy={
                            "result":
                                "NOT_EVALUATED"
                        },

                        pa_requirement=None,

                        status=INFO,

                        reason_type=
                            "MISSING_PA_FIELDS",

                        reasoning=reasoning,

                        chroma_evidence=[]
                    )


                # =================================================
                # 4. PA REQUIREMENT
                # =================================================

                pa_requirement = (
                    self._check_pa_requirement(

                        cur,

                        eligibility[
                            "payer_name"
                        ],

                        requested_hcpcs
                    )
                )


                if (
                    pa_requirement
                    and
                    pa_requirement["requires_pa"] == 0
                ):

                    reasoning = (

                        f"HCPCS {requested_hcpcs} "
                        "does not require prior authorization "
                        "according to the configured PA "
                        "requirement rule."
                    )


                    return self._finalize(

                        cur,
                        conn,
                        request_id,
                        request,

                        patient,

                        eligibility,

                        clinical={},

                        utilization={},

                        all_utilization=[],

                        policy={
                            "result":
                                "NOT_EVALUATED"
                        },

                        pa_requirement=
                            pa_requirement,

                        status=NOT_REQUIRED,

                        reason_type=
                            "PA_NOT_REQUIRED",

                        reasoning=reasoning,

                        chroma_evidence=[]
                    )


                # =================================================
                # 5. PATIENT HISTORY
                # =================================================

                clinical = (
                    self._build_clinical_evidence(

                        cur,

                        patient_id,

                        diagnosis_icd10
                    )
                )


                utilization = (
                    self._get_prior_utilization(

                        cur,

                        patient_id,

                        requested_hcpcs
                    )
                )


                all_utilization = (
                    self._get_all_utilization(

                        cur,

                        patient_id
                    )
                )


                # =================================================
                # 6. POLICY RESOLUTION (POLICY-AWARE STAGED QUERY)
                # =================================================

                patient_state = patient.get("state") if patient else None

                policy = (
                    self._resolve_policy(
                        cur,
                        requested_hcpcs,
                        diagnosis_icd10,
                        patient_state=patient_state,
                        service_date=signed_order_date
                    )
                )


                # =================================================
                # 7. CHROMA
                # =================================================

                chroma_evidence = (
                    self._retrieve_chroma_evidence(
                        requested_hcpcs,
                        diagnosis_icd10
                    )
                )


                # =================================================
                # 8. NO ARTICLE
                # =================================================

                if policy["result"] == "NO_ARTICLE":

                    reasoning = (
                        f"No active article was found "
                        f"for HCPCS {requested_hcpcs}. "
                        "The absence of a rule is NOT treated "
                        "as non-coverage. Manual policy review "
                        "is required."
                    )


                    return self._finalize(
                        cur,
                        conn,
                        request_id,
                        request,
                        patient,
                        eligibility,
                        clinical,
                        utilization,
                        all_utilization,
                        policy,
                        pa_requirement,
                        status=PENDED,
                        reason_type="RULE_NOT_FOUND",
                        reasoning=reasoning,
                        chroma_evidence=chroma_evidence
                    )


                matches = policy["matches"]


                # =================================================
                # 9. NO ACTIVE MATCH
                # =================================================

                if not matches:

                    reasoning = (
                        f"HCPCS {requested_hcpcs} "
                        "was not associated with an active "
                        "policy article for the requested "
                        "diagnosis. "
                        "This does not establish non-coverage. "
                        "Manual policy review is required."
                    )


                    return self._finalize(
                        cur,
                        conn,
                        request_id,
                        request,
                        patient,
                        eligibility,
                        clinical,
                        utilization,
                        all_utilization,
                        policy,
                        pa_requirement,
                        status=PENDED,
                        reason_type="NO_ACTIVE_POLICY_MATCH",
                        reasoning=reasoning,
                        chroma_evidence=chroma_evidence
                    )


                # MULTIPLE CONFLICTING POLICY MATCHES CHECK
                if len(matches) > 1:
                    distinct_titles = set(m.get("article_title") for m in matches)
                    if len(distinct_titles) > 1:
                        reasoning = (
                            f"Multiple conflicting active policy articles matched HCPCS {requested_hcpcs} "
                            f"and diagnosis {diagnosis_icd10}. Human review is required to resolve policy precedence."
                        )
                        return self._finalize(
                            cur,
                            conn,
                            request_id,
                            request,
                            patient,
                            eligibility,
                            clinical,
                            utilization,
                            all_utilization,
                            policy,
                            pa_requirement,
                            status=PENDED,
                            reason_type="MULTIPLE_POLICY_MATCHES",
                            reasoning=reasoning,
                            chroma_evidence=chroma_evidence
                        )


                # =================================================
                # 10. COVERED / NON-COVERED
                # =================================================

                covered_matches = [
                    m for m in matches if m["covered"] is not None
                ]

                noncovered_matches = [
                    m for m in matches if m["noncovered"] is not None
                ]


                # =================================================
                # 11. NON-COVERED (CORRECTION 1: ROUTE TO PENDED_NURSE_REVIEW)
                # =================================================

                if not covered_matches and noncovered_matches:

                    m = noncovered_matches[0]

                    reasoning = (
                        f"Diagnosis {diagnosis_icd10} "
                        "is explicitly listed as non-covered "
                        "in article "
                        f"{m['article_id']} "
                        f"version {m['article_version']}. "
                        "Deterministic KB evidence indicates non-coverage; "
                        "the system cannot automatically approve and human clinical review is required."
                    )


                    return self._finalize(
                        cur,
                        conn,
                        request_id,
                        request,
                        patient,
                        eligibility,
                        clinical,
                        utilization,
                        all_utilization,
                        policy,
                        pa_requirement,
                        status=PENDED,
                        reason_type="NONCOVERED_DIAGNOSIS",
                        reasoning=reasoning,
                        chroma_evidence=chroma_evidence
                    )


                # LCD & JURISDICTION & NCD INTEGRITY CHECKS ON MATCHED ARTICLE
                if covered_matches:
                    top_m = covered_matches[0]
                    lcd_data = top_m.get("lcd", {})
                    juris_data = top_m.get("jurisdiction", {})
                    ncd_data = top_m.get("ncd", {})

                    # Check LCD Status & Effective Dates if LCD bridge is present
                    if lcd_data.get("present") and lcd_data.get("lcd_records"):
                        lcd_rec = lcd_data["lcd_records"][0]
                        if not lcd_rec.get("is_active"):
                            reasoning = f"Associated LCD policy {lcd_rec['lcd_id']} (version {lcd_rec['lcd_version']}) is inactive. Nurse review is required."
                            return self._finalize(
                                cur, conn, request_id, request, patient, eligibility, clinical, utilization, all_utilization, policy, pa_requirement,
                                status=PENDED, reason_type="INACTIVE_LCD_POLICY", reasoning=reasoning, chroma_evidence=chroma_evidence
                            )
                        if not lcd_rec.get("is_effective"):
                            reasoning = f"Associated LCD policy {lcd_rec['lcd_id']} is not in effect on requested service date {signed_order_date}. Nurse review is required."
                            return self._finalize(
                                cur, conn, request_id, request, patient, eligibility, clinical, utilization, all_utilization, policy, pa_requirement,
                                status=PENDED, reason_type="LCD_EFFECTIVE_DATE_MISMATCH", reasoning=reasoning, chroma_evidence=chroma_evidence
                            )

                    # Check Jurisdiction Proxy Match
                    if juris_data.get("status") == "MISMATCH":
                        reasoning = f"Patient state '{patient_state}' does not match the LCD policy jurisdiction states ({', '.join(juris_data.get('policy_states', []))}). Nurse review is required."
                        return self._finalize(
                            cur, conn, request_id, request, patient, eligibility, clinical, utilization, all_utilization, policy, pa_requirement,
                            status=PENDED, reason_type="JURISDICTION_MISMATCH", reasoning=reasoning, chroma_evidence=chroma_evidence
                        )
                    elif juris_data.get("status") == "UNDETERMINED":
                        reasoning = f"Patient state is missing and jurisdiction applicability cannot be confirmed for LCD policy. Nurse review is required."
                        return self._finalize(
                            cur, conn, request_id, request, patient, eligibility, clinical, utilization, all_utilization, policy, pa_requirement,
                            status=PENDED, reason_type="JURISDICTION_UNDETERMINED", reasoning=reasoning, chroma_evidence=chroma_evidence
                        )

                    # Check NCD Effective Status if NCD bridge is present
                    if ncd_data.get("status") == "PRESENT" and ncd_data.get("ncd_records"):
                        ncd_rec = ncd_data["ncd_records"][0]
                        if not ncd_rec.get("is_active") or not ncd_rec.get("is_effective"):
                            reasoning = f"Associated NCD policy {ncd_rec['ncd_id']} ('{ncd_rec.get('title')}') is inactive or expired for date {signed_order_date}. Nurse review is required."
                            return self._finalize(
                                cur, conn, request_id, request, patient, eligibility, clinical, utilization, all_utilization, policy, pa_requirement,
                                status=PENDED, reason_type="INACTIVE_NCD_POLICY", reasoning=reasoning, chroma_evidence=chroma_evidence
                            )


                # =================================================
                # 12. COVERED MATCH
                # =================================================

                if covered_matches:

                    # ---------------------------------------------
                    # NEW PATIENT
                    # ---------------------------------------------

                    if not clinical["history_found"]:

                        reasoning = (

                            "An active HCPCS + ICD-10 "
                            "coverage match exists, but "
                            "the patient has no available "
                            "clinical history or care-plan "
                            "evidence. Automated approval "
                            "is therefore not permitted. "
                            "Additional patient history or "
                            "clinical documentation is required."
                        )


                        return self._finalize(

                            cur,
                            conn,
                            request_id,
                            request,

                            patient,
                            eligibility,
                            clinical,
                            utilization,
                            all_utilization,
                            policy,
                            pa_requirement,

                            status=INFO,

                            reason_type=
                                "NO_PATIENT_HISTORY",

                            reasoning=reasoning,

                            chroma_evidence=
                                chroma_evidence
                        )


                    # ---------------------------------------------
                    # DIAGNOSIS NOT IN HISTORY
                    # ---------------------------------------------

                    if not clinical[
                        "diagnosis_history_found"
                    ]:

                        reasoning = (

                            "The HCPCS + ICD-10 combination "
                            "matches an active coverage policy, "
                            "but the requested diagnosis is not "
                            "supported by the patient's available "
                            "condition history. Human review is "
                            "required rather than automatically "
                            "denying the request."
                        )


                        return self._finalize(

                            cur,
                            conn,
                            request_id,
                            request,

                            patient,
                            eligibility,
                            clinical,
                            utilization,
                            all_utilization,
                            policy,
                            pa_requirement,

                            status=PENDED,

                            reason_type=
                                "DIAGNOSIS_NOT_IN_HISTORY",

                            reasoning=reasoning,

                            chroma_evidence=
                                chroma_evidence
                        )


                    # ---------------------------------------------
                    # MISSING RATIONALE
                    # ---------------------------------------------

                    if not provider_rationale:

                        reasoning = (

                            "The requested service and diagnosis "
                            "match an active coverage policy and "
                            "the diagnosis is present in the "
                            "patient history. However, the provider "
                            "did not supply clinical rationale. "
                            "Additional documentation is required "
                            "before automated approval."
                        )


                        return self._finalize(

                            cur,
                            conn,
                            request_id,
                            request,

                            patient,
                            eligibility,
                            clinical,
                            utilization,
                            all_utilization,
                            policy,
                            pa_requirement,

                            status=INFO,

                            reason_type=
                                "MISSING_CLINICAL_RATIONALE",

                            reasoning=reasoning,

                            chroma_evidence=
                                chroma_evidence
                        )


                    # ---------------------------------------------
                    # REPEAT UTILIZATION
                    # ---------------------------------------------

                    if utilization["count"] > 0:

                        reasoning = (

                            f"HCPCS {requested_hcpcs} "
                            f"was previously performed "
                            f"{utilization['count']} time(s). "

                            "The policy match exists, but "
                            "repeat utilization requires "
                            "clinical review."
                        )


                        return self._finalize(

                            cur,
                            conn,
                            request_id,
                            request,

                            patient,
                            eligibility,
                            clinical,
                            utilization,
                            all_utilization,
                            policy,
                            pa_requirement,

                            status=PENDED,

                            reason_type=
                                "REPEAT_UTILIZATION",

                            reasoning=reasoning,

                            chroma_evidence=
                                chroma_evidence
                        )


                    # ---------------------------------------------
                    # APPROVAL
                    # ---------------------------------------------

                    m = covered_matches[0]


                    reasoning = (

                        "Exact HCPCS + ICD-10 coverage "
                        "match found. "

                        f"Article {m['article_id']} "
                        f"version {m['article_version']} "
                        "is active. "

                        f"HCPCS {requested_hcpcs} "
                        f"and diagnosis {diagnosis_icd10} "
                        "are associated with the same "
                        "policy article. "

                        "Required patient history is present "
                        "and no repeat utilization was detected."
                    )


                    return self._finalize(

                        cur,
                        conn,
                        request_id,
                        request,

                        patient,
                        eligibility,
                        clinical,
                        utilization,
                        all_utilization,
                        policy,
                        pa_requirement,

                        status=APPROVED,

                        reason_type=
                            "CRITERIA_MET",

                        reasoning=reasoning,

                        chroma_evidence=
                            chroma_evidence
                    )


                # =================================================
                # 13. FALLBACK
                # =================================================

                reasoning = (

                    "The request could not be deterministically "
                    "classified from the available active policy "
                    "records. Human policy review is required."
                )


                return self._finalize(

                    cur,
                    conn,
                    request_id,
                    request,

                    patient,
                    eligibility,
                    clinical,
                    utilization,
                    all_utilization,
                    policy,
                    pa_requirement,

                    status=PENDED,

                    reason_type=
                        "AMBIGUOUS",

                    reasoning=reasoning,

                    chroma_evidence=
                        chroma_evidence
                )


        finally:

            conn.close()


# ============================================================
# CONSOLE INPUT
# ============================================================

def get_console_input():

    print("\n")
    print("=" * 75)
    print(" PRIOR AUTHORIZATION DECISION ENGINE")
    print("=" * 75)

    print(
        "\nEnter PA request information.\n"
    )


    patient_id = input(
        "Patient ID: "
    ).strip()


    requested_hcpcs = input(
        "Requested HCPCS/CPT: "
    ).strip()


    diagnosis_icd10 = input(
        "Diagnosis ICD-10: "
    ).strip()


    ordering_physician = input(
        "Ordering physician: "
    ).strip()


    signed_order_date = input(
        "Signed order date (YYYY-MM-DD): "
    ).strip()


    provider_rationale = input(
        "Clinical rationale (optional): "
    ).strip()


    return {

        "patient_id":
            patient_id,

        "requested_hcpcs":
            requested_hcpcs,

        "diagnosis_icd10":
            diagnosis_icd10,

        "ordering_physician":
            ordering_physician,

        "signed_order_date":
            signed_order_date,

        "provider_rationale":
            provider_rationale
    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(result):

    print("\n")
    print("=" * 85)
    print(" PA DECISION RESULT")
    print("=" * 85)


    print(
        f"\nRequest ID : "
        f"{result.get('request_id')}"
    )


    print(
        f"Decision   : "
        f"{result.get('status')}"
    )


    print(
        f"Reason     : "
        f"{result.get('reason_type')}"
    )


    print(
        "\nDeterministic Reasoning:"
    )

    print(
        result.get("reasoning")
    )


    print(
        "\nHuman Review Required : "
        f"{result.get('requires_human_review')}"
    )


    llm = result.get(
        "llm_explanation"
    )


    if not llm:
        return


    print("\n")
    print("-" * 85)
    print(" LLM EXPLANATION")
    print("-" * 85)


    print(
        f"\nProvider : "
        f"{llm.get('_provider', 'NONE')}"
    )


    # ========================================================
    # 1
    # ========================================================

    print("\n")
    print(
        "1. DECISION SUMMARY"
    )

    print("-" * 85)

    print(
        llm.get(
            "decision_summary",
            "Not available"
        )
    )


    # ========================================================
    # 2
    # ========================================================

    print("\n")
    print(
        "2. DETERMINISTIC DECISION BASIS"
    )

    print("-" * 85)

    print(
        llm.get(
            "deterministic_decision_basis",
            "Not available"
        )
    )


    # ========================================================
    # 3
    # ========================================================

    print("\n")
    print(
        "3. POLICY EVIDENCE"
    )

    print("-" * 85)


    policy = llm.get(
        "policy_evidence",
        []
    )


    if policy:

        for item in policy:

            print(
                f"  - {item}"
            )

    else:

        print(
            "  - None explicitly identified"
        )


    # ========================================================
    # 4
    # ========================================================

    print("\n")
    print(
        "4. PATIENT / CLINICAL EVIDENCE"
    )

    print("-" * 85)


    clinical = llm.get(
        "patient_clinical_evidence",
        []
    )


    if clinical:

        for item in clinical:

            print(
                f"  - {item}"
            )

    else:

        print(
            "  - None explicitly identified"
        )


    # ========================================================
    # 5
    # ========================================================

    print("\n")
    print(
        "5. EVIDENCE RELATIONSHIP"
    )

    print("-" * 85)


    relationship = llm.get(
        "evidence_relationship",
        []
    )


    if relationship:

        for item in relationship:

            print(
                f"  - {item}"
            )

    else:

        print(
            "  - None explicitly identified"
        )


    # ========================================================
    # 6
    # ========================================================

    print("\n")
    print(
        "6. COVERAGE INTERPRETATION"
    )

    print("-" * 85)

    print(
        llm.get(
            "coverage_interpretation",
            "Not available"
        )
    )


    # ========================================================
    # 7
    # ========================================================

    print("\n")
    print(
        "7. MISSING INFORMATION"
    )

    print("-" * 85)


    missing = llm.get(
        "missing_information",
        []
    )


    if missing:

        for item in missing:

            print(
                f"  - {item}"
            )

    else:

        print(
            "  - None identified"
        )


    # ========================================================
    # 8
    # ========================================================

    print("\n")
    print(
        "8. RISK / REVIEW FLAGS"
    )

    print("-" * 85)


    flags = llm.get(
        "risk_review_flags",
        []
    )


    if flags:

        for item in flags:

            print(
                f"  - {item}"
            )

    else:

        print(
            "  - None"
        )


    # ========================================================
    # 9
    # ========================================================

    print("\n")
    print(
        "9. HUMAN REVIEW NOTE"
    )

    print("-" * 85)

    print(
        llm.get(
            "human_review_note",
            "Not available"
        )
    )


    # ========================================================
    # 10
    # ========================================================

    print("\n")
    print(
        "10. FINAL AUTHORITATIVE RESULT"
    )

    print("-" * 85)

    print(
        f"Decision: {result.get('status')}"
    )

    print(
        f"Reason: {result.get('reason_type')}"
    )


    print("\n")
    print("=" * 85)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # DATABASE CONFIG
    # --------------------------------------------------------

    if not DB_CONFIG["user"]:

        raise RuntimeError(
            "DB_USER is not configured in .env"
        )


    if not DB_CONFIG["password"]:

        raise RuntimeError(
            "DB_PASSWORD is not configured in .env"
        )


    # --------------------------------------------------------
    # DISPLAY CONFIGURATION
    # --------------------------------------------------------

    print("\nLLM configuration:")

    print(
        f"Primary  : OpenAI / {PRIMARY_MODEL}"
    )

    print(
        f"Fallback : Gemini / {GEMINI_MODEL}"
    )

    print(
        f"Fallback : Groq / {GROQ_MODEL}"
    )


    # --------------------------------------------------------
    # ENGINE
    # --------------------------------------------------------

    engine = DecisionEngine(
        DB_CONFIG
    )


    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    while True:

        request = get_console_input()


        try:

            result = engine.evaluate(

                patient_id=request[
                    "patient_id"
                ],

                requested_hcpcs=request[
                    "requested_hcpcs"
                ],

                diagnosis_icd10=request[
                    "diagnosis_icd10"
                ],

                ordering_physician=request[
                    "ordering_physician"
                ],

                signed_order_date=request[
                    "signed_order_date"
                ],

                provider_rationale=request[
                    "provider_rationale"
                ]
            )


            print_result(
                result
            )


        except Exception as exc:

            print(
                "\nENGINE ERROR"
            )

            print(
                type(exc).__name__
            )

            print(
                str(exc)
            )


        again = input(
            "\nTest another PA request? (y/n): "
        ).strip().lower()


        if again != "y":

            break