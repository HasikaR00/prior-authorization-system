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

load_dotenv()


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
    "openai/gpt-oss-120b"
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
# LLM OUTPUT FIELDS
# ============================================================

LLM_REQUIRED_FIELDS = [

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
You are the EXPLANATION LAYER of a Prior Authorization system.

You are NOT the decision maker.

The deterministic MySQL engine has already made the decision.

Your job is ONLY to explain that decision using the supplied
database evidence.

============================================================
ABSOLUTE RULES
============================================================

1. NEVER change the deterministic decision.

2. NEVER recommend a different final decision.

3. NEVER invent coverage rules.

4. NEVER invent patient information.

5. NEVER invent physician information.

6. NEVER invent insurance information.

7. NEVER invent policy criteria.

8. NEVER use external medical knowledge.

9. Use ONLY the supplied payload.

10. If evidence is unavailable, explicitly state that it
    is unavailable.

11. Do NOT turn missing evidence into evidence of absence.

12. Do NOT claim medical necessity failed unless the supplied
    policy evidence explicitly says that a criterion failed.

13. Missing documentation is NOT the same as medical-necessity
    failure.

14. NOT_REQUIRED is NOT DENIED.

15. RETRACTED is NOT an original denial.

16. If a diagnosis is explicitly listed as non-covered in the
    supplied policy evidence, explain that exact fact.

17. If deterministic decision is INFO_REQUESTED because of
    explicit non-coverage, explain that the system requires
    additional justification or human review according to
    the deterministic rule.

18. If deterministic decision is PENDED_NURSE_REVIEW because
    policy is unavailable or ambiguous, explain that policy
    evidence is insufficient for automated processing.

19. If deterministic decision is APPROVED, explain the exact
    supplied evidence supporting the deterministic criteria.

20. If deterministic decision is NOT_REQUIRED, explain that
    the configured PA requirement rule says authorization is
    unnecessary.

21. If deterministic decision is RETRACTED, explain that this
    is a lifecycle/retraction event rather than a new denial.

22. Do not provide treatment recommendations.

23. Do not diagnose the patient.

24. Do not expose hidden chain-of-thought.

25. Provide a detailed reviewer-facing explanation.
For APPROVED requests:

- Clearly explain why the deterministic criteria were satisfied.
- Connect the requested HCPCS, diagnosis, active policy article,
  patient history, and utilization evidence.
- Explain the evidence relationship in natural reviewer-facing language.
- You may state that the request satisfies the configured coverage
  criteria when the supplied evidence supports that conclusion.
- Do NOT make a broader clinical claim that is not present in the
  supplied evidence.
- Do NOT independently determine medical necessity.

============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON.

The JSON must contain exactly these fields:

{
  "decision_summary": "...",
  "deterministic_decision_basis": "...",
  "policy_evidence": ["..."],
  "patient_clinical_evidence": ["..."],
  "evidence_relationship": ["..."],
  "coverage_interpretation": "...",
  "missing_information": ["..."],
  "risk_review_flags": ["..."],
  "human_review_note": "..."
}

Do not add additional fields.
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
            FROM article_hcpc
            WHERE hcpc_code = %s
            """,
            (hcpcs_code,)
        )

        return cur.fetchall()


    # ========================================================
    # ARTICLE
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
            FROM article_policy
            WHERE article_id = %s
              AND article_version = %s
            """,
            (
                article_id,
                article_version
            )
        )

        return cur.fetchone()


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
                article_id,
                article_version,
                icd10_code,
                covered_group,
                description
            FROM article_icd10_covered
            WHERE article_id = %s
              AND article_version = %s
              AND icd10_code = %s
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
                icd10_code,
                noncovered_group,
                description
            FROM article_icd10_noncovered
            WHERE article_id = %s
              AND article_version = %s
              AND icd10_code = %s
            """,
            (
                article_id,
                article_version,
                icd10_code
            )
        )

        return cur.fetchone()


    # ========================================================
    # POLICY RESOLUTION
    # ========================================================

    def _resolve_policy(
        self,
        cur,
        hcpcs,
        icd10
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

            article_version = article[
                "article_version"
            ]


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


            matches.append({

                "article_id":
                    article_id,

                "article_version":
                    article_version,

                "article_title":
                    policy["title"],

                "status":
                    policy["status"],

                "covered":
                    covered,

                "noncovered":
                    noncovered
            })


        return {
            "result": "FOUND",
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

    def _call_groq(
        self,
        payload
    ):

        if not self.groq_client:

            raise RuntimeError(
                "Groq client unavailable"
            )


        response = (
            self.groq_client
            .chat
            .completions
            .create(

                model=GROQ_MODEL,

                messages=[

                    {
                        "role":
                            "system",

                        "content":
                            LLM_SYSTEM_PROMPT
                    },

                    {
                        "role":
                            "user",

                        "content":
                            json.dumps(
                                payload,
                                default=str
                            )
                    }

                ],

                temperature=0,

                max_tokens=1800,

                response_format={
                    "type":
                        "json_object"
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
                "Groq returned empty response"
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

            output["decision_summary"],

            output["deterministic_decision_basis"],

            output["coverage_interpretation"],

            output["human_review_note"]

        ]).upper()


        # ----------------------------------------------------
        # APPROVED
        # ----------------------------------------------------

        if deterministic_status == APPROVED:

            if (
                "DENIED" in combined
                or
                "NOT COVERED" in combined
            ):

                raise ValueError(
                    "LLM contradicted APPROVED"
                )


        # ----------------------------------------------------
        # PENDED
        # ----------------------------------------------------

        elif deterministic_status == PENDED:

            if (
                "AUTOMATICALLY APPROVE"
                in combined
            ):

                raise ValueError(
                    "LLM contradicted PENDED"
                )


        # ----------------------------------------------------
        # INFO
        # ----------------------------------------------------

        elif deterministic_status == INFO:

            if (
                "AUTOMATICALLY APPROVE"
                in combined
            ):

                raise ValueError(
                    "LLM contradicted INFO_REQUESTED"
                )


        # ----------------------------------------------------
        # NOT REQUIRED
        # ----------------------------------------------------

        elif deterministic_status == NOT_REQUIRED:

            if (
                "DENIED" in combined
                or
                "PENDED" in combined
            ):

                raise ValueError(
                    "LLM contradicted NOT_REQUIRED"
                )


        # ----------------------------------------------------
        # Attach authoritative metadata
        # ----------------------------------------------------

        output["_authoritative_status"] = (
            deterministic_status
        )

        output["_authoritative_reason"] = (
            deterministic_reason
        )


        return output


    # ========================================================
    # PROVIDER FALLBACK
    # ========================================================

    def _generate_llm_explanation(
        self,
        payload
    ):

        providers = [

            (
                "OpenAI",
                self._call_openai
            ),

            (
                "Gemini",
                self._call_gemini
            ),

            (
                "Groq",
                self._call_groq
            )
        ]


        errors = []


        for provider_name, provider_function in providers:

            # ------------------------------------------------
            # Don't print failure details to final user.
            # ------------------------------------------------

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

                    "provider":
                        provider_name,

                    "error":
                        f"{type(exc).__name__}: {str(exc)}"
                }


                errors.append(error)


                # ------------------------------------------------
                # SILENT FALLBACK
                # ------------------------------------------------

                continue


        # ====================================================
        # ALL PROVIDERS FAILED
        # ====================================================

        return {

            "decision_summary":
                "A detailed LLM explanation could not be generated. "
                "The deterministic database decision remains authoritative.",

            "deterministic_decision_basis":
                payload["decision"]["deterministic_reasoning"],

            "policy_evidence": [

                "LLM explanation unavailable; inspect the supplied "
                "database policy evidence directly."
            ],

            "patient_clinical_evidence": [

                "LLM explanation unavailable; inspect the supplied "
                "patient and clinical evidence directly."
            ],

            "evidence_relationship": [

                "The deterministic engine remains the authoritative "
                "source for the final PA status."
            ],

            "coverage_interpretation":
                "No LLM interpretation was available. "
                "The deterministic decision remains authoritative.",

            "missing_information": [],

            "risk_review_flags": [

                "LLM_UNAVAILABLE"
            ],

            "human_review_note":
                "All configured LLM providers were unavailable. "
                "Review the deterministic result and database evidence.",

            "_provider":
                "NONE",

            # Keep technical errors INTERNAL.
            "_errors":
                errors
        }


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
                # 6. POLICY
                # =================================================

                policy = (
                    self._resolve_policy(

                        cur,

                        requested_hcpcs,

                        diagnosis_icd10
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

                        reason_type=
                            "RULE_NOT_FOUND",

                        reasoning=reasoning,

                        chroma_evidence=
                            chroma_evidence
                    )


                matches = policy[
                    "matches"
                ]


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

                        reason_type=
                            "NO_ACTIVE_POLICY_MATCH",

                        reasoning=reasoning,

                        chroma_evidence=
                            chroma_evidence
                    )


                # =================================================
                # 10. COVERED / NON-COVERED
                # =================================================

                covered_matches = [

                    m

                    for m in matches

                    if m["covered"] is not None
                ]


                noncovered_matches = [

                    m

                    for m in matches

                    if m["noncovered"] is not None
                ]


                # =================================================
                # 11. NON-COVERED
                # =================================================

                if (
                    not covered_matches
                    and
                    noncovered_matches
                ):

                    m = noncovered_matches[0]


                    reasoning = (

                        f"Diagnosis {diagnosis_icd10} "
                        "is explicitly listed as non-covered "
                        "in article "
                        f"{m['article_id']} "
                        f"version {m['article_version']}. "

                        "This is not treated as an automatic "
                        "denial. Additional clinical "
                        "justification or human review "
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

                        status=INFO,

                        reason_type=
                            "NONCOVERED_DIAGNOSIS",

                        reasoning=reasoning,

                        chroma_evidence=
                            chroma_evidence
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