# Google Gmail OAuth + Ollama Setup Guide

This guide explains how to connect the AI Email app with Gmail and Ollama.

---

# 1. Required Files

The backend needs two Gmail OAuth files:

```text
backend/credentials/credentials.json
backend/credentials/token.json
```

## Important

Never commit these files to GitHub.

They are already ignored in `.gitignore`.

---

# 2. Create Google OAuth Credentials

Go to:

```text
https://console.cloud.google.com/
```

## Steps

1. Create or select a Google Cloud project.
2. Go to **APIs & Services**.
3. Go to **Library**.
4. Search for **Gmail API**.
5. Click **Enable**.
6. Go to **APIs & Services → OAuth consent screen**.
7. Choose **External**.
8. Fill required app information.
9. Add your Gmail account as a test user.
10. Go to **APIs & Services → Credentials**.
11. Click **Create Credentials → OAuth Client ID**.
12. Choose:

```text
Desktop app
```

13. Download the JSON file.
14. Rename it to:

```text
credentials.json
```

15. Put it here:

```text
backend/credentials/credentials.json
```

If the `credentials` folder does not exist:

```bash
mkdir backend/credentials
```

---

# 3. Generate token.json

After `credentials.json` is placed correctly, start the backend:

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

Then trigger Gmail loading from the frontend or backend.

The first time Gmail is accessed:

1. A browser window opens.
2. Sign in with your Gmail account.
3. Allow Gmail permissions.
4. Google redirects back to the local app.
5. The backend automatically creates:

```text
backend/credentials/token.json
```

You do not manually create `token.json`.

It is generated after successful Gmail login.

---

# 4. Backend .env Gmail Configuration

Create `.env` inside `backend/`.

```env
GMAIL_CREDENTIALS_PATH=credentials/credentials.json
GMAIL_TOKEN_PATH=credentials/token.json
```

Recommended full local `.env`:

```env
GMAIL_CREDENTIALS_PATH=credentials/credentials.json
GMAIL_TOKEN_PATH=credentials/token.json

ATTACHMENT_USE_OLLAMA=true
ATTACHMENT_LLM_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434

USE_CELERY=false
```

---

# 5. Install Ollama

Ollama is required for local AI summaries, replies, document intelligence, and OCR-based LLM summaries.

Download Ollama:

```text
https://ollama.com/download
```

Install it for your operating system.

---

# 6. Pull the Required Model

After installing Ollama, open a terminal and run:

```bash
ollama pull llama3.1
```

You can verify installed models:

```bash
ollama list
```

---

# 7. Start Ollama

Usually Ollama runs automatically after installation.

To start manually:

```bash
ollama serve
```

Ollama runs at:

```text
http://localhost:11434
```

---

# 8. Connect Backend to Ollama

In `backend/.env`, make sure these values exist:

```env
ATTACHMENT_USE_OLLAMA=true
ATTACHMENT_LLM_MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
```

The backend will use Ollama for:

- Email analysis
- Reply generation
- Attachment summaries
- OCR document summaries
- Thread summaries
- Document intelligence

---

# 9. Verify Ollama Connection

Run:

```bash
curl http://localhost:11434/api/tags
```

If Ollama is running, it returns available models.

You can also test:

```bash
ollama run llama3.1
```

Then type:

```text
Hello
```

If it replies, Ollama is working.

---

# 10. Run Backend

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

Check health:

```text
http://localhost:8000/health
```

---

# 11. Run Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

# 12. Full Local Startup Order

Use this order:

```text
1. Start Ollama
2. Start FastAPI backend
3. Start React frontend
4. Open frontend
5. Connect Gmail
6. Analyze emails
```

---

# 13. Common Issues

## token.json not created

Check:

- Gmail API is enabled.
- OAuth consent screen is configured.
- Your Gmail is added as a test user.
- `credentials.json` is inside `backend/credentials/`.
- `.env` paths are correct.
- Backend is running from the `backend` folder.

---

## Ollama connection failed

Check:

```bash
ollama list
```

Then:

```bash
ollama serve
```

Confirm `.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434
ATTACHMENT_LLM_MODEL=llama3.1
```

---

## Model not found

Run:

```bash
ollama pull llama3.1
```

---

## Gmail permission error

Delete the old token and reconnect:

```text
backend/credentials/token.json
```

Then restart backend and authorize again.

---

# 14. Security Rules

Never commit:

```text
backend/.env
backend/credentials/credentials.json
backend/credentials/token.json
```

Each developer should create their own Google OAuth credentials and token locally.

---

# 15. Summary

Required for local development:

```text
credentials.json
token.json
Ollama
llama3.1 model
backend .env
```

Without Gmail credentials, the app cannot read Gmail.

Without Ollama, AI summaries/replies/document intelligence will not work locally.