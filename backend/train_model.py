import os
import sys
import json
import time
from datetime import datetime
import numpy as np
import pandas as pd
import pymysql
import joblib
from dotenv import load_dotenv

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    brier_score_loss,
    confusion_matrix
)

# Load environment
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
PA_SYSTEM_DB = os.getenv("DB_NAME", "pa_system")

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_PATH = os.path.join(MODELS_DIR, "approval_predictor.joblib")

def calculate_age(birthdate_str):
    if not birthdate_str:
        return 50  # default median age
    try:
        b_date = datetime.strptime(str(birthdate_str)[:10], "%Y-%m-%d")
        today = datetime.now()
        return today.year - b_date.year - ((today.month, today.day) < (b_date.month, b_date.day))
    except Exception:
        return 50

def load_real_data():
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=PA_SYSTEM_DB,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    r.request_id,
                    r.requested_hcpcs,
                    r.diagnosis_icd10,
                    COALESCE(r.payer_name, 'Unknown') AS payer_name,
                    COALESCE(r.urgency, 'LOW') AS urgency,
                    COALESCE(CHAR_LENGTH(r.clinical_rationale), 0) AS rationale_length,
                    r.status AS engine_status,
                    r.insurer_final_status,
                    p.birthdate,
                    COALESCE(p.gender, 'U') AS gender,
                    COALESCE(p.state, 'Unknown') AS state
                FROM pa_request r
                LEFT JOIN patients p ON r.patient_id = p.patient_id
            """)
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"Warning: Could not load real data from database ({e})")
        return []

def generate_synthetic_dataset(num_samples=500, random_seed=42):
    np.random.seed(random_seed)
    
    hcpcs_list = ["29881", "G0296", "29877", "Q5107", "72148", "93458", "99214"]
    icd10_list = ["M23.22", "F17.210", "C85.80", "C18.8", "M51.16", "I21.A1", "Z00.00"]
    payers = ["Medicaid", "Medicare", "Blue Cross", "Aetna", "NO_INSURANCE"]
    genders = ["M", "F"]
    states = ["Massachusetts", "New York", "California", "Texas", "Florida"]
    urgencies = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    records = []
    for i in range(num_samples):
        hcpcs = np.random.choice(hcpcs_list)
        icd10 = np.random.choice(icd10_list)
        payer = np.random.choice(payers)
        gender = np.random.choice(genders)
        state = np.random.choice(states)
        urgency = np.random.choice(urgencies)
        age = int(np.random.randint(18, 85))
        rationale_len = int(np.random.randint(10, 400))
        
        # Define synthetic rule-based approval probability with noise
        base_prob = 0.5
        if hcpcs in ["Q5107", "G0296"]:
            base_prob += 0.25
        if icd10 in ["F17.210", "I21.A1"]:
            base_prob += 0.20
        if rationale_len > 150:
            base_prob += 0.15
        if payer == "Medicare":
            base_prob += 0.05
        if urgency == "CRITICAL":
            base_prob += 0.10
        
        prob = np.clip(base_prob + np.random.normal(0, 0.1), 0.05, 0.95)
        target = 1 if np.random.rand() < prob else 0
        
        records.append({
            "patient_age": age,
            "gender": gender,
            "state": state,
            "requested_hcpcs": hcpcs,
            "diagnosis_icd10": icd10,
            "payer_name": payer,
            "urgency": urgency,
            "rationale_length": rationale_len,
            "target": target
        })
    return pd.DataFrame(records)

def train_and_evaluate():
    start_time = time.time()
    print("================ ML TRAINING PIPELINE ================")
    
    # 1. Inspect real database records
    real_rows = load_real_data()
    print(f"Total real PA records in DB: {len(real_rows)}")
    
    # Process real rows
    real_records = []
    for r in real_rows:
        # Determine target from historical final status or engine status
        final_stat = r.get("insurer_final_status")
        if final_stat:
            target = 1 if final_stat == "APPROVED" else 0
        else:
            target = 1 if r.get("engine_status") == "APPROVED" else 0
            
        real_records.append({
            "patient_age": calculate_age(r.get("birthdate")),
            "gender": r.get("gender") or "U",
            "state": r.get("state") or "Unknown",
            "requested_hcpcs": r.get("requested_hcpcs") or "Unknown",
            "diagnosis_icd10": r.get("diagnosis_icd10") or "Unknown",
            "payer_name": r.get("payer_name") or "Unknown",
            "urgency": r.get("urgency") or "LOW",
            "rationale_length": int(r.get("rationale_length") or 0),
            "target": target
        })
    
    real_df = pd.DataFrame(real_records)
    
    # Determine if real data is sufficient for production training
    # Step 13 & 14 requirement: If insufficient real labeled data, use synthetic baseline and set is_synthetic_model=True
    num_real_approved = real_df["target"].sum() if not real_df.empty else 0
    num_real_non_approved = len(real_df) - num_real_approved if not real_df.empty else 0
    
    print(f"Real data outcomes: Approved = {num_real_approved}, Non-approved = {num_real_non_approved}")
    
    if len(real_df) >= 100 and num_real_approved >= 20 and num_real_non_approved >= 20:
        print("Using REAL historical PA dataset for model training.")
        df = real_df
        is_synthetic = False
        model_version = "v1.0-real-rf"
    else:
        print("Notice: Insufficient real historical PA decisions for production-grade training.")
        print("Generating clearly labeled DEMO / SYNTHETIC baseline dataset (500 records)...")
        df = generate_synthetic_dataset(num_samples=500, random_seed=42)
        is_synthetic = True
        model_version = "v1.0-synthetic-rf"
    
    # Pre-adjudication features
    num_features = ["patient_age", "rationale_length"]
    cat_features = ["gender", "state", "requested_hcpcs", "diagnosis_icd10", "payer_name", "urgency"]
    
    X = df[num_features + cat_features]
    y = df["target"]
    
    # Train / Test Split
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )
        stratified = True
    except Exception:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42
        )
        stratified = False
        
    print(f"Train records: {len(X_train)} | Test records: {len(X_test)}")
    print(f"Train class distribution: Approved={y_train.sum()}, Non-approved={len(y_train)-y_train.sum()}")
    print(f"Test class distribution:  Approved={y_test.sum()}, Non-approved={len(y_test)-y_test.sum()}")
    
    # Build scikit-learn preprocessing + model pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', StandardScaler(), num_features),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_features)
        ]
    )
    
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', clf)
    ])
    
    # Train pipeline
    pipeline.fit(X_train, y_train)
    
    # Predict on test set
    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]
    
    # Compute Evaluation Metrics
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    
    # ROC-AUC check
    if len(np.unique(y_test)) > 1:
        roc_auc = roc_auc_score(y_test, y_proba)
        roc_auc_str = f"{roc_auc:.4f}"
    else:
        roc_auc = None
        roc_auc_str = "Not available due to insufficient class diversity"
        
    brier = brier_score_loss(y_test, y_proba)
    cm = confusion_matrix(y_test, y_pred).tolist()
    
    # Baseline comparison (Majority Class)
    majority_class = y_train.mode()[0]
    y_baseline = np.full_like(y_test, majority_class)
    baseline_acc = accuracy_score(y_test, y_baseline)
    
    training_time = time.time() - start_time
    
    print("\n--- EVALUATION METRICS ---")
    print(f"Accuracy:          {acc:.4f}")
    print(f"Precision:         {prec:.4f}")
    print(f"Recall:            {rec:.4f}")
    print(f"F1-Score:          {f1:.4f}")
    print(f"ROC-AUC:           {roc_auc_str}")
    print(f"Brier Score:       {brier:.4f}")
    print(f"Confusion Matrix:  {cm}")
    print(f"Majority Baseline: {baseline_acc:.4f}")
    print(f"Training Time:     {training_time:.3f}s")
    
    # Save complete model artifact
    os.makedirs(MODELS_DIR, exist_ok=True)
    artifact = {
        "pipeline": pipeline,
        "metadata": {
            "model_version": model_version,
            "is_synthetic_model": is_synthetic,
            "num_features": num_features,
            "cat_features": cat_features,
            "total_samples": len(df),
            "approved_count": int(y.sum()),
            "non_approved_count": int(len(y) - y.sum()),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "metrics": {
                "accuracy": round(acc, 4),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1, 4),
                "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
                "brier_score": round(brier, 4),
                "confusion_matrix": cm,
                "baseline_accuracy": round(baseline_acc, 4)
            },
            "trained_at": datetime.now().isoformat()
        }
    }
    
    joblib.dump(artifact, MODEL_PATH)
    print(f"\nModel artifact saved successfully to:\n{MODEL_PATH}")
    print("======================================================")

# Need sklearn Pipeline import
from sklearn.pipeline import Pipeline

if __name__ == "__main__":
    train_and_evaluate()
