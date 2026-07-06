
---

### `SETUP.md`

For teammates.

```md
# Setup Guide

## Requirements

- Python 3.11+
- Node.js 18+
- npm
- Git
- Gmail OAuth credentials
- Optional: Ollama
- Optional: Redis/Celery
- Optional: Tesseract OCR

## Clone

```bash
git clone https://github.com/Skatip/email-AI.git
cd email-AI

##Backend Setup
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements_attachment_optional.txt

##Create .env inside backend/.

GMAIL_CREDENTIALS_PATH=credentials/credentials.json
GMAIL_TOKEN_PATH=credentials/token.json
ATTACHMENT_USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434
ATTACHMENT_LLM_MODEL=llama3.1
USE_CELERY=false

Run backend:

uvicorn app.main:app --reload

##Frontend Setup
cd frontend
npm install
npm run dev

Open:

http://localhost:5173
Optional Redis/Celery

Redis/Celery is optional and should be used for background tasks only.

USE_CELERY=true
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

Worker:

celery -A app.celery_app.celery_app worker --pool=solo --loglevel=info
