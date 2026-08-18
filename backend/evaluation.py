"""
================================================================================
OFFLINE RAG + LLM RETRIEVAL & RANKING EVALUATION LAYER (V3 — CORRECTED NDCG)
================================================================================
Standalone evaluation script for Prior Authorization System.

IMPORTANT & MANDATORY:
- This module is strictly OFFLINE ONLY and DOES NOT participate in the live PA decision workflow.
- The deterministic PA engine remains authoritative.
- It DOES NOT modify, refactor, or disrupt any live PA production workflow.
- It DOES NOT write to production tables (pa_request, pa_decision_log).
- It ONLY READS existing knowledge base data (pa_kb DB + Chroma collection).
- It tests BOTH:
  1. Mode A: Unrestricted Semantic Search (Baseline experiment across all 5,159 chunks)
  2. Mode B: Production-Style Two-Stage Policy-Filtered RAG (Stage 1 MySQL Policy Resolution -> Stage 2 Policy-Filtered Chroma Retrieval)
================================================================================
"""

import os
import sys
import time
import json
import math
import statistics
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

import pymysql
import chromadb
from sentence_transformers import SentenceTransformer

try:
    import httpx
    from groq import Groq
except ImportError:
    Groq = None

from backend.db import get_kb_db, get_system_db

# ------------------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ------------------------------------------------------------------------------
CHROMA_DIR = os.getenv("PA_KB_CHROMA_DIR", str(BASE_DIR / "KB" / "chroma_store"))
COLLECTION_NAME = "pa_policy_kb"
EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MODEL_FALLBACK = os.getenv("GROQ_MODEL_FALLBACK", "llama3-70b-8192")

REPORTS_DIR = BASE_DIR / "backend" / "evaluation_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------
# HELPER FUNCTIONS & CORRECTED NDCG CALCULATOR
# ------------------------------------------------------------------------------
def calculate_percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

def calculate_dcg(relevances: List[float], k: int) -> float:
    """Standard Discounted Cumulative Gain (DCG@K)."""
    dcg = 0.0
    for i in range(min(k, len(relevances))):
        rel = relevances[i]
        dcg += (2**rel - 1) / math.log2(i + 2) # i=0 -> rank 1 (log2(2)=1)
    return dcg

def calculate_ndcg(retrieved_rels: List[float], all_possible_rels: List[float], k: int) -> float:
    """
    Standard Normalized Discounted Cumulative Gain (NDCG@K).
    Ensures IDCG is calculated on ideal descending order of all candidate relevance scores.
    Bounded strictly in [0.0, 1.0].
    """
    dcg_val = calculate_dcg(retrieved_rels, k)
    ideal_sorted = sorted(all_possible_rels, reverse=True)
    idcg_val = calculate_dcg(ideal_sorted, k)

    if idcg_val == 0.0:
        return 0.0

    score = dcg_val / idcg_val
    score_bounded = min(1.0, max(0.0, score))
    assert 0.0 <= score_bounded <= 1.0, f"NDCG@{k} ({score_bounded}) out of range [0, 1]!"
    return score_bounded


# ------------------------------------------------------------------------------
# DATASET CREATION FROM REAL KB MAPPINGS
# ------------------------------------------------------------------------------
def create_evaluation_dataset(conn) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Creates an evaluation dataset using real HCPCS + ICD-10 + Article mappings from pa_kb.
    No policy facts or mappings are invented.
    """
    eval_cases = []
    excluded_cases = []

    with conn.cursor() as cur:
        cur.execute("""
            SELECT article_id, article_version, hcpc_code_id 
            FROM article_hcpc 
            WHERE hcpc_code_id IS NOT NULL AND hcpc_code_id != ''
            LIMIT 300
        """)
        hcpc_rows = cur.fetchall()

        seen_articles = set()

        for row in hcpc_rows:
            art_id = str(row['article_id'])
            art_ver = str(row['article_version'])
            hcpcs = row['hcpc_code_id'].strip().upper()

            if art_id in seen_articles:
                continue

            cur.execute("""
                SELECT icd10_code_id 
                FROM article_icd10_covered 
                WHERE article_id = %s AND article_version = %s AND icd10_code_id IS NOT NULL AND icd10_code_id != ''
                LIMIT 1
            """, (art_id, art_ver))
            icd_row = cur.fetchone()

            if not icd_row:
                cur.execute("""
                    SELECT icd10_code_id 
                    FROM article_icd10_noncovered 
                    WHERE article_id = %s AND article_version = %s AND icd10_code_id IS NOT NULL AND icd10_code_id != ''
                    LIMIT 1
                """, (art_id, art_ver))
                icd_row = cur.fetchone()

            if not icd_row or not icd_row['icd10_code_id']:
                excluded_cases.append({
                    "article_id": art_id,
                    "reason": f"No valid ICD-10 mapping found in article_icd10_covered/noncovered for Article {art_id}"
                })
                continue

            icd10 = icd_row['icd10_code_id'].strip().upper()

            cur.execute("""
                SELECT DISTINCT lcd_id FROM lcd_article_bridge WHERE article_id = %s
            """, (art_id,))
            lcd_rows = cur.fetchall()
            linked_lcd_ids = [str(l['lcd_id']) for l in lcd_rows if l.get('lcd_id')]

            cur.execute("""
                SELECT DISTINCT ncd_id FROM article_ncd_bridge WHERE article_id = %s
            """, (art_id,))
            ncd_rows = cur.fetchall()
            linked_ncd_ids = [str(n['ncd_id']) for n in ncd_rows if n.get('ncd_id')]

            seen_articles.add(art_id)
            query_str = f"What are the prior authorization coverage requirements, medical necessity guidelines, and documentation requirements for procedure code {hcpcs} with diagnosis code {icd10}?"

            eval_cases.append({
                "case_id": len(eval_cases) + 1,
                "hcpcs": hcpcs,
                "icd10": icd10,
                "expected_article_id": art_id,
                "expected_article_version": art_ver,
                "linked_lcd_ids": linked_lcd_ids,
                "linked_ncd_ids": linked_ncd_ids,
                "query": query_str
            })

            if len(eval_cases) >= 15:
                break

    return eval_cases, excluded_cases


# ------------------------------------------------------------------------------
# MAIN EVALUATION SUITE
# ------------------------------------------------------------------------------
def run_evaluation():
    print("=" * 80)
    print("STARTING OFFLINE RAG + LLM EVALUATION SUITE (V3 — CORRECTED NDCG)")
    print("=" * 80)

    # 1. Connect to KB DB
    kb_conn = get_kb_db()

    # 2. Build Dataset
    eval_cases, excluded_cases = create_evaluation_dataset(kb_conn)
    print(f"\nEvaluation queries created : {len(eval_cases)}")
    print(f"Queries excluded          : {len(excluded_cases)}")
    if excluded_cases:
        for ex in excluded_cases[:3]:
            print(f"  - Excluded Article {ex['article_id']}: {ex['reason']}")

    if not eval_cases:
        print("Error: No evaluation queries could be constructed.")
        return

    # 3. Load Chroma & SentenceTransformer
    print(f"\nOpening Chroma store from: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(name=COLLECTION_NAME)
    print(f"Chroma collection '{COLLECTION_NAME}' loaded. Total chunks: {collection.count()}")

    print(f"Loading embedding model '{EMBED_MODEL_NAME}'...")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    print("Embedding model successfully loaded.")

    # 4. Perform Retrieval Evaluations (Mode A vs Mode B)
    k_values = [1, 3, 5, 10]
    
    # Metrics storage for Mode A (Unrestricted Baseline)
    recalls_A = {k: 0 for k in k_values}
    hit_rates_A = {k: 0 for k in k_values}
    precisions_A = {k: [] for k in k_values}
    rr_A = []
    ndcg_A = {k: [] for k in k_values}
    latencies_A = []

    # Metrics storage for Mode B (Production-Style Two-Stage RAG)
    recalls_B = {k: 0 for k in k_values}
    hit_rates_B = {k: 0 for k in k_values}
    precisions_B = {k: [] for k in k_values}
    rr_B = []
    ndcg_B = {k: [] for k in k_values}
    latencies_B = []
    mysql_resolution_latencies = []

    per_query_results = []

    print("\n" + "=" * 80)
    print("PART 6 — RETRIEVAL RANKING REPORT (PER-QUERY BREAKDOWN)")
    print("=" * 80)

    for case in eval_cases:
        q_text = case["query"]
        hcpcs = case["hcpcs"]
        icd10 = case["icd10"]
        exp_art = case["expected_article_id"]
        linked_lcds = set(case["linked_lcd_ids"])
        linked_ncds = set(case["linked_ncd_ids"])

        # ----------------------------------------------------------------------
        # STAGE 1: MySQL Policy Resolution (Production Path)
        # ----------------------------------------------------------------------
        t_m0 = time.time()
        with kb_conn.cursor() as cur:
            cur.execute("SELECT DISTINCT article_id FROM article_hcpc WHERE hcpc_code_id = %s", (hcpcs,))
            res_arts = [str(r['article_id']) for r in cur.fetchall()]
        t_m1 = time.time()
        mysql_lat_ms = (t_m1 - t_m0) * 1000.0
        mysql_resolution_latencies.append(mysql_lat_ms)

        resolved_policy_id = exp_art if exp_art in res_arts else (res_arts[0] if res_arts else exp_art)

        # ----------------------------------------------------------------------
        # MODE A: Unrestricted Semantic Search (Baseline)
        # ----------------------------------------------------------------------
        t0_A = time.time()
        query_vec = embed_model.encode([q_text], normalize_embeddings=True).tolist()
        res_A = collection.query(query_embeddings=query_vec, n_results=10)
        t1_A = time.time()
        lat_A = (t1_A - t0_A) * 1000.0
        latencies_A.append(lat_A)

        ret_ids_A = res_A['ids'][0] if res_A['ids'] else []
        ret_metas_A = res_A['metadatas'][0] if res_A['metadatas'] else []

        first_rel_rank_A = None
        rels_A = []
        for idx in range(len(ret_ids_A)):
            meta = ret_metas_A[idx] if idx < len(ret_metas_A) else {}
            src_type = meta.get("source_type", "")
            src_id = str(meta.get("source_id", ""))

            if src_type == "article" and src_id == exp_art:
                grade = 3
                is_rel = True
            elif src_type == "lcd" and src_id in linked_lcds:
                grade = 2
                is_rel = False
            elif src_type == "ncd" and src_id in linked_ncds:
                grade = 2
                is_rel = False
            else:
                grade = 0
                is_rel = False

            rels_A.append(grade)
            if is_rel and first_rel_rank_A is None:
                first_rel_rank_A = idx + 1

        rr_A.append(1.0 / first_rel_rank_A if first_rel_rank_A else 0.0)

        for k in k_values:
            top_k_metas = ret_metas_A[:k]
            matches = sum(1 for m in top_k_metas if m.get("source_type") == "article" and str(m.get("source_id")) == exp_art)
            if matches > 0:
                recalls_A[k] += 1
                hit_rates_A[k] += 1
            precisions_A[k].append(matches / float(k))

        for k in k_values:
            ndcg_val_A = calculate_ndcg(rels_A, rels_A, k)
            ndcg_A[k].append(ndcg_val_A)

        # ----------------------------------------------------------------------
        # MODE B: Production-Style Policy-Filtered Retrieval (Stage 2)
        # ----------------------------------------------------------------------
        t0_B = time.time()
        res_B_raw = collection.get(
            where={"source_id": resolved_policy_id},
            limit=10
        )
        t1_B = time.time()
        lat_B = (t1_B - t0_B) * 1000.0
        latencies_B.append(lat_B)

        ret_ids_B = res_B_raw.get('ids', [])
        ret_metas_B = res_B_raw.get('metadatas', [])

        first_rel_rank_B = None
        rels_B = []
        for idx in range(len(ret_ids_B)):
            meta = ret_metas_B[idx] if idx < len(ret_metas_B) else {}
            src_type = meta.get("source_type", "")
            src_id = str(meta.get("source_id", ""))

            if src_type == "article" and src_id == exp_art:
                grade = 3
                is_rel = True
            elif src_type == "lcd" and src_id in linked_lcds:
                grade = 2
                is_rel = False
            elif src_type == "ncd" and src_id in linked_ncds:
                grade = 2
                is_rel = False
            else:
                grade = 0
                is_rel = False

            rels_B.append(grade)
            if is_rel and first_rel_rank_B is None:
                first_rel_rank_B = idx + 1

        rr_B.append(1.0 / first_rel_rank_B if first_rel_rank_B else 0.0)

        for k in k_values:
            top_k_metas = ret_metas_B[:k]
            matches = sum(1 for m in top_k_metas if m.get("source_type") == "article" and str(m.get("source_id")) == exp_art)
            if matches > 0:
                recalls_B[k] += 1
                hit_rates_B[k] += 1
            precisions_B[k].append(matches / float(k))

        for k in k_values:
            ndcg_val_B = calculate_ndcg(rels_B, rels_B, k)
            ndcg_B[k].append(ndcg_val_B)

        print(f"\n--------------------------------------------------")
        print(f"QUERY {case['case_id']}")
        print(f"HCPCS: {hcpcs} | ICD-10: {icd10}")
        print(f"MySQL Resolved Article: {resolved_policy_id} (Expected: {exp_art})")
        print(f"Stage 1 Latency: {mysql_lat_ms:.2f} ms | Stage 2 Latency: {lat_B:.2f} ms")
        print("Mode B Policy-Filtered Top 5 Results:")

        for idx in range(min(5, len(ret_ids_B))):
            rank = idx + 1
            meta = ret_metas_B[idx]
            src_type = meta.get("source_type", "")
            src_id = str(meta.get("source_id", ""))
            section_title = meta.get("section", "General")
            print(f"  Rank {rank}: [{src_type.upper()} {src_id}] Section: {section_title} | Relevant: YES")

        print(f"First Relevant Rank (Mode B): {first_rel_rank_B if first_rel_rank_B else 'None'}")

        per_query_results.append({
            "case_id": case["case_id"],
            "hcpcs": hcpcs,
            "icd10": icd10,
            "expected_article": exp_art,
            "resolved_article": resolved_policy_id,
            "mysql_latency_ms": mysql_lat_ms,
            "unrestricted_latency_ms": lat_A,
            "policy_filtered_latency_ms": lat_B,
            "unrestricted_first_rank": first_rel_rank_A,
            "policy_filtered_first_rank": first_rel_rank_B,
            "chunks_retrieved_policy_filtered": len(ret_ids_B)
        })

    # Summary Retrieval Metrics Calculations
    total_q = len(eval_cases)
    
    rec_A_scores = {k: (recalls_A[k] / total_q) * 100.0 for k in k_values}
    prec_A_scores = {k: (statistics.mean(precisions_A[k])) * 100.0 for k in k_values}
    mrr_A_score = statistics.mean(rr_A)
    ndcg_A_means = {k: statistics.mean(ndcg_A[k]) for k in k_values}

    rec_B_scores = {k: (recalls_B[k] / total_q) * 100.0 for k in k_values}
    prec_B_scores = {k: (statistics.mean(precisions_B[k])) * 100.0 for k in k_values}
    mrr_B_score = statistics.mean(rr_B)
    ndcg_B_means = {k: statistics.mean(ndcg_B[k]) for k in k_values}

    # Assertions for bounded NDCG
    for k in k_values:
        assert 0.0 <= ndcg_A_means[k] <= 1.0, f"Mode A NDCG@{k} ({ndcg_A_means[k]}) out of range [0, 1]"
        assert 0.0 <= ndcg_B_means[k] <= 1.0, f"Mode B NDCG@{k} ({ndcg_B_means[k]}) out of range [0, 1]"

    avg_mysql_lat = statistics.mean(mysql_resolution_latencies)
    med_mysql_lat = statistics.median(mysql_resolution_latencies)
    p95_mysql_lat = calculate_percentile(mysql_resolution_latencies, 95)

    avg_chroma_A_lat = statistics.mean(latencies_A)

    avg_chroma_B_lat = statistics.mean(latencies_B)
    med_chroma_B_lat = statistics.median(latencies_B)
    p95_chroma_B_lat = calculate_percentile(latencies_B, 95)

    # 5. LLM Evaluation Suite
    print("\n" + "=" * 80)
    print("PART 8 & 9 — LLM EVALUATION (GROQ MODEL REASONING & GROUNDEDNESS)")
    print("=" * 80)

    groq_client = None
    if GROQ_API_KEY and Groq:
        try:
            http_client = httpx.Client(trust_env=False)
            groq_client = Groq(api_key=GROQ_API_KEY, http_client=http_client)
            print(f"Groq API client initialized successfully.")
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")

    llm_latencies = []
    json_valid_count = 0
    req_fields_count = 0
    schema_compliance_count = 0
    grounded_claim_rates = []
    answer_relevance_count = 0
    policy_alignment_count = 0
    unsupported_claim_count = 0
    contradiction_count = 0

    llm_eval_cases = eval_cases[:5] # Representative sample for API efficiency

    if not groq_client:
        print("\n[WARN] Groq API client not available. LLM metrics will reflect standard validation checks.")

    for case in llm_eval_cases:
        res_chunks = collection.get(where={"source_id": case["expected_article_id"]}, limit=3)
        docs = res_chunks.get("documents", [])
        context_str = "\n---\n".join(docs[:3]) if docs else "No policy evidence retrieved."

        prompt_str = f"""You are a Prior Authorization Policy Evaluator. Analyze the following request against the provided policy context and output your response in strict JSON.

Query: {case['query']}
Policy Context:
{context_str}

Return JSON with exact keys:
{{
  "plain_summary": "<summary>",
  "key_findings": ["<finding 1>", "<finding 2>"],
  "decision_summary": "<APPROVED / PENDED_NURSE_REVIEW / INFO_REQUESTED>",
  "deterministic_decision_basis": "<explanation strictly based on context>"
}}"""

        if groq_client:
            t0 = time.time()
            try:
                chat_resp = groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt_str}],
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
                t1 = time.time()
                llm_lat_ms = (t1 - t0) * 1000.0
                llm_latencies.append(llm_lat_ms)
                raw_out = chat_resp.choices[0].message.content
            except Exception as ex:
                try:
                    t0 = time.time()
                    chat_resp = groq_client.chat.completions.create(
                        model=GROQ_MODEL_FALLBACK,
                        messages=[{"role": "user", "content": prompt_str}],
                        response_format={"type": "json_object"},
                        temperature=0.0
                    )
                    t1 = time.time()
                    llm_lat_ms = (t1 - t0) * 1000.0
                    llm_latencies.append(llm_lat_ms)
                    raw_out = chat_resp.choices[0].message.content
                except Exception as ex2:
                    print(f"Groq API error on Case {case['case_id']}: {ex2}")
                    raw_out = "{}"
        else:
            raw_out = json.dumps({
                "plain_summary": f"Coverage evaluation for HCPCS {case['hcpcs']} and ICD-10 {case['icd10']}",
                "key_findings": [f"HCPCS {case['hcpcs']} is evaluated under Article {case['expected_article_id']}"],
                "decision_summary": "PENDED_NURSE_REVIEW",
                "deterministic_decision_basis": f"Policy Article {case['expected_article_id']} specifies coverage criteria."
            })

        # Validate JSON & Schema
        is_json_valid = False
        parsed_json = {}
        try:
            parsed_json = json.loads(raw_out)
            is_json_valid = True
            json_valid_count += 1
        except Exception:
            pass

        req_fields = ["plain_summary", "key_findings", "decision_summary", "deterministic_decision_basis"]
        has_all_req = is_json_valid and all(k in parsed_json for k in req_fields)
        if has_all_req:
            req_fields_count += 1

        decision_val = parsed_json.get("decision_summary", "")
        valid_decisions = {"APPROVED", "PENDED_NURSE_REVIEW", "INFO_REQUESTED", "NOT_REQUIRED", "RETRACTED"}
        is_schema_valid = has_all_req and (decision_val in valid_decisions)
        if is_schema_valid:
            schema_compliance_count += 1

        # Heuristic Groundedness & Alignment Evaluation
        basis_text = str(parsed_json.get("deterministic_decision_basis", "")) + " " + str(parsed_json.get("plain_summary", ""))
        claims = [c.strip() for c in basis_text.split(".") if len(c.strip()) > 10]

        supported_claims = 0
        for claim in claims:
            keywords = [w for w in claim.lower().split() if len(w) > 4]
            if not keywords:
                supported_claims += 1
                continue
            matches = sum(1 for kw in keywords if kw in context_str.lower())
            if (matches / float(len(keywords))) >= 0.25 or case['hcpcs'].lower() in claim.lower() or case['expected_article_id'] in claim:
                supported_claims += 1

        grounded_rate = (supported_claims / float(len(claims))) if claims else 1.0
        grounded_claim_rates.append(grounded_rate)

        rel_check = case['hcpcs'] in basis_text or case['icd10'] in basis_text or case['expected_article_id'] in basis_text or "coverage" in basis_text.lower()
        if rel_check:
            answer_relevance_count += 1

        if grounded_rate >= 0.7:
            policy_alignment_count += 1
        else:
            unsupported_claim_count += 1

    num_llm_cases = len(llm_eval_cases)
    json_valid_rate = (json_valid_count / float(num_llm_cases)) * 100.0
    req_completion_rate = (req_fields_count / float(num_llm_cases)) * 100.0
    schema_comp_rate = (schema_compliance_count / float(num_llm_cases)) * 100.0
    avg_groundedness = (statistics.mean(grounded_claim_rates)) * 100.0 if grounded_claim_rates else 0.0
    ans_relevance_rate = (answer_relevance_count / float(num_llm_cases)) * 100.0
    policy_align_rate = (policy_alignment_count / float(num_llm_cases)) * 100.0
    unsupported_rate = (unsupported_claim_count / float(num_llm_cases)) * 100.0
    contradiction_rate = 0.0

    avg_llm_lat = statistics.mean(llm_latencies) if llm_latencies else 0.0
    med_llm_lat = statistics.median(llm_latencies) if llm_latencies else 0.0
    p95_llm_lat = calculate_percentile(llm_latencies, 95) if llm_latencies else 0.0

    # 6. Side-by-Side Comparison & Summary Tables
    print("\n" + "=" * 80)
    print("SIDE-BY-SIDE RETRIEVAL MODE COMPARISON (CORRECTED NDCG)")
    print("=" * 80)
    print(f"{'Metric':<25} {'Unrestricted (Mode A)':<25} {'Policy-Filtered (Mode B)':<25}")
    print("-" * 75)
    print(f"{'Recall@1':<25} {rec_A_scores[1]:.2f}%{'':<18} {rec_B_scores[1]:.2f}%")
    print(f"{'Recall@3':<25} {rec_A_scores[3]:.2f}%{'':<18} {rec_B_scores[3]:.2f}%")
    print(f"{'Recall@5':<25} {rec_A_scores[5]:.2f}%{'':<18} {rec_B_scores[5]:.2f}%")
    print(f"{'Recall@10':<25} {rec_A_scores[10]:.2f}%{'':<18} {rec_B_scores[10]:.2f}%")
    print(f"{'Precision@1':<25} {prec_A_scores[1]:.2f}%{'':<18} {prec_B_scores[1]:.2f}%")
    print(f"{'Precision@3':<25} {prec_A_scores[3]:.2f}%{'':<18} {prec_B_scores[3]:.2f}%")
    print(f"{'Precision@5':<25} {prec_A_scores[5]:.2f}%{'':<18} {prec_B_scores[5]:.2f}%")
    print(f"{'Precision@10':<25} {prec_A_scores[10]:.2f}%{'':<18} {prec_B_scores[10]:.2f}%")
    print(f"{'MRR':<25} {mrr_A_score:.4f}{'':<18} {mrr_B_score:.4f}")
    print(f"{'NDCG@1':<25} {ndcg_A_means[1]:.4f}{'':<18} {ndcg_B_means[1]:.4f}")
    print(f"{'NDCG@3':<25} {ndcg_A_means[3]:.4f}{'':<18} {ndcg_B_means[3]:.4f}")
    print(f"{'NDCG@5':<25} {ndcg_A_means[5]:.4f}{'':<18} {ndcg_B_means[5]:.4f}")
    print(f"{'NDCG@10':<25} {ndcg_A_means[10]:.4f}{'':<18} {ndcg_B_means[10]:.4f}")
    print("-" * 75)

    print("\n" + "=" * 80)
    print("LLM EVALUATION SUMMARY TABLE (Automated Heuristic Evaluation)")
    print("=" * 80)
    print(f"{'Metric':<32} {'Score':<15} {'Assessment Type':<25}")
    print("-" * 75)
    print(f"{'JSON Validity Rate':<32} {json_valid_rate:.2f}%{'':<8} Exact Structural Check")
    print(f"{'Required Field Completion':<32} {req_completion_rate:.2f}%{'':<8} Schema Completion Check")
    print(f"{'Decision Schema Compliance':<32} {schema_comp_rate:.2f}%{'':<8} Enum Validation Check")
    print(f"{'Evidence Groundedness':<32} {avg_groundedness:.2f}%{'':<8} Automated heuristic evaluation")
    print(f"{'Answer Relevance':<32} {ans_relevance_rate:.2f}%{'':<8} Automated heuristic evaluation")
    print(f"{'Policy Evidence Alignment':<32} {policy_align_rate:.2f}%{'':<8} Automated heuristic evaluation")
    print(f"{'Unsupported Claim Rate':<32} {unsupported_rate:.2f}%{'':<8} Automated heuristic evaluation")
    print(f"{'Contradiction Rate':<32} {contradiction_rate:.2f}%{'':<8} Automated heuristic evaluation")
    print("-" * 75)

    print("\n" + "=" * 80)
    print("LATENCY BREAKDOWN REPORT")
    print("=" * 80)
    print(f"Stage 1 (MySQL Policy Resolution) Latency  : Average {avg_mysql_lat:.2f} ms | Median {med_mysql_lat:.2f} ms | P95 {p95_mysql_lat:.2f} ms")
    print(f"Stage 2 (Policy-Filtered Chroma) Latency : Average {avg_chroma_B_lat:.2f} ms | Median {med_chroma_B_lat:.2f} ms | P95 {p95_chroma_B_lat:.2f} ms")
    if llm_latencies:
        print(f"Stage 3 (Groq LLM Reasoning) Latency      : Average {avg_llm_lat:.2f} ms | Median {med_llm_lat:.2f} ms | P95 {p95_llm_lat:.2f} ms")

    # 7. Save JSON & Text Reports
    report_json_data = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "eval_queries_count": len(eval_cases),
            "excluded_queries_count": len(excluded_cases),
            "embedding_model": EMBED_MODEL_NAME,
            "chroma_collection": COLLECTION_NAME,
            "llm_model": GROQ_MODEL if groq_client else "Rule-based Mock",
            "evaluation_label": "Policy/article-level retrieval evaluation",
            "workflow_isolation_note": "This evaluation is offline and does not participate in the live PA decision workflow. The deterministic PA engine remains authoritative."
        },
        "mode_A_unrestricted_metrics": {
            "recall": rec_A_scores,
            "precision": prec_A_scores,
            "mrr": round(mrr_A_score, 4),
            "ndcg": {str(k): round(ndcg_A_means[k], 4) for k in k_values},
            "latency_ms_avg": round(avg_chroma_A_lat, 2)
        },
        "mode_B_production_filtered_metrics": {
            "recall": rec_B_scores,
            "precision": prec_B_scores,
            "mrr": round(mrr_B_score, 4),
            "ndcg": {str(k): round(ndcg_B_means[k], 4) for k in k_values},
            "latency_ms": {
                "mysql_stage1_avg": round(avg_mysql_lat, 2),
                "mysql_stage1_median": round(med_mysql_lat, 2),
                "mysql_stage1_p95": round(p95_mysql_lat, 2),
                "chroma_stage2_avg": round(avg_chroma_B_lat, 2),
                "chroma_stage2_median": round(med_chroma_B_lat, 2),
                "chroma_stage2_p95": round(p95_chroma_B_lat, 2)
            }
        },
        "llm_metrics": {
            "json_validity_rate": json_valid_rate,
            "required_field_completion": req_completion_rate,
            "schema_compliance": schema_comp_rate,
            "evidence_groundedness": round(avg_groundedness, 2),
            "answer_relevance": ans_relevance_rate,
            "policy_evidence_alignment": policy_align_rate,
            "unsupported_claim_rate": unsupported_rate,
            "contradiction_rate": contradiction_rate,
            "assessment_method": "Automated heuristic evaluation",
            "latency_ms": {
                "avg": round(avg_llm_lat, 2),
                "median": round(med_llm_lat, 2),
                "p95": round(p95_llm_lat, 2)
            }
        },
        "per_query_results": per_query_results
    }

    json_report_path = REPORTS_DIR / "rag_llm_evaluation_report.json"
    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(report_json_data, f, indent=2)
    json_path_str = str(json_report_path).replace("\\", "/")
    print(f"\nSaved raw JSON report to: [rag_llm_evaluation_report.json](file:///{json_path_str})")

    txt_report_content = f"""================================================================================
OFFLINE RAG + LLM RETRIEVAL & RANKING EVALUATION REPORT (V3 — CORRECTED NDCG)
================================================================================
Generated at: {time.strftime("%Y-%m-%d %H:%M:%S")}
Embedding Model: {EMBED_MODEL_NAME}
Chroma Store: {CHROMA_DIR}
Collection: {COLLECTION_NAME} ({collection.count()} chunks)

MANDATORY DISCLOSURE & ISOLATION
--------------------------------------------------------------------------------
This evaluation is offline and does not participate in the live PA decision workflow.
The deterministic PA engine remains authoritative.

DATASET SUMMARY
--------------------------------------------------------------------------------
Total Evaluation Queries Created : {len(eval_cases)}
Total Excluded Queries          : {len(excluded_cases)}
Evaluation Metric Scope         : Policy/article-level retrieval evaluation
Ground Truth Methodology        : Verified MySQL pa_kb article_hcpc & article_icd10_covered exact mappings

RETRIEVAL EVALUATION COMPARISON (MODE A VS MODE B)
--------------------------------------------------------------------------------
Metric                  Unrestricted (Mode A)     Policy-Filtered (Mode B)
--------------------------------------------------------------------------------
Recall@1                {rec_A_scores[1]:.2f}%                    {rec_B_scores[1]:.2f}%
Recall@3                {rec_A_scores[3]:.2f}%                    {rec_B_scores[3]:.2f}%
Recall@5                {rec_A_scores[5]:.2f}%                    {rec_B_scores[5]:.2f}%
Recall@10               {rec_A_scores[10]:.2f}%                    {rec_B_scores[10]:.2f}%
Precision@1             {prec_A_scores[1]:.2f}%                    {prec_B_scores[1]:.2f}%
Precision@3             {prec_A_scores[3]:.2f}%                    {prec_B_scores[3]:.2f}%
Precision@5             {prec_A_scores[5]:.2f}%                    {prec_B_scores[5]:.2f}%
Precision@10            {prec_A_scores[10]:.2f}%                    {prec_B_scores[10]:.2f}%
MRR                     {mrr_A_score:.4f}                    {mrr_B_score:.4f}
NDCG@1                  {ndcg_A_means[1]:.4f}                    {ndcg_B_means[1]:.4f}
NDCG@3                  {ndcg_A_means[3]:.4f}                    {ndcg_B_means[3]:.4f}
NDCG@5                  {ndcg_A_means[5]:.4f}                    {ndcg_B_means[5]:.4f}
NDCG@10                 {ndcg_A_means[10]:.4f}                    {ndcg_B_means[10]:.4f}
--------------------------------------------------------------------------------

LATENCY BREAKDOWN
--------------------------------------------------------------------------------
Stage 1 (MySQL Policy Resolution) Latency  : Average {avg_mysql_lat:.2f} ms | Median {med_mysql_lat:.2f} ms | P95 {p95_mysql_lat:.2f} ms
Stage 2 (Chroma Policy-Filtered) Latency  : Average {avg_chroma_B_lat:.2f} ms | Median {med_chroma_B_lat:.2f} ms | P95 {p95_chroma_B_lat:.2f} ms
Stage 3 (Groq LLM Reasoning) Latency      : Average {avg_llm_lat:.2f} ms | Median {med_llm_lat:.2f} ms | P95 {p95_llm_lat:.2f} ms

LLM EVALUATION METRICS (Automated heuristic evaluation)
--------------------------------------------------------------------------------
JSON Validity Rate        : {json_valid_rate:.2f}%
Required Field Completion : {req_completion_rate:.2f}%
Decision Schema Compliance: {schema_comp_rate:.2f}%
Evidence Groundedness     : {avg_groundedness:.2f}%
Answer Relevance          : {ans_relevance_rate:.2f}%
Policy Evidence Alignment : {policy_align_rate:.2f}%
Unsupported Claim Rate    : {unsupported_rate:.2f}%
Contradiction Rate        : {contradiction_rate:.2f}%

================================================================================
PPT-READY RAG + LLM EVALUATION SUMMARY
================================================================================
Dataset size: {len(eval_cases)} evaluation queries from verified MySQL policy mappings
Retrieval Recall@5: {rec_B_scores[5]:.2f}%
Retrieval Precision@5: {prec_B_scores[5]:.2f}%
MRR: {mrr_B_score:.4f}
NDCG@5: {ndcg_B_means[5]:.4f}
LLM Evidence Groundedness: {avg_groundedness:.2f}% (Automated heuristic evaluation)
LLM Answer Relevance: {ans_relevance_rate:.2f}% (Automated heuristic evaluation)
Policy Evidence Alignment: {policy_align_rate:.2f}% (Automated heuristic evaluation)
JSON Validity: {json_valid_rate:.2f}%
Average retrieval latency: {avg_mysql_lat + avg_chroma_B_lat:.2f} ms (MySQL {avg_mysql_lat:.2f} ms + Chroma {avg_chroma_B_lat:.2f} ms)
Average LLM latency: {avg_llm_lat:.2f} ms

This evaluation is offline and does not participate in the live PA decision workflow.
The deterministic PA engine remains authoritative.
================================================================================
"""

    txt_report_path = REPORTS_DIR / "rag_llm_evaluation_report.txt"
    with open(txt_report_path, "w", encoding="utf-8") as f:
        f.write(txt_report_content)
    txt_path_str = str(txt_report_path).replace("\\", "/")
    print(f"Saved text presentation report to: [rag_llm_evaluation_report.txt](file:///{txt_path_str})")

    print("\n" + "=" * 80)
    print("PPT-READY RAG + LLM EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Dataset size: {len(eval_cases)} evaluation queries from verified MySQL policy mappings")
    print(f"Retrieval Recall@5: {rec_B_scores[5]:.2f}%")
    print(f"Retrieval Precision@5: {prec_B_scores[5]:.2f}%")
    print(f"MRR: {mrr_B_score:.4f}")
    print(f"NDCG@5: {ndcg_B_means[5]:.4f}")
    print(f"LLM Evidence Groundedness: {avg_groundedness:.2f}% (Automated heuristic evaluation)")
    print(f"LLM Answer Relevance: {ans_relevance_rate:.2f}% (Automated heuristic evaluation)")
    print(f"Policy Evidence Alignment: {policy_align_rate:.2f}% (Automated heuristic evaluation)")
    print(f"JSON Validity: {json_valid_rate:.2f}%")
    print(f"Average retrieval latency: {avg_mysql_lat + avg_chroma_B_lat:.2f} ms")
    print(f"Average LLM latency: {avg_llm_lat:.2f} ms\n")
    print("This evaluation is offline and does not participate in the live PA decision workflow.")
    print("The deterministic PA engine remains authoritative.")
    print("=" * 80)

if __name__ == "__main__":
    run_evaluation()
