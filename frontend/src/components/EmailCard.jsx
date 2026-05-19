import { useEffect, useMemo, useState } from "react";
import * as BadgeModule from "./Badge";
import {
  generateReply,
  fetchMultiReply,
  sendFeedback,
  saveReplyExample,
  fetchThreadSummary,
  createFollowup,
} from "../api";

const Badge = BadgeModule.Badge || BadgeModule.default;

function pct(x) {
  const n = Number(x || 0);
  return `${Math.round(n * 100)}%`;
}

function decodeHtml(s) {
  const str = String(s || "");
  if (!str) return "";
  if (typeof document === "undefined") return str;
  if (!str.includes("&")) return str;
  const txt = document.createElement("textarea");
  txt.innerHTML = str;
  return txt.value;
}

function clampText(s, n = 170) {
  const str = decodeHtml((s || "").trim());
  if (!str) return "";
  return str.length > n ? str.slice(0, n - 1) + "…" : str;
}

function normalizeDraftPayload(payload) {
  const p = payload || {};
  const meta = p.meta || p.reply_meta || {};

  const replyText =
    p.reply ??
    p.text ??
    meta.reply ??
    meta.text ??
    meta.draft ??
    "";

  const tone = (meta.tone ?? p.tone ?? "professional") || "professional";

  let conf =
    meta.confidence ??
    meta.conf ??
    p.confidence ??
    p.conf ??
    0.85;

  conf = Number(conf || 0);
  if (conf > 1.0) conf = conf / 100.0;

  return {
    reply: String(replyText || ""),
    tone: String(tone),
    confidence: conf,
    safety_blocked: Boolean(meta.safety_blocked ?? p.safety_blocked ?? false),
    safety_reason: String(meta.safety_reason ?? p.safety_reason ?? ""),
    reply_meta: meta.reply_meta ?? p.reply_meta ?? meta ?? null,
  };
}

function seedDraftFromItem(item) {
  if (!item) return null;

  const replyText =
    item?.suggested_reply ??
    item?.reply?.text ??
    item?.reply?.reply ??
    item?.reply ??
    "";

  const meta =
    item?.suggested_reply_meta ??
    item?.reply?.meta ??
    item?.reply_meta ??
    null;

  if (!replyText && !meta) return null;

  return normalizeDraftPayload({
    reply: replyText,
    meta: meta || {},
  });
}

function priorityClass(label) {
  const v = String(label || "").toUpperCase();
  if (v === "HIGH") return "high";
  if (v === "MEDIUM") return "medium";
  return "low";
}

function riskClass(risk) {
  const n = Number(risk || 0);
  if (n >= 0.6) return "high";
  if (n >= 0.25) return "medium";
  return "low";
}

function senderTypeIcon(type) {
  if (type === "PERSONAL") return "👤";
  if (type === "COMPANY") return "🏢";
  if (type === "AUTOMATED") return "🤖";
  return "❔";
}

function icon(cat) {
  if (cat === "IMPORTANT") return "⭐";
  if (cat === "LESS") return "🕓";
  if (cat === "SPAM") return "🚫";
  if (cat === "PROMO") return "🏷️";
  return "";
}

function formatThreadSummary(res) {
  if (!res || typeof res !== "object") {
    return "No summary returned.";
  }

  const summary = String(res.summary || "").trim();
  const actionItems = Array.isArray(res.action_items) ? res.action_items : [];
  const decisions = Array.isArray(res.decisions) ? res.decisions : [];
  const timeline = Array.isArray(res.timeline) ? res.timeline : [];
  const participants = Array.isArray(res.participants) ? res.participants : [];

  let out = "";

  if (summary) {
    out += `Summary:\n${summary}\n\n`;
  }

  if (actionItems.length) {
    out += "Action Items:\n";
    out += actionItems.map((x) => `- ${x}`).join("\n");
    out += "\n\n";
  }

  if (decisions.length) {
    out += "Decisions:\n";
    out += decisions.map((x) => `- ${typeof x === "string" ? x : JSON.stringify(x)}`).join("\n");
    out += "\n\n";
  }

  if (timeline.length) {
    out += "Timeline:\n";
    out += timeline.map((x) => {
      if (typeof x === "string") return `- ${x}`;
      return `- ${x.from || "Someone"}: ${x.event || x.subject || JSON.stringify(x)}`;
    }).join("\n");
    out += "\n\n";
  }

  if (participants.length) {
    out += "Participants:\n";
    out += participants.map((x) => `- ${x}`).join("\n");
  }

  return out.trim() || "No summary returned.";
}

export default function EmailCard({ item, onPatchItem, selected, onSelect }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(() => seedDraftFromItem(item));
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editedText, setEditedText] = useState("");
  const [savingExample, setSavingExample] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  const [threadSummary, setThreadSummary] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [followMsg, setFollowMsg] = useState("");
  const [multiReplies, setMultiReplies] = useState([]);
  const [loadingMulti, setLoadingMulti] = useState(false);

  useEffect(() => {
    const d = seedDraftFromItem(item);
    setDraft(d);
    setEditing(false);
    setEditedText(d?.reply || "");
    setErr("");
    setCopied(false);
    setSavedMsg("");
    setThreadSummary("");
    setFollowMsg("");
    setMultiReplies([]);
  }, [item?.id]);

  const subject = decodeHtml(item?.subject || "(no subject)");
  const from = decodeHtml(item?.from || "(no sender)");
  const preview = useMemo(() => clampText(item?.snippet || ""), [item?.snippet]);

  const badgeTone =
    item?.label === "HIGH" ? "red" : item?.label === "MEDIUM" ? "yellow" : "green";

  const userCat = (item?.user_pref?.user_category || "").toUpperCase();
  const showPref = ["IMPORTANT", "LESS", "SPAM", "PROMO"].includes(userCat);

  const senderType =
    String(
      item?.human_signals?.sender_type ||
      item?.sender_type ||
      "UNKNOWN"
    ).toUpperCase();

  async function onFeedback(clicked) {
    setErr("");
    try {
      const senderEmail = String(item?.from || "").match(/<([^>]+)>/)?.[1] || "";

      onPatchItem?.({
        user_pref: {
          user_category: clicked,
          user_category_confidence: 1.0,
          user_category_source: "manual",
          user_category_evidence: 1,
        },
      });

      await sendFeedback({
        action: "label_email",
        email_id: item?.id,
        sender_email: senderEmail,
        clicked,
        subject: item?.subject || "",
        snippet: item?.snippet || "",
        provider: item?.provider || "gmail",
        meta: { ui: "emailcard" },
      });
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  async function onSaveExample(useEdited = false) {
    if (!draft?.reply && !editedText) return;
    setSavingExample(true);
    setSavedMsg("");
    setErr("");

    try {
      const inbound = [item?.subject || "", item?.snippet || ""]
        .filter(Boolean)
        .join("\n\n");

      const outbound = useEdited
        ? String(editedText || "").trim()
        : String(draft?.reply || "").trim();

      if (!outbound) throw new Error("Reply text is empty.");

      await saveReplyExample({
        inbound,
        outbound,
        label: "style",
      });

      setSavedMsg("Saved to style memory");
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setSavingExample(false);
    }
  }

  async function onGenerateOrRegenerate() {
    setLoadingDraft(true);
    setErr("");

    try {
      const email = {
        id: item?.id,
        from: item?.from,
        subject: item?.subject,
        snippet: item?.snippet,
        body: item?.body || "",
        ts: item?.ts,
        provider: item?.provider || "gmail",
        threadId: item?.threadId || "",
      };

      const analysis = { ...item };

      const out = await generateReply({
        email,
        analysis,
        force: false,
      });

      const d = normalizeDraftPayload(out);
      setDraft(d);
      setEditedText(d?.reply || "");
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingDraft(false);
    }
  }

  async function onGenerateMulti() {
    setLoadingMulti(true);
    setErr("");
    setMultiReplies([]);

    try {
      const res = await fetchMultiReply({
        email: {
          id: item?.id,
          from: item?.from,
          subject: item?.subject,
          snippet: item?.snippet,
          body: item?.body || "",
          ts: item?.ts,
          provider: item?.provider || "gmail",
          threadId: item?.threadId || "",
        },
        analysis: { ...item },
      });

      setMultiReplies(Array.isArray(res?.options) ? res.options : []);
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingMulti(false);
    }
  }

  async function onSummarizeThread() {
    setLoadingSummary(true);
    setThreadSummary("");
    setErr("");

    try {
      if (!item?.threadId) {
        throw new Error("Missing threadId for this email.");
      }

      const res = await fetchThreadSummary(item.threadId, item?.provider || "gmail", item);
      setThreadSummary(formatThreadSummary(res));
    } catch (e) {
      setErr(String(e?.message || e));
      setThreadSummary("Error generating summary");
    } finally {
      setLoadingSummary(false);
    }
  }

  async function onCreateFollowup() {
    setErr("");
    setFollowMsg("");

    try {
      await createFollowup({
        email_id: item?.id,
        thread_id: item?.threadId || "",
        remind_at: Math.floor(Date.now() / 1000) + 3600,
        note: "Follow up on this email",
        subject: item?.subject || "",
        sender: item?.from || "",
        provider: item?.provider || "gmail",
      });
      setFollowMsg("Follow-up set");
    } catch (e) {
      setErr(String(e?.message || e));
      setFollowMsg("Failed to set reminder");
    }
  }

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(editing ? editedText : draft?.reply || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      setErr("Copy failed.");
    }
  }

  if (!Badge) {
    return <div style={{ padding: 16, color: "crimson" }}>Badge import failed.</div>;
  }

  return (
    <article
      className={`emailCard redesign ${selected ? "selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect?.();
        }
      }}
    >
      <div className={`priorityRail ${priorityClass(item?.label)}`} />

      <div className="cardMain">
        <div className="cardTop">
          <div className="leftTop">
            <div className="subjectRow">
              <h3 className="subject">{subject}</h3>
              <Badge tone={badgeTone}>{item?.label}</Badge>
            </div>

            <div className="fromLine">{from}</div>
          </div>

          <div className="scoreStack">
            <div className={`scorePill ${priorityClass(item?.label)}`}>
              Priority {pct(item?.priority)}
            </div>
            <div className={`scorePill ${riskClass(item?.risk)}`}>
              Risk {pct(item?.risk)}
            </div>
          </div>
        </div>

        {preview && <p className="preview">{preview}</p>}

        <div className="tagRow">
          <span className={`glassTag band ${String(item?.sender_band || "UNKNOWN").toLowerCase()}`}>
            {item?.sender_band || "UNKNOWN"}
          </span>

          <span className={`glassTag type ${senderType.toLowerCase()}`}>
            {senderTypeIcon(senderType)} {senderType}
          </span>

          {item?.intent && <span className="glassTag neutral">{item.intent}</span>}

          {showPref && (
            <span className={`glassTag pref ${userCat.toLowerCase()}`}>
              {icon(userCat)} {userCat}
            </span>
          )}
        </div>

        <div className="primaryActions" onClick={(e) => e.stopPropagation()}>
          <button className="softBtn" onClick={() => setOpen((v) => !v)} type="button">
            {open ? "Hide analysis" : "Show analysis"}
          </button>

          <button
            className="softBtn primary"
            onClick={onGenerateOrRegenerate}
            disabled={loadingDraft}
            type="button"
          >
            {loadingDraft ? "Generating..." : draft ? "Regenerate reply" : "Generate reply"}
          </button>

          <button
            className="softBtn"
            onClick={onGenerateMulti}
            disabled={loadingMulti}
            type="button"
          >
            {loadingMulti ? "Generating..." : "Multi Reply"}
          </button>

          <button
            className="softBtn"
            onClick={onSummarizeThread}
            disabled={loadingSummary}
            type="button"
          >
            {loadingSummary ? "Summarizing..." : "Summarize Thread"}
          </button>

          <button
            className="softBtn"
            onClick={onCreateFollowup}
            type="button"
          >
            Follow-up
          </button>

          {draft && !draft.safety_blocked && (
            <button className="softBtn" onClick={onCopy} type="button">
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>

        <div className="feedbackRow" onClick={(e) => e.stopPropagation()}>
          <button className="microBtn" onClick={() => onFeedback("IMPORTANT")} type="button">
            ⭐ Important
          </button>
          <button className="microBtn" onClick={() => onFeedback("LESS")} type="button">
            🕓 Less
          </button>
          <button className="microBtn" onClick={() => onFeedback("SPAM")} type="button">
            🚫 Spam
          </button>
          <button className="microBtn" onClick={() => onFeedback("PROMO")} type="button">
            🏷️ Promo
          </button>
        </div>

        {savedMsg && <div className="notice">{savedMsg}</div>}
        {followMsg && <div className="notice">{followMsg}</div>}
        {err && <div className="error">{err}</div>}

        {open && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="analysisGrid">
              <div className="analysisBox">
                <span>Priority</span>
                <strong>{pct(item?.priority)}</strong>
              </div>

              <div className="analysisBox">
                <span>Risk</span>
                <strong>{pct(item?.risk)}</strong>
              </div>

              <div className="analysisBox">
                <span>Sender Band</span>
                <strong>{item?.sender_band || "UNKNOWN"}</strong>
              </div>

              <div className="analysisBox">
                <span>Intent</span>
                <strong>{item?.intent || "Unknown"}</strong>
              </div>
            </div>

            <div className="reasonBox">
              <div className="sectionLabel">Why this matters</div>
              <div className="reasonText">{item?.reason || "No explanation available."}</div>
            </div>

            <div className="reasonBox">
              <div className="sectionLabel">Risk Explanation</div>
              <div className="reasonText">
                {(item?.risk_reasons || item?.human_signals?.risk_reasons || []).length
                  ? (item?.risk_reasons || item?.human_signals?.risk_reasons || []).map((x, i) => <div key={i}>• {x}</div>)
                  : "No major risk signals detected."}
              </div>
            </div>
          </div>
        )}

        {threadSummary && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="sectionLabel">Thread Summary</div>
            <div className="reasonText" style={{ whiteSpace: "pre-wrap" }}>
              {threadSummary}
            </div>
          </div>
        )}

        {multiReplies.length > 0 && (
          <div className="analysisPanel" onClick={(e) => e.stopPropagation()}>
            <div className="sectionLabel">Multi Reply Options</div>
            <div className="reasonText" style={{ whiteSpace: "pre-wrap" }}>
              {multiReplies.map((r, i) => `${i + 1}. ${r}`).join("\n\n")}
            </div>
          </div>
        )}

        {draft && (
          <div className="draftShell" onClick={(e) => e.stopPropagation()}>
            {draft.safety_blocked ? (
              <div className="muted">
                <b>Draft blocked:</b> {draft.safety_reason}
              </div>
            ) : (
              <>
                <div className="draftTop">
                  <div>
                    <div className="draftTitle">Suggested Reply</div>
                    <div className="draftMeta">
                      tone: {draft.tone} • conf: {Math.round((draft.confidence || 0) * 100)}%
                    </div>
                  </div>

                  <div className="draftActionRow">
                    <button
                      className="softBtn"
                      onClick={() => {
                        setEditing((v) => !v);
                        setEditedText(draft?.reply || "");
                      }}
                      type="button"
                    >
                      {editing ? "Cancel" : "Edit"}
                    </button>

                    <button
                      className="softBtn"
                      onClick={() => onSaveExample(false)}
                      disabled={savingExample}
                      type="button"
                    >
                      {savingExample ? "Saving..." : "Use this"}
                    </button>

                    {editing && (
                      <button
                        className="softBtn primary"
                        onClick={() => onSaveExample(true)}
                        disabled={savingExample}
                        type="button"
                      >
                        {savingExample ? "Saving..." : "Save edited"}
                      </button>
                    )}
                  </div>
                </div>

                {editing ? (
                  <textarea
                    className="draftEdit"
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                  />
                ) : (
                  <pre className="draftText">{String(draft.reply || "")}</pre>
                )}

                {draft.reply_meta && (
                  <div className="draftFoot">
                    regen: {draft.reply_meta.regenerated ? "yes" : "no"} • used_rag:{" "}
                    {String(draft.reply_meta.used_rag)} • suppressed:{" "}
                    {String(draft.reply_meta.suppressed || false)}
                    {draft.reply_meta.reply_intent ? ` • intent: ${draft.reply_meta.reply_intent}` : ""}
                    {draft.reply_meta.strategy ? ` • strategy: ${draft.reply_meta.strategy}` : ""}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </article>
  );
}