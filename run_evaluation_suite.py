import sys
import os
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.db import SYSTEM_DB_CONFIG
from backend.eval_logger import EvaluatedDecisionEngine

# 15 Test Cases spanning unconditional, conditional, noncovered, and rule-not-found scenarios
TEST_CASES = [
    # Unconditional Covered Scenarios
    {"id": "TC01", "patient_id": "0133267a-6406-a01b-8d4a-f60993b1e3ca", "hcpcs": "70450", "icd10": "G44.1", "physician": "Dr. Sarah Jenkins", "date": "2026-08-01", "rationale": "Severe headache evaluation", "category": "unconditional"},
    {"id": "TC02", "patient_id": "01a006ce-6457-50c2-8e0a-fb58fc310a86", "hcpcs": "70450", "icd10": "S06.5X0A", "physician": "Dr. Mark Thorne", "date": "2026-08-02", "rationale": "Traumatic brain injury workup", "category": "unconditional"},
    {"id": "TC03", "patient_id": "0582e289-d8d6-738b-bf47-3da4f26f6f34", "hcpcs": "70551", "icd10": "G35", "physician": "Dr. Elena Rostova", "date": "2026-08-03", "rationale": "Multiple sclerosis screening", "category": "unconditional"},
    {"id": "TC04", "patient_id": "062ce52a-5823-aeb4-e0d1-d514baf42a38", "hcpcs": "70551", "icd10": "C79.31", "physician": "Dr. James Wilson", "date": "2026-08-04", "rationale": "Brain metastasis evaluation", "category": "unconditional"},

    # Conditional Covered Scenarios
    {"id": "TC05", "patient_id": "08d6836a-cefb-bc53-c8c2-cb0ee6c5e53d", "hcpcs": "93458", "icd10": "I25.10", "physician": "Dr. Robert Chen", "date": "2026-08-05", "rationale": "Coronary artery disease evaluation with angina notes", "category": "conditional"},
    {"id": "TC06", "patient_id": "09c92ce0-6ff1-7234-956d-33795ad6648c", "hcpcs": "93458", "icd10": "I20.0", "physician": "Dr. Anita Patel", "date": "2026-08-06", "rationale": "Unstable angina pectoris diagnostic cardiac catheterization", "category": "conditional"},
    {"id": "TC07", "patient_id": "0fb515d6-ec2d-33f3-512e-7615b6e3091d", "hcpcs": "72148", "icd10": "M54.5", "physician": "Dr. David Miller", "date": "2026-08-07", "rationale": "Lumbar radiculopathy following conservative physical therapy", "category": "conditional"},
    {"id": "TC08", "patient_id": "1060044a-f072-f905-e067-c67d12ad8e6b", "hcpcs": "72148", "icd10": "M51.16", "physician": "Dr. Lisa Wong", "date": "2026-08-08", "rationale": "Intervertebral disc degeneration lumbar spine", "category": "conditional"},

    # Noncovered Scenarios
    {"id": "TC09", "patient_id": "13472219-c176-990a-641f-14cf9d4d8480", "hcpcs": "70450", "icd10": "R51", "physician": "Dr. Alan Grant", "date": "2026-08-09", "rationale": "Unspecified headache", "category": "noncovered"},
    {"id": "TC10", "patient_id": "139cd667-593c-c80f-ece7-7561016c43db", "hcpcs": "93458", "icd10": "R07.9", "physician": "Dr. Ellie Sattler", "date": "2026-08-10", "rationale": "Unspecified chest pain", "category": "noncovered"},
    {"id": "TC11", "patient_id": "0133267a-6406-a01b-8d4a-f60993b1e3ca", "hcpcs": "72148", "icd10": "M54.9", "physician": "Dr. Ian Malcolm", "date": "2026-08-11", "rationale": "Dorsalgia unspecified", "category": "noncovered"},
    {"id": "TC12", "patient_id": "01a006ce-6457-50c2-8e0a-fb58fc310a86", "hcpcs": "70551", "icd10": "R42", "physician": "Dr. Henry Wu", "date": "2026-08-12", "rationale": "Dizziness and giddiness", "category": "noncovered"},

    # Rule-Not-Found / Missing Policy Scenarios
    {"id": "TC13", "patient_id": "0582e289-d8d6-738b-bf47-3da4f26f6f34", "hcpcs": "99999", "icd10": "Z00.00", "physician": "Dr. Claire Dearing", "date": "2026-08-13", "rationale": "Unlisted procedure code test", "category": "rule-not-found"},
    {"id": "TC14", "patient_id": "062ce52a-5823-aeb4-e0d1-d514baf42a38", "hcpcs": "00000", "icd10": "Z01.89", "physician": "Dr. Owen Grady", "date": "2026-08-14", "rationale": "Non-existent service code", "category": "rule-not-found"},
    {"id": "TC15", "patient_id": "08d6836a-cefb-bc53-c8c2-cb0ee6c5e53d", "hcpcs": "78815", "icd10": "Z99.9", "physician": "Dr. Simon Masrani", "date": "2026-08-15", "rationale": "PET scan without matching policy", "category": "rule-not-found"},
]

def run_evaluation():
    print("==================================================================")
    print("PRIOR AUTHORIZATION DECISION ENGINE - EVALUATION SUITE")
    print("==================================================================")
    print(f"Running {len(TEST_CASES)} test cases x 3 iterations = {len(TEST_CASES)*3} evaluations...\n")

    engine = EvaluatedDecisionEngine(SYSTEM_DB_CONFIG)

    case_results = {}
    total_evals = 0
    decision_counts = {}
    human_in_loop_count = 0
    contradiction_count = 0
    matching_article_count = 0

    total_engine_time = 0
    total_llm_time = 0
    total_time = 0
    provider_counts = {}

    for tc in TEST_CASES:
        tc_id = tc["id"]
        case_results[tc_id] = []

        for run_idx in range(3):
            total_evals += 1
            res = engine.evaluate(
                patient_id=tc["patient_id"],
                requested_hcpcs=tc["hcpcs"],
                diagnosis_icd10=tc["icd10"],
                ordering_physician=tc["physician"],
                signed_order_date=tc["date"],
                provider_rationale=tc["rationale"]
            )
            
            case_results[tc_id].append(res)

            status = res.get("status", "UNKNOWN")
            decision_counts[status] = decision_counts.get(status, 0) + 1

            if res.get("requires_human_review", True):
                human_in_loop_count += 1

            llm_exp = res.get("llm_explanation") or {}
            prov = llm_exp.get("_provider", "UNKNOWN") if isinstance(llm_exp, dict) else "UNKNOWN"
            provider_counts[prov] = provider_counts.get(prov, 0) + 1

            # Check matching policy article presence
            if res.get("reason_type") not in ("RULE_NOT_FOUND", "NO_ACTIVE_POLICY_MATCH"):
                if run_idx == 0:
                    matching_article_count += 1

    # Check determinism per test case
    deterministic_cases = 0
    for tc_id, runs in case_results.items():
        s0 = runs[0].get("status")
        r0 = runs[0].get("reason_type")
        if all(r.get("status") == s0 and r.get("reason_type") == r0 for r in runs):
            deterministic_cases += 1

    # Query metrics from eval_run_log table
    conn = engine._conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT AVG(engine_time_ms), AVG(llm_time_ms), AVG(total_time_ms), SUM(contradiction_detected) FROM eval_run_log")
            avg_eng, avg_llm, avg_tot, contra_sum = cur.fetchone().values()
            total_engine_time = float(avg_eng or 0)
            total_llm_time = float(avg_llm or 0)
            total_time = float(avg_tot or 0)
            contradiction_count = int(contra_sum or 0)
    except Exception as e:
        print(f"Metrics query notice: {e}")
    finally:
        conn.close()

    print("==================================================================")
    print("EVALUATION SUITE SUMMARY REPORT")
    print("==================================================================")
    print(f"1. Determinism Score:         {deterministic_cases}/{len(TEST_CASES)} cases returned identical status & reason across 3 runs")
    print(f"2. Policy Rule Coverage:      {matching_article_count}/{len(TEST_CASES)} cases matched an active policy article")
    print(f"3. Human-in-Loop Compliance:  {human_in_loop_count}/{total_evals} evaluations flagged for human confirmation")
    print(f"4. Contradiction Flag Rate:   {contradiction_count}/{total_evals} explanations flagged for banned phrasing (Target: 0)")
    print("\n5. Decision Distribution:")
    for stat, count in decision_counts.items():
        print(f"   - {stat}: {count}")
    print("\n6. Performance & Timing Metrics:")
    print(f"   - Avg Engine (MySQL) Time: {total_engine_time:.1f} ms")
    print(f"   - Avg LLM Explanation Time:{total_llm_time:.1f} ms")
    print(f"   - Avg Total End-to-End Time:{total_time:.1f} ms")
    print("\n7. LLM Provider Usage Breakdown:")
    for prov, count in provider_counts.items():
        print(f"   - {prov}: {count} responses")
    print("==================================================================")

if __name__ == "__main__":
    run_evaluation()
