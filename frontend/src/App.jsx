import { useEffect, useMemo, useState } from "react";
import {
  fetchInbox,
  analyzeEmail,
  fetchAnalytics,
  fetchDueFollowups,
  fetchFollowups,
  updateFollowupStatus,
} from "./api";
import EmailCard from "./components/EmailCard";
import DetailPanel from "./components/DetailPanel";
import ProviderLogo from "./components/ProviderLogo";
import "./styles.css";

const PROVIDERS = [
  {
    id: "gmail",
    name: "Gmail",
    logo: "gmail",
    email: import.meta.env.VITE_GMAIL_USER || "",
    color: "gmail",
    description: "Analyze Gmail inbox with priority, risk, replies, summaries, and reminders.",
  },
  {
    id: "outlook",
    name: "Outlook",
    logo: "outlook",
    email: import.meta.env.VITE_OUTLOOK_USER || "",
    color: "outlook",
    description: "Analyze Outlook inbox. Slack and Jira can be added later.",
  },
];

function pct(x) {
  return `${Math.round(Number(x || 0) * 100)}%`;
}

function fmtTime(ts) {
  if (!ts) return "No time";
  const n = Number(ts) * 1000;
  if (!Number.isFinite(n)) return "No time";
  return new Date(n).toLocaleString();
}


function attachmentSearchText(it) {
  const attachments = Array.isArray(it?.attachments) ? it.attachments : [];
  const analyses = Array.isArray(it?.attachment_analysis) ? it.attachment_analysis : [];
  return [
    ...attachments.map((a) => `${a?.filename || ""} ${a?.file_type || ""} ${a?.mime_type || ""}`),
    ...analyses.map((a) => `${a?.filename || ""} ${a?.document_type || ""} ${a?.document_label || ""} ${a?.summary || ""}`),
  ].join(" ");
}

function hasAttachmentDocType(it, docType) {
  const analyses = Array.isArray(it?.attachment_analysis) ? it.attachment_analysis : [];
  const attachments = Array.isArray(it?.attachments) ? it.attachments : [];
  const target = String(docType || "").toLowerCase();
  return analyses.some((a) => String(a?.document_type || "").toLowerCase() === target) ||
    attachments.some((a) => String(a?.file_type || "").toLowerCase() === target);
}

function ThemeToggle({ theme, toggleTheme }) {
  return (
    <button className="themeToggle" onClick={toggleTheme}>
      {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
    </button>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="statCard">
      <span>{label}</span>
      <b>{value}</b>
      {sub && <small>{sub}</small>}
    </div>
  );
}

function MiniBar({ label, value, max }) {
  const width = max > 0 ? Math.max(4, Math.round((Number(value || 0) / max) * 100)) : 0;
  return (
    <div className="miniBarRow">
      <span>{label}</span>
      <div className="miniBarTrack">
        <i style={{ width: `${width}%` }} />
      </div>
      <b>{value}</b>
    </div>
  );
}

function LandingPage({ onChoose, theme, toggleTheme }) {
  return (
    <main className="landingPage">
      <div className="landingTheme">
        <ThemeToggle theme={theme} toggleTheme={toggleTheme} />
      </div>

      <section className="heroCard">
        <div className="heroKicker">AI Email Command Center</div>
        <h1>Choose your workspace</h1>
        <p>
          Start with Gmail or Outlook now. Later, Slack and Jira can plug into the same launcher.
        </p>

        <div className="providerGrid">
          {PROVIDERS.map((p) => (
            <button key={p.id} className={`providerTile ${p.color}`} onClick={() => onChoose(p)}>
              <div className="providerIcon"><ProviderLogo type={p.logo} size={34} /></div>
              <div>
                <h2>{p.name}</h2>
                <p>{p.description}</p>
                <small>{p.email}</small>
              </div>
            </button>
          ))}

          <button className="providerTile disabled" disabled>
            <div className="providerIcon"><ProviderLogo type="slack" size={34} /></div>
            <div>
              <h2>Slack</h2>
              <p>Coming later for action items and team messages.</p>
            </div>
          </button>

          <button className="providerTile disabled" disabled>
            <div className="providerIcon"><ProviderLogo type="jira" size={34} /></div>
            <div>
              <h2>Jira</h2>
              <p>Coming later for issue creation and task tracking.</p>
            </div>
          </button>
        </div>
      </section>
    </main>
  );
}

function AnalyticsPanel({ analytics, loading }) {
  if (loading) return <div className="panelCard">Loading analytics...</div>;
  if (!analytics) return <div className="panelCard">No analytics yet. Refresh inbox first.</div>;

  const intents = analytics.intent_counts || {};
  const maxIntent = Math.max(1, ...Object.values(intents).map(Number));
  const senders = analytics.top_senders || [];
  const maxSender = Math.max(1, ...senders.map((x) => Number(x.count || 0)));

  return (
    <div className="dashboardGrid">
      <StatCard label="Analyzed Emails" value={analytics.total || 0} />
      <StatCard label="High Priority" value={analytics.high_priority || 0} />
      <StatCard label="Risky Emails" value={analytics.risky || 0} />
      <StatCard label="Safe Emails" value={analytics.safe || 0} />

      <div className="panelCard wide">
        <h3>Intent Trends</h3>
        {Object.entries(intents).length === 0 && <p>No intent data yet.</p>}
        {Object.entries(intents).map(([k, v]) => (
          <MiniBar key={k} label={k} value={v} max={maxIntent} />
        ))}
      </div>

      <div className="panelCard wide">
        <h3>Top Sender Domains</h3>
        {senders.length === 0 && <p>No sender data yet.</p>}
        {senders.map((s) => (
          <MiniBar key={s.sender} label={s.sender} value={s.count} max={maxSender} />
        ))}
      </div>

      <div className="panelCard full">
        <h3>Daily Trend</h3>
        <div className="trendGrid">
          {(analytics.daily_trend || []).map((d) => (
            <div key={d.date} className="trendItem">
              <b>{d.date}</b>
              <span>Total: {d.total}</span>
              <span>High: {d.high}</span>
              <span>Risky: {d.risky}</span>
              <span>Avg Priority: {pct(d.avg_priority)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FollowupPanel({ followups, onDone, onRefresh }) {
  return (
    <div className="panelCard full">
      <div className="panelHeader">
        <div>
          <h3>Follow-up & Reminder Dashboard</h3>
          <p>Pending and due reminders from your emails.</p>
        </div>
        <button className="softBtn" onClick={onRefresh}>Refresh reminders</button>
      </div>

      {followups.length === 0 && <div className="emptyState">No reminders yet.</div>}

      {followups.map((f) => (
        <div key={f.id} className={`followupRow ${f.status}`}>
          <div>
            <b>{f.subject || f.email_id || "Email follow-up"}</b>
            <p>{f.note || "No note"}</p>
            <small>{f.sender || f.provider || "email"} • due {fmtTime(f.remind_at)} • {f.status}</small>
          </div>

          {f.status !== "done" && (
            <button className="softBtn primary" onClick={() => onDone(f.id)}>
              Mark done
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  const [workspace, setWorkspace] = useState(null);
  const [items, setItems] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");
  const [labelFilter, setLabelFilter] = useState("ALL");
  const [maxResults, setMaxResults] = useState(10);
  const [tab, setTab] = useState("inbox");
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [followups, setFollowups] = useState([]);

  const provider = workspace?.id || "gmail";
  const activeEmail = workspace?.email || "";

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  async function loadInbox() {
    if (!workspace) return;

    setLoading(true);
    setErr("");

    try {
      const data = await fetchInbox({
        maxResults,
        userEmail: activeEmail,
        provider,
      });

      const next = Array.isArray(data) ? data : data?.items || [];

      setItems(next);
      setSelectedId((prev) => (next.some((x) => x.id === prev) ? prev : next[0]?.id || null));

      analyzeVisibleEmails(next);
    } catch (e) {
      setErr(String(e?.message || `Failed to load ${provider}`));
    } finally {
      setLoading(false);
    }
  }

  async function analyzeVisibleEmails(list) {
    // Speed-first: render inbox immediately, then analyze only a small visible batch.
    // Full AI work still runs when the user opens/clicks actions; this avoids blocking the UI.
    const autoLimit = Number(import.meta.env.VITE_AUTO_ANALYZE_LIMIT || 3);
    const batch = (list || []).slice(0, Math.min(Number(maxResults || 10), autoLimit));

    // Let the browser paint the inbox before background analysis begins.
    await new Promise((resolve) => setTimeout(resolve, 150));

    for (const email of batch) {
      if (!email?.id || email.analysis_status === "done") continue;

      try {
        setItems((prev) =>
          prev.map((x) => (x.id === email.id ? { ...x, analysis_status: "loading" } : x))
        );

        const analyzed = await analyzeEmail({
          email,
          provider,
          user_email: activeEmail,
        });

        setItems((prev) =>
          prev.map((x) =>
            x.id === email.id ? { ...x, ...analyzed, analysis_status: "done" } : x
          )
        );
      } catch {
        setItems((prev) =>
          prev.map((x) => (x.id === email.id ? { ...x, analysis_status: "error" } : x))
        );
      }
    }
  }

  async function loadAnalytics() {
    setAnalyticsLoading(true);

    try {
      setAnalytics(await fetchAnalytics(14));
    } catch (e) {
      setErr(String(e?.message || e));
    } finally {
      setAnalyticsLoading(false);
    }
  }

  async function loadFollowups() {
    try {
      await fetchDueFollowups();
      setFollowups(await fetchFollowups(""));
    } catch (e) {
      setErr(String(e?.message || e));
    }
  }

  useEffect(() => {
    if (workspace) {
      loadInbox();
      loadAnalytics();
      loadFollowups();
    }
  }, [workspace?.id, maxResults]);

  const filtered = useMemo(() => {
    let res = [...items];
    const q = query.trim().toLowerCase();

    if (q) {
      res = res.filter((it) =>
        [it.subject, it.from, it.snippet, it.body, attachmentSearchText(it)].some((x) =>
          String(x || "").toLowerCase().includes(q)
        )
      );
    }

    if (labelFilter !== "ALL") {
      if (labelFilter === "ATTACHMENTS") {
        res = res.filter((it) => Array.isArray(it.attachments) && it.attachments.length > 0);
      } else if (labelFilter === "INVOICE") {
        res = res.filter((it) => hasAttachmentDocType(it, "invoice"));
      } else if (labelFilter === "CONTRACT") {
        res = res.filter((it) => hasAttachmentDocType(it, "contract"));
      } else if (labelFilter === "OFFER_LETTER") {
        res = res.filter((it) => hasAttachmentDocType(it, "offer_letter"));
      } else if (labelFilter === "RESUME") {
        res = res.filter((it) => hasAttachmentDocType(it, "resume"));
      } else if (labelFilter === "TAX_DOCUMENT") {
        res = res.filter((it) => hasAttachmentDocType(it, "tax_document"));
      } else {
        res = res.filter((it) => it.label === labelFilter);
      }
    }

    return res;
  }, [items, query, labelFilter]);

  const selectedItem = useMemo(
    () => items.find((it) => it.id === selectedId) || null,
    [items, selectedId]
  );

  const counts = useMemo(() => {
    const high = items.filter((x) => x.label === "HIGH").length;
    const risky = items.filter((x) => Number(x.risk || 0) >= 0.5).length;
    return { total: items.length, high, risky };
  }, [items]);

  if (!workspace) {
    return (
      <LandingPage
        onChoose={setWorkspace}
        theme={theme}
        toggleTheme={toggleTheme}
      />
    );
  }

  return (
    <div className="appShell">
      <header className="appHeader">
        <button className="backBtn" onClick={() => setWorkspace(null)}>
          ← Workspaces
        </button>

        <div className="brandBlock">
          <div className={`brandIcon ${provider}`}><ProviderLogo type={workspace.logo || provider} size={30} /></div>
          <div>
            <h1>{workspace.name} AI Inbox</h1>
            <p>{activeEmail}</p>
          </div>
        </div>

        <div className="headerRight">
          <ThemeToggle theme={theme} toggleTheme={toggleTheme} />

          <div className="headerStats">
            <StatCard label="Emails" value={counts.total} />
            <StatCard label="High" value={counts.high} />
            <StatCard label="Risky" value={counts.risky} />
          </div>
        </div>
      </header>

      <nav className="tabBar">
        <button className={tab === "inbox" ? "active" : ""} onClick={() => setTab("inbox")}>
          Inbox
        </button>

        <button
          className={tab === "followups" ? "active" : ""}
          onClick={() => {
            setTab("followups");
            loadFollowups();
          }}
        >
          Follow-ups
        </button>

        <button
          className={tab === "analytics" ? "active" : ""}
          onClick={() => {
            setTab("analytics");
            loadAnalytics();
          }}
        >
          Analytics
        </button>
      </nav>

      {err && <div className="errorBanner">{err}</div>}

      {tab === "inbox" && (
        <>
          <section className="toolbar">
            <input
              className="searchInput"
              placeholder={`Search ${workspace.name} emails...`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />

            <select
              className="selectInput"
              value={labelFilter}
              onChange={(e) => setLabelFilter(e.target.value)}
            >
              <option value="ALL">All Priority</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
              <option value="ATTACHMENTS">Has Attachments</option>
              <option value="INVOICE">Invoices</option>
              <option value="CONTRACT">Contracts</option>
              <option value="OFFER_LETTER">Offer Letters</option>
              <option value="RESUME">Resumes</option>
              <option value="TAX_DOCUMENT">Tax Documents</option>
            </select>

            <select
              className="selectInput"
              value={maxResults}
              onChange={(e) => setMaxResults(Number(e.target.value))}
            >
              <option value={5}>5 Emails</option>
              <option value={10}>10 Emails</option>
              <option value={20}>20 Emails</option>
              <option value={50}>50 Emails</option>
            </select>

            <button className="primaryBtn" onClick={loadInbox} disabled={loading}>
              {loading ? "Fetching..." : "Refresh"}
            </button>
          </section>

          <main className="contentGrid">
            <section className="listPane">
              {filtered.map((it) => (
                <EmailCard
                  key={it.id}
                  item={it}
                  selected={selectedId === it.id}
                  onSelect={() => setSelectedId(it.id)}
                  onPatchItem={(patch) =>
                    setItems((prev) =>
                      prev.map((x) => (x.id === it.id ? { ...x, ...patch } : x))
                    )
                  }
                  onFollowupCreated={loadFollowups}
                />
              ))}

              {loading && <div className="emptyState">Fetching emails...</div>}

              {!loading && filtered.length === 0 && (
                <div className="emptyState">No {workspace.name} emails found.</div>
              )}
            </section>

            <DetailPanel item={selectedItem} />
          </main>
        </>
      )}

      {tab === "followups" && (
        <main className="pagePanel">
          <FollowupPanel
            followups={followups}
            onRefresh={loadFollowups}
            onDone={async (id) => {
              await updateFollowupStatus(id, "done");
              await loadFollowups();
            }}
          />
        </main>
      )}

      {tab === "analytics" && (
        <main className="pagePanel">
          <AnalyticsPanel analytics={analytics} loading={analyticsLoading} />
        </main>
      )}
    </div>
  );
}