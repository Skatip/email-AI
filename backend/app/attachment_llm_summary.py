import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DOCUMENT_TYPES = [
    "Offer Letter", "Contract", "Invoice", "Resume", "Certificate", "Tax Document",
    "Bank Statement", "Medical Document", "Academic Transcript", "Travel Document",
    "ID Document", "Spreadsheet", "Image", "Screenshot", "Project Document",
    "Technical Document", "Meeting Notes", "Presentation", "General Document", "Unknown Document",
]

SYSTEM_PROMPT = """
You are an enterprise Document Intelligence Agent inside a smart AI email assistant.
Your job is not to summarize OCR text. Your job is to understand what the attachment is, what matters, and what action is needed.
Return ONLY valid JSON. Do not include markdown.

Core behavior:
- Extract only facts that are supported by the attachment text, filename, or email context.
- Do not guess missing facts.
- Ignore duplicated OCR blocks, legal disclaimers, logo descriptions, watermarks, copyright notices, page footers, and repeated provider boilerplate.
- Do not classify a document from a single weak keyword. Use the whole context and confidence.
- If the evidence is weak, return General Document, Project Document, Screenshot, Image, or Unknown Document with lower confidence instead of forcing a specific type.
- Travel Document requires clear travel evidence such as flight, airline, airport, boarding, itinerary, booking reference, reservation, route, departure, arrival, seat, gate, PNR, hotel, check-in, or trip date. Do not use Travel Document for software release documents, project documents, or ordinary confirmations.
- Image should describe whether meaningful OCR text was found. If text is weak/noisy, say that the image does not contain enough readable text.
- Keep output concise and useful for the UI.

Return JSON with exactly these keys:
{
  "document_type": "Certificate",
  "title": "Document title or course/program/name",
  "summary": "One polished paragraph explaining what the document is and why it matters.",
  "key_details": ["Recipient: ...", "Course: ...", "Issuer: ..."],
  "action_items": ["No action required unless this needs to be saved or shared."],
  "dates": ["Sep 22, 2025"],
  "amounts": [],
  "ids": ["Certificate ID: ..."],
  "action_required": false,
  "business_value": "Why this document matters to the user.",
  "priority_reason": "Short reason for priority impact.",
  "reply_context": "One sentence the reply agent can use naturally.",
  "confidence": 0.90
}
""".strip()

LEGAL_NOISE_PATTERNS = [
    r"the .*? logo is a registered mark of .*?(?:inc\.|llc|ltd|corporation|institute).*?",
    r"privacy policy.*?",
    r"terms of service.*?",
    r"all rights reserved.*?",
    r"copyright .*?",
    r"this (?:email|message|document) .*? confidential.*?",
]

TRAVEL_STRONG_TERMS = [
    "flight", "airline", "airport", "boarding", "boarding pass", "itinerary", "reservation",
    "booking reference", "confirmation number", "pnr", "departure", "arrival", "gate", "seat",
    "check-in", "check in", "hotel", "rental car", "lga", "sfo", "jfk", "ewr", "ord", "dfw", "lax",
]
PROJECT_TERMS = [
    "development", "release", "sprint", "feature", "bug", "frontend", "backend", "fastapi", "react",
    "ai email", "agent", "implementation", "deployment", "requirements", "roadmap", "technical",
    "architecture", "api", "database", "redis", "celery", "ollama", "llm", "rag", "ocr",
]
CERT_TERMS = ["certificate", "certification", "course completed", "completed by", "certificate id", "pdu", "contact hours", "linkedIn learning"]


def preclean_extracted_text(text: str, limit: int = None) -> str:
    if limit is None:
        limit = int(os.getenv("ATTACHMENT_LLM_TEXT_LIMIT", "4500"))
    if not text:
        return ""
    text = text.replace("\x00", " ").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    for pat in LEGAL_NOISE_PATTERNS:
        text = re.sub(pat, " ", text, flags=re.I | re.S)
    lines: List[str] = []
    seen = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        low = line.lower()
        if "logo is a registered mark" in low:
            continue
        if len(low) < 2:
            continue
        if low in seen:
            continue
        seen.add(low)
        lines.append(line)
    cleaned = "\n".join(lines)
    # Remove repeated large blocks using normalized chunk keys.
    chunks = [c.strip() for c in re.split(r"\n{2,}", cleaned) if c.strip()]
    out: List[str] = []
    seen_chunks = set()
    for chunk in chunks:
        key = re.sub(r"\W+", " ", chunk.lower()).strip()[:260]
        if key in seen_chunks:
            continue
        seen_chunks.add(key)
        out.append(chunk)
    return "\n\n".join(out).strip()[:limit]


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    raw = s.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            return None
    return None


def _normalize_list(value: Any, limit: int = 10) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen = set()
    for item in value:
        s = re.sub(r"\s+", " ", str(item or "").strip())
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:260])
        if len(out) >= limit:
            break
    return out


def _valid_document_type(value: str, fallback: str = "General Document") -> str:
    value = str(value or "").strip()
    for t in DOCUMENT_TYPES:
        if value.lower() == t.lower():
            return t
    low = value.lower()
    if "cert" in low:
        return "Certificate"
    if "offer" in low:
        return "Offer Letter"
    if "invoice" in low or "bill" in low:
        return "Invoice"
    if "travel" in low or "flight" in low or "itinerary" in low:
        return "Travel Document"
    if "resume" in low or low == "cv":
        return "Resume"
    if "project" in low or "technical" in low:
        return "Project Document"
    if "screen" in low:
        return "Screenshot"
    return fallback if fallback in DOCUMENT_TYPES else "General Document"


def _contains_any(text: str, terms: List[str]) -> List[str]:
    low = (text or "").lower()
    return [t for t in terms if t.lower() in low]


def _evidence_document_type(filename: str, file_type: str, detected_label: str, text: str, email_subject: str = "") -> Tuple[str, float, List[str]]:
    combined = f"{filename}\n{detected_label}\n{email_subject}\n{text}".lower()
    travel_hits = _contains_any(combined, TRAVEL_STRONG_TERMS)
    project_hits = _contains_any(combined, PROJECT_TERMS)
    cert_hits = _contains_any(combined, CERT_TERMS)

    if len(cert_hits) >= 2:
        return "Certificate", min(0.92, 0.62 + 0.08 * len(cert_hits)), cert_hits[:8]
    if len(travel_hits) >= 2:
        return "Travel Document", min(0.90, 0.58 + 0.08 * len(travel_hits)), travel_hits[:8]
    if project_hits and len(travel_hits) < 2:
        return "Project Document", min(0.86, 0.55 + 0.06 * len(project_hits)), project_hits[:8]
    if file_type == "image":
        meaningful = _meaningful_text(text)
        return ("Screenshot" if meaningful else "Image"), (0.62 if meaningful else 0.45), []
    return _valid_document_type(detected_label, "General Document"), 0.50, []


def _meaningful_text(text: str) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"Image detected\. Format:.*?(?:OCR text:)?", " ", text, flags=re.I | re.S)
    words = re.findall(r"[A-Za-z0-9]{3,}", cleaned)
    # Avoid treating metadata-only image output as meaningful OCR.
    if len(words) < int(os.getenv("IMAGE_MEANINGFUL_OCR_WORDS", "8")):
        return False
    meta_words = {"image", "detected", "format", "size", "ocr", "text", "available", "install", "tesseract"}
    useful = [w for w in words if w.lower() not in meta_words]
    return len(useful) >= int(os.getenv("IMAGE_USEFUL_OCR_WORDS", "6"))


def _first_match(patterns: List[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.M | re.S)
        if m:
            groups = [g for g in m.groups() if g]
            return re.sub(r"\s+", " ", (" ".join(groups) if groups else m.group(0))).strip()
    return ""


def _fallback_document_type(filename: str, detected_label: str, text: str, file_type: str = "", email_subject: str = "") -> str:
    evidence_type, _, _ = _evidence_document_type(filename, file_type, detected_label, text, email_subject)
    low = f"{filename}\n{detected_label}\n{text}".lower()
    if evidence_type != "General Document":
        return evidence_type
    if any(x in low for x in ["offer letter", "employment offer", "compensation", "salary"]):
        return "Offer Letter"
    if any(x in low for x in ["invoice", "amount due", "payment due", "subtotal"]):
        return "Invoice"
    if any(x in low for x in ["contract", "agreement", "terms and conditions", "effective date"]):
        return "Contract"
    if any(x in low for x in ["resume", "curriculum vitae", "work experience", "education", "skills"]):
        return "Resume"
    return "General Document"


def _find_cert_details(text: str, dates: List[str]) -> Tuple[str, List[str], List[str], List[str], str, str, str]:
    title = _first_match([
        r"^(Artificial Intelligence for Cybersecurity)$",
        r"LinkedIn\s+Learning\s+\n?\s*([A-Z][A-Za-z0-9 &,/()\-]{6,140})\s+Course completed by",
        r"^([A-Z][A-Za-z0-9 &,/()\-]{6,140})\s+Course completed by",
    ], text)
    recipient = _first_match([
        r"Course completed by\s+([A-Z][A-Za-z .'-]{2,80})",
        r"(?:awarded to|presented to)\s+([A-Z][A-Za-z .'-]{2,80})",
    ], text)
    cert_id = _first_match([r"Certificate ID:\s*([A-Za-z0-9\-]{10,140})", r"Credential ID:\s*([A-Za-z0-9\-]{6,140})"], text)
    hours = _first_match([r"PDUs/Contact\s*Hours:\s*([0-9.]+)", r"Contact\s*Hours:\s*([0-9.]+)"], text)
    issuer = ""
    if re.search(r"LinkedIn\s+Learning", text, re.I):
        issuer = "LinkedIn Learning"
    elif re.search(r"PMI", text, re.I):
        issuer = "PMI Registered Education Provider"
    skills: List[str] = []
    m = re.search(r"Top skills covered\s+(.+?)(?:\n|Program:|Provider ID:|Certificate ID:|$)", text, flags=re.I | re.S)
    if m:
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        if "AI for Cybersecurity" in raw and "Artificial Intelligence" in raw:
            skills = ["AI for Cybersecurity", "Cybersecurity", "Artificial Intelligence (AI)"]
        else:
            skills = [x.strip() for x in re.split(r",|;|\|", raw) if x.strip()][:4]
    key_details: List[str] = []
    if recipient:
        key_details.append(f"Recipient: {recipient}")
    if title:
        key_details.append(f"Course: {title}")
    if issuer:
        key_details.append(f"Issuer: {issuer}")
    if dates:
        key_details.append(f"Completion date: {dates[0]}")
    if hours:
        key_details.append(f"PDUs/Contact hours: {hours}")
    if skills:
        key_details.append("Skills: " + ", ".join(skills[:4]))
    ids = [f"Certificate ID: {cert_id}"] if cert_id else []
    summary = f"This is a professional certificate confirming completion of {title or 'a training course'}"
    if recipient:
        summary += f" by {recipient}"
    if issuer:
        summary += f" through {issuer}"
    if dates:
        summary += f" on {dates[0]}"
    summary += ". It can support resume, LinkedIn profile, job application evidence, or career documentation."
    actions = ["No reply is required unless this certificate needs to be saved, shared, or added to a resume/profile."]
    business_value = "Professional development credential that can support career branding, applications, and skills documentation."
    priority_reason = "Professional certificate detected; useful for career records but usually not urgent."
    return title, key_details, actions, ids, summary, business_value, priority_reason


def _fallback_summary(filename: str, file_type: str, detected_document_label: str, extracted_text: str, dates: Optional[List[str]] = None, amounts: Optional[List[str]] = None, email_subject: str = "") -> Dict[str, Any]:
    text = preclean_extracted_text(extracted_text)
    dates = dates or []
    amounts = amounts or []
    doc_type = _fallback_document_type(filename, detected_document_label, text, file_type, email_subject)
    evidence_type, confidence, evidence = _evidence_document_type(filename, file_type, detected_document_label, text, email_subject)
    if evidence_type != "General Document":
        doc_type = evidence_type
    title = _first_match([r"^(.{6,120})$"], text.splitlines()[0] if text.splitlines() else "")
    key_details: List[str] = []
    action_items: List[str] = []
    ids: List[str] = []
    business_value = "Document may contain useful context for this email."
    priority_reason = "Attachment analyzed; priority depends on document type, sender, and action required."
    summary = "Attachment analyzed."

    if doc_type == "Certificate":
        title, key_details, action_items, ids, summary, business_value, priority_reason = _find_cert_details(text, dates)
        confidence = max(confidence, 0.82 if key_details else 0.60)
    elif doc_type == "Project Document":
        title = title or _first_match([r"(AI Email Agent[^\n]{0,120})", r"([A-Z][A-Za-z0-9 &,/()\-]{6,120}(?:Development|Release|Requirements|Roadmap)[^\n]{0,80})"], f"{filename}\n{text}") or "Project Document"
        summary = "This appears to be a project or technical document related to product development, implementation, release planning, or engineering work."
        action_items = ["Review the project details if this document is related to current work or requested changes."]
        business_value = "Project context that may help with implementation, planning, or technical decision-making."
        priority_reason = "Project document detected; priority depends on whether the email requests action."
        confidence = max(confidence, 0.68)
    elif doc_type == "Travel Document":
        title = title or "Travel Document"
        summary = "This appears to be a travel-related document such as an itinerary, booking, boarding, hotel, or flight confirmation."
        if dates:
            key_details.append(f"Travel/booking date: {dates[0]}")
        action_items = ["Review travel date, route, confirmation, and check-in details if this trip is still active."]
        business_value = "Travel information that may require review before travel."
        priority_reason = "Travel document detected with travel-specific evidence."
        confidence = max(confidence, 0.70)
    elif doc_type in {"Image", "Screenshot"}:
        meaningful = _meaningful_text(text)
        title = "Screenshot" if doc_type == "Screenshot" else "Image"
        if meaningful:
            summary = "This image contains readable text that may provide context for the email."
            action_items = ["Review the extracted image text if it is relevant to the email."]
            priority_reason = "Image contains meaningful readable text."
            confidence = max(confidence, 0.60)
        else:
            summary = "This image was received, but OCR did not find enough meaningful readable text to summarize confidently."
            action_items = ["Open the image manually if the visual content matters."]
            priority_reason = "Image detected; no strong text evidence found."
            confidence = min(confidence, 0.45)
    elif doc_type == "Offer Letter":
        title = "Offer Letter"
        summary = "This appears to be an employment offer or career document that may require careful review."
        action_items = ["Review role, compensation, start date, and acceptance/signature requirements."]
        business_value = "Career-impacting document that may require timely review."
        priority_reason = "Offer letter detected; likely important and may require response."
        confidence = max(confidence, 0.70)
    else:
        doc_type = "General Document" if doc_type not in DOCUMENT_TYPES else doc_type
        title = title or doc_type
        summary = "This attachment was analyzed, but there was not enough strong evidence to assign a more specific document type confidently."
        action_items = ["Review the document if it is relevant to this email."]
        priority_reason = "General document detected with limited specific evidence."
        confidence = min(confidence, 0.58)

    return {
        "document_type": doc_type,
        "title": title[:220],
        "summary": summary,
        "key_details": key_details[:12],
        "action_items": action_items[:8],
        "dates": dates[:8],
        "amounts": amounts[:8],
        "ids": ids[:8],
        "action_required": any("no reply" not in a.lower() and "no action" not in a.lower() for a in action_items),
        "business_value": business_value,
        "priority_reason": priority_reason,
        "reply_context": f"The attachment is a {doc_type}. {summary}",
        "confidence": round(confidence, 2),
        "evidence_terms": evidence,
        "llm_summary_used": False,
    }


def _normalize_response(data: Dict[str, Any], fallback: Dict[str, Any], filename: str, file_type: str, detected_label: str, text: str, email_subject: str) -> Dict[str, Any]:
    fb_type = fallback.get("document_type", "General Document")
    document_type = _valid_document_type(data.get("document_type"), fb_type)
    evidence_type, evidence_conf, evidence_terms = _evidence_document_type(filename, file_type, detected_label, text, email_subject)
    # Guardrail: prevent confident false Travel based on weak terms.
    if document_type == "Travel Document" and evidence_type != "Travel Document":
        document_type = evidence_type if evidence_type in {"Project Document", "Certificate", "Screenshot", "Image"} else "General Document"
    # Guardrail: avoid forcing specific labels when confidence is weak.
    try:
        raw_conf = float(data.get("confidence", fallback.get("confidence", 0.55)))
    except Exception:
        raw_conf = 0.55
    confidence = max(0.0, min(1.0, max(raw_conf, evidence_conf if document_type == evidence_type else 0.0)))
    if confidence < 0.55 and document_type not in {"Image", "Screenshot"}:
        document_type = "General Document"

    title = str(data.get("title") or fallback.get("title") or document_type).strip()[:220]
    summary = re.sub(r"\s+", " ", str(data.get("summary") or fallback.get("summary") or "Attachment analyzed.").strip())
    if len(summary) > 900:
        summary = summary[:897] + "..."
    key_details = _normalize_list(data.get("key_details"), 12) or fallback.get("key_details", [])
    action_items = _normalize_list(data.get("action_items") or data.get("actions"), 8) or fallback.get("action_items", [])
    dates = _normalize_list(data.get("dates"), 8) or fallback.get("dates", [])
    amounts = _normalize_list(data.get("amounts"), 8) or fallback.get("amounts", [])
    ids = _normalize_list(data.get("ids"), 8) or fallback.get("ids", [])
    action_required = data.get("action_required")
    if isinstance(action_required, str):
        action_required = action_required.strip().lower() in {"true", "yes", "required", "needed"}
    elif action_required is None:
        action_required = bool(fallback.get("action_required", False))
    else:
        action_required = bool(action_required)
    business_value = str(data.get("business_value") or fallback.get("business_value") or "").strip()[:500]
    priority_reason = str(data.get("priority_reason") or fallback.get("priority_reason") or "").strip()[:350]
    reply_context = str(data.get("reply_context") or fallback.get("reply_context") or f"The attachment is a {document_type}.").strip()[:700]
    return {
        "document_type": document_type,
        "title": title,
        "summary": summary,
        "key_details": key_details[:12],
        "action_items": action_items[:8],
        "dates": dates[:8],
        "amounts": amounts[:8],
        "ids": ids[:8],
        "action_required": action_required,
        "business_value": business_value,
        "priority_reason": priority_reason,
        "reply_context": reply_context,
        "confidence": round(confidence, 2),
        "evidence_terms": evidence_terms,
        "llm_summary_used": True,
    }


def _build_user_prompt(filename: str, file_type: str, detected_document_label: str, extracted_text: str, email_subject: str = "", email_sender: str = "", email_snippet: str = "") -> str:
    clean = preclean_extracted_text(extracted_text)
    return f"""
Attachment filename: {filename}
Attachment file type: {file_type}
Initial detected document type: {detected_document_label}
Email sender: {email_sender}
Email subject: {email_subject}
Email snippet: {email_snippet}

Cleaned extracted text:
---
{clean}
---

Return ONLY valid JSON. Do not include markdown.
""".strip()


def _call_ollama(prompt: str) -> Optional[Dict[str, Any]]:
    base_url = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    model = os.getenv("ATTACHMENT_LLM_MODEL") or os.getenv("OLLAMA_MODEL") or "llama3.1"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.05, "num_predict": int(os.getenv("ATTACHMENT_LLM_NUM_PREDICT", "700"))},
    }).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(os.getenv("ATTACHMENT_LLM_TIMEOUT", "20"))) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return _safe_json_loads(((payload.get("message") or {}).get("content") or "").strip())
    except Exception:
        return None


def _call_openai(prompt: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("ATTACHMENT_OPENAI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(os.getenv("ATTACHMENT_LLM_TIMEOUT", "20"))) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return _safe_json_loads(payload["choices"][0]["message"]["content"])
    except Exception:
        return None


def summarize_attachment_with_llm(filename: str, file_type: str, detected_document_label: str, extracted_text: str, email_subject: str = "", email_sender: str = "", email_snippet: str = "", dates: Optional[List[str]] = None, amounts: Optional[List[str]] = None) -> Dict[str, Any]:
    cleaned_text = preclean_extracted_text(extracted_text)
    fallback = _fallback_summary(filename, file_type, detected_document_label, cleaned_text, dates=dates, amounts=amounts, email_subject=email_subject)
    if not cleaned_text:
        return fallback
    prompt = _build_user_prompt(filename, file_type, detected_document_label, cleaned_text, email_subject, email_sender, email_snippet)
    data = None
    if os.getenv("OPENAI_API_KEY"):
        data = _call_openai(prompt)
    elif (os.getenv("ATTACHMENT_USE_OLLAMA") or os.getenv("USE_OLLAMA") or "").lower() in {"1", "true", "yes", "on"}:
        data = _call_ollama(prompt)
    if not data:
        return fallback
    normalized = _normalize_response(data, fallback, filename, file_type, detected_document_label, cleaned_text, email_subject)
    if not normalized.get("dates") and dates:
        normalized["dates"] = dates[:8]
    if not normalized.get("amounts") and amounts:
        normalized["amounts"] = amounts[:8]
    if not normalized.get("ids") and fallback.get("ids"):
        normalized["ids"] = fallback["ids"]
    return normalized
