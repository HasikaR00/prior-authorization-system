from fastapi import APIRouter, HTTPException, Depends
from backend.db import get_system_db
from backend.auth import get_current_user
from backend.decision_engine import simplify_description

router = APIRouter(prefix="/codes", tags=["codes"])

@router.get("/hcpcs")
def get_hcpcs_codes(search: str = "", limit: int = 5000, user_payload: dict = Depends(get_current_user)):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            if search.strip():
                cur.execute("""
                    SELECT DISTINCT hcpc_code, short_description, long_description 
                    FROM article_hcpc 
                    WHERE hcpc_code LIKE %s OR short_description LIKE %s OR long_description LIKE %s 
                    ORDER BY hcpc_code ASC LIMIT %s
                """, (f"%{search}%", f"%{search}%", f"%{search}%", limit))
            else:
                cur.execute("""
                    SELECT DISTINCT hcpc_code, short_description, long_description 
                    FROM article_hcpc 
                    ORDER BY hcpc_code ASC LIMIT %s
                """, (limit,))
            rows = cur.fetchall()
            for r in rows:
                raw_desc = r.get("long_description") or r.get("short_description") or ""
                r["simplified_description"] = simplify_description(raw_desc)
            return rows
    finally:
        conn.close()

@router.get("/icd10")
def get_icd10_codes(search: str = "", hcpcs: str = "", limit: int = 5000, user_payload: dict = Depends(get_current_user)):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            if hcpcs.strip():
                # Filter ICD-10 codes associated with the selected HCPCS code via active policy article
                query = """
                    SELECT DISTINCT c.icd10_code, c.description
                    FROM article_icd10_covered c
                    JOIN article_hcpc h ON c.article_id = h.article_id AND c.article_version = h.article_version
                    WHERE h.hcpc_code = %s
                """
                params = [hcpcs]
                if search.strip():
                    query += " AND (c.icd10_code LIKE %s OR c.description LIKE %s)"
                    params.extend([f"%{search}%", f"%{search}%"])
                query += " ORDER BY c.icd10_code ASC LIMIT %s"
                params.append(limit)
                cur.execute(query, tuple(params))
            else:
                if search.strip():
                    cur.execute("""
                        SELECT DISTINCT icd10_code, description 
                        FROM article_icd10_covered 
                        WHERE icd10_code LIKE %s OR description LIKE %s 
                        ORDER BY icd10_code ASC LIMIT %s
                    """, (f"%{search}%", f"%{search}%", limit))
                else:
                    cur.execute("""
                        SELECT DISTINCT icd10_code, description 
                        FROM article_icd10_covered 
                        ORDER BY icd10_code ASC LIMIT %s
                    """, (limit,))
            rows = cur.fetchall()
            for r in rows:
                raw_desc = r.get("description") or ""
                r["simplified_description"] = simplify_description(raw_desc)
            return rows
    finally:
        conn.close()
