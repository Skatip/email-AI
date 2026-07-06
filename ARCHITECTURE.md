#  System Architecture

The AI Email Intelligence Platform follows a modular architecture designed for fast user interaction while supporting advanced AI capabilities.

---

# High-Level Architecture

```text
                React Frontend
                       │
                       ▼
                 FastAPI Backend
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 Gmail Service   AI Intelligence   Data Storage
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
Reply Agent    Thread Intelligence  Attachment Intelligence
       │               │                │
       ▼               ▼                ▼
  Follow-ups      Reminders      OCR + Document Intelligence
```

---

# Execution Layers

```text
                    FastAPI
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
 Instant Layer    Quick AI Layer   Background Layer
```

---

# Instant Layer

Response Time:

```
< 100 ms
```

Purpose

- Load inbox instantly
- Show metadata
- Load cached AI results

Responsibilities

- Email metadata
- Sender
- Subject
- Snippet
- Labels
- Cached summaries
- Attachment metadata
- Follow-up status
- Reminder status

No LLM calls occur in this layer.

---

# Quick AI Layer

Response Time

```
1–3 seconds
```

Purpose

Provide AI responses for user-triggered actions.

Responsibilities

- Email analysis
- Priority detection
- Intent detection
- Risk analysis
- Generate Reply
- Multi Reply
- Thread Summary
- Attachment Analysis
- OCR
- Document Intelligence

This layer communicates directly with Ollama or OpenAI.

---

# Background Layer

Purpose

Run long-running AI tasks asynchronously.

Examples

- Large OCR jobs
- Batch inbox analysis
- Analytics refresh
- Reminder scheduler
- Follow-up scheduler
- Future RAG indexing
- Vector database updates

Redis and Celery are intended only for this layer.

---

# AI Components

## Reply Agent

- Human-like replies
- Multi-reply generation
- Context-aware responses
- Attachment-aware responses

---

## Thread Intelligence

- Thread summarization
- Timeline generation
- Action item extraction
- Pending response detection

---

## Attachment Intelligence

- PDF analysis
- DOCX analysis
- Image OCR
- Certificate detection
- Invoice detection
- Contract detection
- Offer Letter detection
- Resume detection
- Dynamic document understanding

---

## Follow-up Engine

- AI follow-up detection
- Reminder generation
- Due status tracking
- Follow-up dashboard

---

# Future Architecture

The long-term roadmap includes:

- Retrieval-Augmented Generation (RAG)
- Semantic Chunking
- Vector Database
- Knowledge Graph
- AI Agents
- MCP Integration
- Slack Integration
- Outlook Integration
- Google Drive Integration