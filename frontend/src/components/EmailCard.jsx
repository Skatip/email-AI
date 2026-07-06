import { useEffect, useMemo, useState } from "react";
import * as BadgeModule from "./Badge";
import {
  generateReply,
  fetchMultiReply,
  sendFeedback,
  saveReplyExample,
  fetchThreadSummary,
  createFollowup,
  analyzeAttachment,
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


function shouldOfferReply(item) {
  const senderBand = String(item?.sender_band || "").toUpperCase();
  const senderType = String(item?.human_signals?.sender_type || item?.sender_type || "").toUpperCase();
  const intent = String(item?.intent || "").toLowerCase();
  const category = String(
    item?.email_type ||
    item?.email_category ||
    item?.category ||
    item?.human_signals?.email_type ||
    item?.human_signals?.email_category ||
    item?.human_signals?.category ||
    ""
  ).toLowerCase();
  const text = `${item?.subject || ""} ${item?.snippet || ""}`.toLowerCase();

  if (item?.respond_recommended === false) return false;

  const noReplyBands = ["BULK", "PLATFORM", "AUTOMATED"];
  const noReplyTypes = ["AUTOMATED", "BULK", "PLATFORM"];
  const noReplyCategories = ["promotional", "promotion", "promo", "bill", "billing", "security", "spam", "automated", "notification", "transactional", "transactional_system"];
  const noReplyIntents = ["security", "bill", "billing", "promotion", "promotional", "spam", "notification", "transactional_system", "general"];
  const noReplyText = ["paperless", "document is ready", "security zone", "verification code", "confirmation", "statement", "unsubscribe", "do not reply", "no-reply", "noreply", "offer", "rewards", "enrolled in paperless"];

  if (noReplyBands.includes(senderBand)) return false;
  if (noReplyTypes.includes(senderType)) return false;
  if (noReplyCategories.includes(category)) return false;
  if (noReplyIntents.includes(intent) && noReplyText.some((x) => text.includes(x))) return false;
  if (noReplyText.some((x) => text.includes(x))) return false;

  return true;
}

function noReplyReason(item) {
  const intent = String(item?.intent || "email").toLowerCase();
  const category = String(item?.email_type || item?.email_category || item?.category || "").toLowerCase();
  const senderType = String(item?.human_signals?.sender_type || item?.sender_type || "").toUpperCase();
  if (senderType === "AUTOMATED") return "No reply needed for automated email.";
  if (["security", "bill", "billing", "spam", "promotional", "promotion", "transactional"].includes(category)) return `No reply needed for ${category} email.`;
  if (["security", "bill", "billing", "spam", "promotional", "promotion"].includes(intent)) return `No reply needed for ${intent} email.`;
  if (item?.respond_recommended === false) return "AI says no reply is needed.";
  return "No reply needed for this notification.";
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

function isFamilyPersonal(item) {
  const rel = String(item?.relationship_type || item?.relationship || item?.human_signals?.relationship_type || "").toLowerCase();
  const senderType = String(item?.human_signals?.sender_type || item?.sender_type || "").toUpperCase();
  return rel.includes("family") || rel.includes("personal") || senderType === "PERSONAL";
}

function isSecurityRelated(item) {
  const joined = [
    item?.intent,
    item?.email_type,
    item?.email_category,
    item?.category,
    item?.subject,
    item?.snippet,
    item?.human_signals?.domain,
  ].filter(Boolean).join(" ").toLowerCase();
  return joined.includes("security") || joined.includes("password") || joined.includes("verification") || joined.includes("sign in") || joined.includes("login");
}

function attachmentIcon(type) {
  const t = String(type || "").toLowerCase();
  if (t === "pdf") return "📄";
  if (t === "word") return "📝";
  if (t === "excel" || t === "csv") return "📊";
  if (t === "image") return "🖼️";
  if (t === "video") return "🎥";
  if (t === "archive") return "📦";
  if (t === "risky_executable") return "⚠️";
  return "📎";
}

function shortFileName(name, n = 36) {
  const s = String(name || "attachment");
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

function attachmentDocLabel(att, result) {
  return result?.document_label || att?.document_label || String(att?.file_type || "file").toUpperCase();
}

function uniqueAttachmentResults(item, localResults) {
  const local = Object.values(localResults || {}).filter(Boolean);
  const saved = Array.isArray(item?.attachment_analysis) ? item.attachment_analysis : [];
  const all = [...saved, ...local];
  const seen = new Set();
  const out = [];
  for (const x of all) {
    const key = String(x?.filename || "") + "|" + String(x?.document_type || "");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(x);
  }
  return out;
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
  const [attachmentResults, setAttachmentResults] = useState({});
  const [loadingAttachment, setLoadingAttachment] = useState("");

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
    setAttachmentResults({});
    setLoadingAttachment("");
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

  const canReply = shouldOfferReply(item);
  const familyPersonal = isFamilyPersonal(item);
  const securityRelated = isSecurityRelated(item);
  const attachments = Array.isArray(item?.attachments) ? item.attachments : [];
  const attachmentAnalyses = uniqueAttachmentResults(item, attachmentResults);

  async function onAnalyzeAttachment(att) {
    const key = String(att?.attachment_id || att?.filename || "attachment");
    setErr("");
    setLoadingAttachment(key);

    try {
      const res = await analyzeAttachment({
        provider: item?.provider || "gmail",
        message_id: item?.id,
        attachment: att,
        sender_band: item?.sender_band || "",
        source_folder: item?.source_folder || "",
        email_subject: item?.subject || "",
        email_sender: item?.from || "",
        email_snippet: item?.snippet || "",
      });

      setAttachmentResults((prev) => ({ ...prev, [key]: res }));

      const existing = Array.isArray(item?.attachment_analysis) ? item.attachment_analysis : [];
      const nextAnalysis = [...existing.filter((x) => x?.filename !== res?.filename), res];
      const boost = Math.max(Number(item?.attachment_priority_boost || 0), Number(res?.priority_boost || 0));
      const basePriority = Number(item?.priority || 0);
      const patchedPriority = Math.min(1, basePriority + boost);

      onPatchItem?.({
        attachment_analysis: nextAnalysis,
        attachment_priority_boost: boost,
        priority: patchedPriority,
        attachment_reply_context: nextAnalysis.map((x) => x?.reply_context).filter(Boolean).join("\n"),
      });
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setLoadingAttachment("");
    }
  }

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
    if (!canReply) {
      setDraft({
        reply: "",
        tone: "none",
        confidence: 1,
        safety_blocked: true,
        safety_reason: noReplyReason(item),
        reply_meta: { suppressed: true, suppress_reason: noReplyReason(item) },
      });
      return;
    }

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
        attachments: item?.attachments || [],
        attachment_analysis: item?.attachment_analysis || [],
        attachment_reply_context: item?.attachment_reply_context || "",
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
          attachments: item?.attachments || [],
          attachment_analysis: item?.attachment_analysis || [],
          attachment_reply_context: item?.attachment_reply_context || "",
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
      className={`emailCard redesign ${selected ? "selected" : ""} ${familyPersonal ? "familyHighlight" : ""} ${securityRelated ? "securityHighlight" : ""}`}
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

        {attachments.length > 0 && (
          <div className="attachmentRow" onClick={(e) => e.stopPropagation()}>
            {attachments.map((att, idx) => {
              const key = String(att?.attachment_id || att?.filename || idx);
              const result = attachmentResults[key] || (item?.attachment_analysis || []).find((x) => x?.filename === att?.filename);
              const risky = ["medium", "high"].includes(String((result || att)?.risk_level || "").toLowerCase());
              const analyzed = Boolean(result);

              return (
                <div key={key} className={`attachmentChip ${risky ? "risky" : ""} ${analyzed ? "analyzed" : ""}`}>
                  <span>
                    {attachmentIcon(att?.file_type)} {shortFileName(att?.filename)}
                  </span>

                  <small>{attachmentDocLabel(att, result)}</small>

                  <button
                    className="microBtn"
                    type="button"
                    disabled={loadingAttachment === key}
                    onClick={() => onAnalyzeAttachment(att)}
                  >
                    {loadingAttachment === key ? "Analyzing..." : analyzed ? "✓ Analyzed" : "Analyze"}
                  </button>

                  {result && (
                    <div className={`attachmentAnalysis ${result.risk_level || "low"}`}>
                      <div className="attachmentAnalysisHead">
                        <b>{result.document_label || "Document Intelligence"}</b>
                        {result.llm_summary_used ? <span>AI summary</span> : null}
                        {result.priority_boost ? <span>+{Math.round(Number(result.priority_boost) * 100)} priority</span> : null}
                      </div>

                      {result.title && <div className="attachmentDocTitle">{result.title}</div>}
                      <p>{result.summary}</p>

                      {result.business_value && (
                        <div className="attachmentBusinessValue">
                          <b>Why it matters:</b> {result.business_value}
                        </div>
                      )}

                      {(result.key_details || []).length > 0 && (
                        <div className="attachmentKeyDetails">
                          <b>Key details:</b>
                          {(result.key_details || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}

                      {(result.action_items || []).length > 0 && (
                        <div>
                          <b>Actions:</b>
                          {(result.action_items || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}

                      {(result.dates || []).length > 0 && (
                        <div><b>Dates:</b> {result.dates.join(", ")}</div>
                      )}

                      {(result.amounts || []).length > 0 && (
                        <div><b>Amounts:</b> {result.amounts.join(", ")}</div>
                      )}

                      {(result.ids || []).length > 0 && (
                        <div><b>IDs:</b> {result.ids.join(", ")}</div>
                      )}

                      {result.priority_reason && (
                        <div><b>Priority reason:</b> {result.priority_reason}</div>
                      )}

                      {(result.risk_reasons || []).length > 0 && (
                        <div>
                          <b>Risk:</b>
                          {(result.risk_reasons || []).map((x, i) => (
                            <div key={i}>• {x}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}


        <div className="tagRow">
          {familyPersonal && (
            <span className="glassTag signalIcon familySignal">👨‍👩‍👧 Family / Personal</span>
          )}

          {securityRelated && (
            <span className="glassTag signalIcon securitySignal">🔐 Security</span>
          )}

          {attachmentAnalyses.map((a, i) => (
            <span key={`${a?.filename || i}-${a?.document_type || "doc"}`} className={`glassTag attachmentType ${String(a?.document_type || "").toLowerCase()}`}>
              📎 {a?.document_label || a?.document_type || "Attachment"}
            </span>
          ))}

          <span className={`glassTag band ${String(item?.sender_band || "UNKNOWN").toLowerCase()}`}>
            {item?.sender_band || "UNKNOWN"}
          </span>

          <span className={`glassTag type ${senderType.toLowerCase()} ${familyPersonal ? "highlightIcon" : ""}`}>
            {senderTypeIcon(senderType)} {senderType}
          </span>

          {item?.source_folder && (
            <span className={`glassTag source ${String(item.source_folder).toLowerCase()}`}>
              {String(item.source_folder).toUpperCase()}
            </span>
          )}

          {item?.email_type && (
            <span className={`glassTag emailtype ${String(item.email_type).toLowerCase()}`}>
              {String(item.email_type).replaceAll("_", " ")}
            </span>
          )}

          {item?.relationship_type && (
            <span className={`glassTag relationship ${String(item.relationship_type).toLowerCase()}`}>
              {String(item.relationship_type).replaceAll("_", " ")}
            </span>
          )}

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
            disabled={loadingDraft || !canReply}
            title={!canReply ? noReplyReason(item) : "Generate a human-like reply"}
            type="button"
          >
            {!canReply ? "No reply needed" : loadingDraft ? "Generating..." : draft ? "Regenerate reply" : "Generate reply"}
          </button>

          <button
            className="softBtn"
            onClick={onGenerateMulti}
            disabled={loadingMulti || !canReply}
            title={!canReply ? noReplyReason(item) : "Generate multiple reply options"}
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

        {!canReply && <div className="notice subtleNotice">{noReplyReason(item)}</div>}
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

            {attachmentAnalyses.length > 0 && (
              <div className="reasonBox">
                <div className="sectionLabel">Attachment Intelligence</div>
                <div className="reasonText attachmentPanelText">
                  {attachmentAnalyses.map((a, i) => (
                    <div key={`${a?.filename || i}-panel`} className="attachmentPanelItem">
                      <b>{a?.document_label || "Attachment"}</b> — {a?.filename}
                      {a?.priority_boost ? <span> • priority boost +{Math.round(Number(a.priority_boost) * 100)}</span> : null}
                      {a?.llm_summary_used ? <span> • AI summary</span> : null}
                      {a?.title ? <div><b>Title:</b> {a.title}</div> : null}
                      <div>{a?.summary || "No attachment summary available."}</div>
                      {a?.business_value ? <div><b>Why it matters:</b> {a.business_value}</div> : null}
                      {(a?.key_details || []).length > 0 && (
                        <div>Key details: {(a.key_details || []).join("; ")}</div>
                      )}
                      {(a?.action_items || []).length > 0 && (
                        <div>Actions: {(a.action_items || []).join("; ")}</div>
                      )}
                      {(a?.ids || []).length > 0 && (
                        <div>IDs: {(a.ids || []).join("; ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

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