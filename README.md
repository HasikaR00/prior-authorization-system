# Prior Authorization System

An AI-driven healthcare Prior Authorization System designed to streamline, evaluate, and triage medical prior authorization requests using AI decision engines, RAG (Retrieval-Augmented Generation), machine learning prediction models, and optical character recognition (OCR).

---

## 🚀 Features

- **AI-Powered Decision Engine**: Evaluates prior authorization requests against medical guidelines and knowledge bases using LLMs (OpenAI, Google Gemini, or Groq) integrated with ChromaDB vector search.
- **Medical PDF & Image OCR**: Extract clinical data and medical context directly from uploaded medical records and clinical notes using PyMuPDF and PyTesseract.
- **Role-Based Workflows**: Tailored user dashboards for Healthcare Providers (Doctors/Staff) and Payers/Reviewers.
- **Patient & Request Management**: Create and maintain patient records, submit prior authorization requests, track real-time status updates, and attach supporting documentation.
- **Urgency & Triage Classification**: Automatically assess decision urgency and risk indicators for pending authorizations.
- **Machine Learning Predictor & Training**: Includes trained predictive models to estimate approval likelihood and historical outcomes (`backend/train_model.py`, `backend/ml_predictor.py`).
- **Comprehensive Evaluation Suite**: Benchmarking tools (`run_evaluation_suite.py`) to measure decision accuracy, latency, and model reliability.

---

## 🛠️ Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
- **Database**: MySQL (via `PyMySQL`) + [ChromaDB](https://www.trychroma.com/) (Vector DB for RAG)
- **AI / LLM Services**: OpenAI API, Google GenAI SDK, Groq SDK
- **OCR & Document Processing**: PyMuPDF (`fitz`), PyTesseract, Pillow
- **Authentication**: JWT (`PyJWT`), `bcrypt` password hashing

### Frontend
- **Framework**: [React 19](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS 4](https://tailwindcss.com/)
- **Icons & Routing**: Lucide React, React Router v7
- **HTTP Client**: Axios

---

## 📁 Project Structure

```text
.
├── backend/
│   ├── app.py                   # FastAPI application entry point & CORS configuration
│   ├── db.py                    # Database connection setup
│   ├── auth.py                  # JWT authentication middleware & password security
│   ├── decision_engine.py       # Core AI evaluation & guideline retrieval logic
│   ├── ml_predictor.py          # Machine learning approval score predictor
│   ├── pdf_ocr.py               # Document OCR & PDF parsing routines
│   ├── train_model.py           # ML training pipelines
│   ├── eval_logger.py           # Evaluation metric logger
│   ├── evaluation.py            # Evaluation logic
│   └── routes/                  # API endpoints
│       ├── auth_routes.py       # User registration & login
│       ├── patient_routes.py    # Patient management
│       ├── request_routes.py    # Request submission & file attachments
│       ├── review_routes.py     # Payer review & approval actions
│       └── code_routes.py       # Medical code lookups (CPT/ICD)
├── frontend/
│   ├── src/                     # React application source code
│   │   ├── pages/               # Dashboard, Login, Request, and Patient views
│   │   └── components/          # Reusable UI components
│   ├── package.json
│   └── vite.config.js
├── database/                    # SQL scripts & database schema migrations
├── KB/                          # Clinical knowledge base & guideline documents
├── run_evaluation_suite.py      # Standalone evaluation & benchmarking runner
├── .env.example                 # Environment variable template
└── README.md
```

---

## ⚙️ Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: v18+ and `npm`
- **MySQL**: Server instance running locally or remotely
- **Tesseract OCR**: Installed on host machine (required for image OCR)

---

### 1. Backend Setup

1. **Navigate to the backend folder**:
   ```bash
   cd backend
   ```

2. **Create and activate a Python virtual environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**:
   Copy `.env.example` to `.env` in the root (or inside `backend/`) and configure your database and API keys:
   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=pa_system
   PA_KB_NAME=pa_kb

   JWT_SECRET=your_jwt_secret_key
   FRONTEND_ORIGIN=http://localhost:5173

   OPENAI_API_KEY=your_openai_key
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

5. **Initialize Database**:
   Import the SQL schema files located in the `database/` folder into your MySQL server.

6. **Start the Backend Server**:
   ```bash
   uvicorn backend.app:app --reload --port 8000
   ```
   The API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 2. Frontend Setup

1. **Navigate to the frontend folder**:
   ```bash
   cd frontend
   ```

2. **Install Node modules**:
   ```bash
   npm install
   ```

3. **Run Development Server**:
   ```bash
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📊 Running Evaluation & Benchmarks

To run the prior authorization evaluation suite against test cases and models:

```bash
python run_evaluation_suite.py
```

Evaluation logs and performance reports will be generated in `backend/evaluation_reports/`.

---

## 🔒 Security & Guidelines

- Do not commit your `.env` file containing real API keys or DB passwords.
- Ensure CORS origins in `backend/app.py` match your production frontend URL.
