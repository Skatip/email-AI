function pct(x) {
  const n = Number(x || 0);
  return `${Math.round(n * 100)}%`;
}

function chipTone(label) {
  const v = String(label || "").toUpperCase();
  if (v === "HIGH") return "danger";
  if (v === "MEDIUM") return "warn";
  return "ok";
}

function riskTone(x) {
  const n = Number(x || 0);
  if (n >= 0.6) return "danger";
  if (n >= 0.25) return "warn";
  return "ok";
}

export default function DetailPanel({ item }) {
  if (!item) {
    return (
      <aside className="detailPane">
        <div className="detailEmpty">
          <div className="detailEmptyTitle">Select an email</div>
          <div className="detailEmptySub">
            The right panel explains priority, risk, trust, suggested reply, and next action.
          </div>
        </div>
      </aside>
    );
  }

  const reply = item?.suggested_reply ?? item?.reply?.text ?? item?.reply?.reply ?? item?.reply ?? "";
  const riskReasons = item?.risk_reasons || item?.human_signals?.risk_reasons || [];
  const riskSignals = item?.risk_signals || item?.human_signals?.risk_signals || [];
  const riskUrls = item?.risk_urls || item?.human_signals?.risk_urls || [];

  return (
    <aside className="detailPane">
      <div className="paneHeader sticky">
        <div>
          <div className="paneTitle">AI Analysis</div>
          <div className="paneSub">Structured explanation for this email</div>
        </div>
      </div>

      <div className="detailBody">
        <div className="detailCard">
          <div className="detailSubject">{item?.subject || "(no subject)"}</div>
          <div className="detailFrom">{item?.from || "(no sender)"}</div>
        </div>

        <div className="metricGrid">
          <div className={`metricCard ${chipTone(item?.label)}`}><span>Priority</span><b>{pct(item?.priority)}</b></div>
          <div className={`metricCard ${riskTone(item?.risk)}`}><span>Risk</span><b>{pct(item?.risk)}</b></div>
          <div className="metricCard"><span>Trust Band</span><b>{item?.sender_band || "UNKNOWN"}</b></div>
          <div className="metricCard"><span>Intent</span><b>{item?.intent || "Unknown"}</b></div>
        </div>

        <div className="detailCard">
          <div className="detailLabel">What this email means</div>
          <p className="detailText">{item?.reason || "No explanation available yet."}</p>
        </div>

        <div className="detailCard">
          <div className="detailLabel">Risk Detection</div>
          <div className="chipList">
            {riskSignals.length ? riskSignals.map((x) => <span key={x} className="miniChip">{x}</span>) : <span className="miniChip ok">safe</span>}
          </div>
          <ul className="detailList">
            {riskReasons.length ? riskReasons.map((x, i) => <li key={i}>{x}</li>) : <li>No major phishing or fraud signals detected.</li>}
          </ul>
          {riskUrls.length > 0 && (
            <div className="urlBox">
              {riskUrls.map((u, i) => <div key={i}><b>{u.host}</b> — {u.finding}</div>)}
            </div>
          )}
        </div>

        <div className="detailCard">
          <div className="detailLabel">Recommended action</div>
          <p className="detailText">{item?.respond_recommended ? "Reply is recommended." : "A reply may not be necessary."}</p>
        </div>

        <div className="detailCard">
          <div className="detailLabel">Email preview</div>
          <p className="detailText">{item?.snippet || "No preview available."}</p>
        </div>

        <div className="detailCard">
          <div className="detailLabel">Suggested reply</div>
          <div className="replyPreview">{reply ? reply : "Generate reply to see a suggested draft here."}</div>
        </div>
      </div>
    </aside>
  );
}
