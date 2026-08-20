# Prior Authorization System

An AI-driven healthcare **Prior Authorization System** designed to automate, evaluate, and triage medical prior authorization requests. Powered by Retrieval-Augmented Generation (RAG), ML decision predictors, OCR document processing, and role-based clinical dashboards.

---

##  Table of Contents
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Architecture](#-project-architecture)
- [Prerequisites](#-prerequisites)
- [Getting Started](#-getting-started)
  - [1. Backend Setup](#1-backend-setup)
  - [2. Frontend Setup](#2-frontend-setup)
- [API & Evaluation](#-api--evaluation)
- [Security Guidelines](#-security-guidelines)
- [License](#-license)

---

##  Features

-  **AI-Powered Decision Engine**: Evaluates requests against medical coverage guidelines using RAG with ChromaDB vector search and LLMs (OpenAI, Gemini, Groq).
-  **Medical OCR & Document Processing**: Extracts structured clinical data from uploaded PDF medical records and notes using PyMuPDF and Tesseract.
-  **Role-Based Workflows**: Tailored user interfaces for Healthcare Providers (Doctors/Staff) and Payers/Reviewers.
-  **Patient & Authorization Management**: Patient profile tracking, request submission, urgency classification, and document attachments.
-  **Machine Learning Approval Predictor**: Predictive models estimating approval probabilities based on historical data.
-  **Benchmarking & Evaluation Suite**: Automated evaluation runner (`run_evaluation_suite.py`) to measure decision accuracy and model latency.

---

##  Tech Stack

| Category | Technology |
|---|---|
| **Backend Framework** | FastAPI (Python 3.10+) + Uvicorn |
| **Databases** | MySQL (Relational DB) + ChromaDB (Vector DB for RAG) |
| **AI / LLMs** | OpenAI API, Google GenAI SDK, Groq SDK |
| **Document OCR** | PyMuPDF (`fitz`), PyTesseract, Pillow |
| **Authentication** | JWT (`PyJWT`) + `bcrypt` password hashing |
| **Frontend Framework** | React 19 + Vite |
| **Styling & UI** | Tailwind CSS v4, Lucide Icons |
| **HTTP Client** | Axios |

---

##  Project Architecture

```text
.
├── backend/
│   ├── app.py                   # FastAPI entry point & CORS configuration
│   ├── auth.py                  # JWT authentication middleware & hashing
│   ├── decision_engine.py       # Core AI evaluation & RAG logic
│   ├── ml_predictor.py          # Machine learning approval score predictor
│   ├── pdf_ocr.py               # Document OCR & PDF parsing routines
│   ├── train_model.py           # ML model training pipeline
│   └── routes/                  # API endpoints (Auth, Patient, Request, Review, Codes)
├── frontend/
│   ├── src/                     # React application source code
│   │   ├── pages/               # Provider/Payer dashboards, forms, and submission views
│   │   └── components/          # Shared UI elements
│   ├── package.json
│   └── vite.config.js
├── database/                    # SQL schema definitions & migrations
├── KB/                          # Clinical guidelines & knowledge base sources
└── run_evaluation_suite.py      # Standalone evaluation & benchmarking runner
