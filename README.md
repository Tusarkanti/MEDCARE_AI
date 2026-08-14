# MedCare AI

MedCare AI is a healthcare-assistance web application with patient intake, symptom analysis, health predictions, vital-sign tracking, insurance assistance, and a conversational assistant.

> **Medical disclaimer:** This project is for educational and informational use only. It does not provide medical diagnosis or replace advice from a qualified healthcare professional.

## Source layout

- `frontend/` ? static web application served by Firebase Hosting.
- `backend/` ? Flask API, ML inference, chat, and supporting services.
- `backend/ml/` and `models/` ? ML code and model-related assets.
- `public/` ? Firebase public assets.
- `firebase.json` ? Firebase Hosting configuration.

## Requirements

- Python 3.10 or later
- MongoDB (optional for features that store user and patient data)
- A modern browser
- Firebase CLI (only to deploy the frontend)

## Run locally

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure optional services through environment variables:

```powershell
$env:MONGO_URI = "mongodb://localhost:27017"
$env:MONGO_DB_NAME = "medcare_ai"
$env:OPENAI_API_KEY = "your_api_key"  # optional; enables LLM responses
$env:OPENAI_MODEL = "gpt-4o-mini"     # optional
```

Start the API:

```powershell
python backend/app.py
```

The backend runs at `http://localhost:5000` by default. Serve the `frontend/` directory with a local static server or Firebase Hosting emulator to use the web interface.

## Deploy frontend

The repository is configured for Firebase Hosting:

```powershell
firebase deploy --only hosting
```

## Large model artifact

`backend/ml/artifacts/ensemble_models.pkl` is managed with Git LFS. Install Git LFS before cloning if you need the model locally:

```powershell
git lfs install
git lfs pull
```

## Authentication status
