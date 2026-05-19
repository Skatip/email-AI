const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function handle(res) {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return await res.json();
}


export async function fetchInbox({ maxResults = 10, userEmail = "", provider = "gmail", query = "" } = {}) {
  const url =
    `${API_BASE}/inbox?max_results=${encodeURIComponent(maxResults)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}` +
    `&query=${encodeURIComponent(query)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function analyzeEmail(payload) {
  const res = await fetch(`${API_BASE}/email/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchAnalysis({ maxResults = 10, userEmail = "", provider = "gmail", query = "" } = {}) {
  const url =
    `${API_BASE}/analyze?max_results=${encodeURIComponent(maxResults)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}` +
    `&query=${encodeURIComponent(query)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function fetchDrafts({ maxResults = 5, replyTopN = 1, userEmail = "", provider = "gmail" } = {}) {
  const url =
    `${API_BASE}/analyze?max_results=${encodeURIComponent(maxResults)}` +
    `&include_reply=true` +
    `&reply_top_n=${encodeURIComponent(replyTopN)}` +
    `&user_email=${encodeURIComponent(userEmail)}` +
    `&provider=${encodeURIComponent(provider)}`;
  const res = await fetch(url);
  return await handle(res);
}

export async function generateReply(payload) {
  const res = await fetch(`${API_BASE}/reply/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchMultiReply(payload) {
  const res = await fetch(`${API_BASE}/reply/multi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function sendFeedback(payload) {
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function saveReplyExample(payload) {
  const res = await fetch(`${API_BASE}/reply/save_example`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchThreadSummary(threadId, provider = "gmail", email = null) {
  const res = await fetch(`${API_BASE}/thread/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, provider, email }),
  });
  return await handle(res);
}

export async function fetchFullThread(threadId, provider = "gmail") {
  const res = await fetch(
    `${API_BASE}/thread/full?thread_id=${encodeURIComponent(threadId)}&provider=${encodeURIComponent(provider)}`
  );
  return await handle(res);
}

export async function createFollowup(payload) {
  const res = await fetch(`${API_BASE}/followups/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}

export async function fetchFollowups(status = "") {
  const res = await fetch(`${API_BASE}/followups?status=${encodeURIComponent(status)}`);
  return await handle(res);
}

export async function fetchDueFollowups() {
  const res = await fetch(`${API_BASE}/followups/due`);
  return await handle(res);
}

export async function updateFollowupStatus(id, status) {
  const res = await fetch(`${API_BASE}/followups/${encodeURIComponent(id)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return await handle(res);
}

export async function fetchAnalytics(days = 14) {
  const res = await fetch(`${API_BASE}/analytics?days=${encodeURIComponent(days)}`);
  return await handle(res);
}

export async function composeFromNotes(payload) {
  const res = await fetch(`${API_BASE}/compose/from-notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return await handle(res);
}
