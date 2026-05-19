import React from "react";

const styles = {
  sidebarInner: {
    display: "flex",
    flexDirection: "column",
    gap: "20px",
    userSelect: "none",
  },
  sidebarLabel: {
    fontSize: "10px",
    fontWeight: 800,
    color: "var(--muted)",
    letterSpacing: "1px",
    marginBottom: "12px",
    paddingLeft: "10px",
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px",
    borderRadius: "12px",
    cursor: "pointer",
    transition: "all 0.2s ease",
    border: "1px solid transparent",
    color: "var(--text)",
    marginBottom: "4px",
  },
  navInfo: {
    display: "flex",
    flexDirection: "column",
  },
  navTitle: {
    fontSize: "14px",
    fontWeight: 600,
  },
  navSub: {
    fontSize: "11px",
    opacity: 0.7,
  },
  divider: {
    border: 0,
    borderTop: "1px solid var(--border)",
    margin: "10px 0",
  },
  icon: {
    fontSize: "18px",
  },
};

function getNavItemStyle(active) {
  return {
    ...styles.navItem,
    background: active ? "var(--primary)" : "transparent",
    color: active ? "#fff" : "var(--text)",
    boxShadow: active ? "0 4px 15px rgba(139, 92, 246, 0.4)" : "none",
  };
}

export const Sidebar = ({ activeProvider, onProviderChange }) => {
  return (
    <div style={styles.sidebarInner}>
      <div className="sidebar-section">
        <h3 style={styles.sidebarLabel}>ACCOUNTS</h3>

        <div
          style={getNavItemStyle(activeProvider === "gmail")}
          onClick={() => onProviderChange("gmail", "sandeep@gmail.com")}
        >
          <span style={styles.icon}>📧</span>
          <div style={styles.navInfo}>
            <span style={styles.navTitle}>Gmail</span>
            <span style={styles.navSub}>sandeep@gmail.com</span>
          </div>
        </div>

        <div
          style={getNavItemStyle(activeProvider === "outlook")}
          onClick={() => onProviderChange("outlook", "katipagalasandeep@outlook.com")}
        >
          <span style={styles.icon}>Ⓜ️</span>
          <div style={styles.navInfo}>
            <span style={styles.navTitle}>Outlook</span>
            <span style={styles.navSub}>katipagalasandeep@outlook.com</span>
          </div>
        </div>
      </div>

      <hr style={styles.divider} />

      <div className="sidebar-section">
        <h3 style={styles.sidebarLabel}>FOLDERS</h3>
        <div style={styles.navItem}>📥 Inbox</div>
        <div style={styles.navItem}>📤 Sent</div>
        <div style={styles.navItem}>🚩 Flagged</div>
        <div style={styles.navItem}>🗑️ Trash</div>
      </div>
    </div>
  );
};

export default Sidebar;