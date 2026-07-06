#  API Documentation

Base URL

```
http://localhost:8000
```

---

# Health

## GET /health

Returns backend status.

Example Response

```json
{
  "status": "ok"
}
```

---

# Inbox

## GET /inbox

Returns inbox emails with AI metadata.

Parameters

| Parameter | Description |
|-----------|-------------|
| provider | Gmail / Outlook |
| max_results | Number of emails |
| query | Gmail search query |

---

# Analyze Email

## POST /email/analyze

Runs AI analysis on a selected email.

Returns

- Priority
- Risk
- Intent
- Summary
- Reply recommendation

---

# Generate Reply

## POST /reply/generate

Generates a contextual AI reply.

Returns

- Reply draft
- Tone
- Confidence

---

# Generate Multiple Replies

## POST /reply/multi

Returns multiple reply suggestions.

---

# Thread Summary

## POST /thread/summary

Summarizes an entire email thread.

Returns

- Summary
- Timeline
- Participants
- Action Items
- Pending Questions

---

# Get Full Thread

## GET /thread/full

Returns the complete Gmail thread.

---

# Analyze Attachment

## POST /attachment/analyze

Analyzes an attachment using OCR and Document Intelligence.

Supported Files

- PDF
- DOCX
- Images
- Certificates
- Contracts
- Invoices
- Resumes
- Offer Letters
- Tax Documents

Returns

- Document Type
- Summary
- Key Details
- Confidence
- Priority Reason
- Action Items

---

# Follow-ups

## GET /followups

Returns all follow-ups.

---

## POST /followups/create

Creates a new follow-up.

---

## GET /followups/due

Returns overdue follow-ups.

---

## POST /followups/{id}/status

Marks a follow-up as complete.

---

# Reminders

## GET /reminders

Returns reminders.

---

## POST /reminders/create

Creates a reminder.

---

## POST /reminders/{id}/complete

Marks reminder as completed.

---

# Analytics

## GET /analytics

Returns AI analytics.

Includes

- Priority distribution
- Email statistics
- Sender statistics
- AI usage
- Follow-up metrics

---

# Authentication

The backend uses Gmail OAuth for accessing user emails.

Each developer should configure their own credentials locally.

Do **not** commit:

- credentials.json
- token.json
- .env