// src/mocks/outlookData.js
export const mockOutlookEmails = [
  {
    id: "outlook_msg_001",
    from: "Satya Nadella <satya@microsoft.com>",
    subject: "Future of AI Integration",
    snippet: "I saw your new AI email system and I'm impressed...",
    priority: 0.95,
    label: "HIGH",
    reason: "VIP Sender + Strategic Intent",
    intent: "action-required",
    sender_band: "TRUSTED",
    risk: "LOW",
    ts: 1711924800,
    provider: "outlook",
    body: "Hi Team, the AI system looks robust. Let's discuss a partnership."
  },
  {
    id: "outlook_msg_002",
    from: "Azure Security <security@microsoft.com>",
    subject: "Security Info Update",
    snippet: "Your security info will be updated on 4/30/2026...",
    priority: 0.85,
    label: "HIGH",
    reason: "Temporal Signal (30-day lock)",
    intent: "informational",
    sender_band: "PLATFORM",
    risk: "LOW",
    ts: 1711910000,
    provider: "outlook",
    body: "This is an automated notification regarding your security changes."
  }
];