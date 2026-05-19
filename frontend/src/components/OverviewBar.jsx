function StatCard({ label, value, tone }) {
  return (
    <div className={`statCard ${tone || ""}`}>
      <div className="statValue">{value}</div>
      <div className="statLabel">{label}</div>
    </div>
  );
}

export default function OverviewBar({ items = [] }) {
  const safeItems = Array.isArray(items) ? items : [];

  const stats = {
    total: safeItems.length,
    high: safeItems.filter((x) => String(x?.label || "").toUpperCase() === "HIGH").length,
    action: safeItems.filter((x) => x?.respond_recommended === true).length,
    urgent: safeItems.filter((x) => Number(x?.urgency_minutes || 999999) <= 60).length,
    risky: safeItems.filter((x) => Number(x?.risk || 0) >= 0.5).length,
    low: safeItems.filter((x) => String(x?.label || "").toUpperCase() === "LOW").length,
  };

  return (
    <section className="overviewGrid">
      <StatCard label="Total" value={stats.total} />
      <StatCard label="High Priority" value={stats.high} tone="danger" />
      <StatCard label="Action Needed" value={stats.action} tone="warn" />
      <StatCard label="Urgent" value={stats.urgent} tone="danger" />
      <StatCard label="Risky" value={stats.risky} tone="danger" />
      <StatCard label="Low Priority" value={stats.low} tone="ok" />
    </section>
  );
}