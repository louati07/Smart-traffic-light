import React, { useState } from "react";
import { Activity, Shield, BarChart3, Radio, Server, Siren, UserCheck, Brain } from "lucide-react";

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isConnected: boolean;
  heartbeat: number;
  userRole: string;
  onLogin: (role: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  isConnected,
  heartbeat,
  userRole,
  onLogin,
}) => {
  const [showLoginModal, setShowLoginModal] = useState(false);

  const tabs = [
    { id: "twin", label: "2D Digital Twin", icon: Radio },
    { id: "architecture", label: "Architecture", icon: Brain },
    { id: "compare", label: "A/B Battle Compare", icon: BarChart3 },
    { id: "events", label: "Priority Events", icon: Siren },
    { id: "security", label: "Security Audit", icon: Shield },
    { id: "status", label: "System Health", icon: Server },
  ];

  return (
    <header className="glass-panel" style={{ margin: "16px 24px", padding: "12px 24px", borderRadius: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
        {/* Brand */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              width: "42px",
              height: "42px",
              borderRadius: "12px",
              background: "linear-gradient(135deg, #38bdf8, #6366f1)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 0 20px rgba(56, 189, 248, 0.4)",
            }}
          >
            <Activity color="#ffffff" size={24} />
          </div>
          <div>
            <h1 style={{ fontSize: "1.15rem", fontWeight: 700, letterSpacing: "-0.02em" }}>
              CIVILEA <span style={{ color: "#38bdf8" }}>Intersection Twin</span>
            </h1>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              AI Emergency-Vehicle Priority Orchestrator (i1)
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav style={{ display: "flex", gap: "6px", background: "rgba(0,0,0,0.3)", padding: "4px", borderRadius: "12px" }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="btn"
                style={{
                  background: isActive ? "linear-gradient(135deg, rgba(99,102,241,0.8), rgba(56,189,248,0.8))" : "transparent",
                  color: isActive ? "#ffffff" : "var(--text-secondary)",
                  boxShadow: isActive ? "0 4px 12px rgba(56,189,248,0.3)" : "none",
                  border: "none",
                  padding: "8px 14px",
                  borderRadius: "8px",
                }}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Live Status Indicators */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            <span
              style={{
                width: "10px",
                height: "10px",
                borderRadius: "50%",
                background: isConnected ? "var(--accent-green)" : "var(--accent-red)",
                boxShadow: isConnected ? "var(--glow-green)" : "var(--glow-red)",
                display: "inline-block",
              }}
            />
            <span>{isConnected ? "WS Live" : "Reconnecting"}</span>
          </div>

          <div
            className="font-mono"
            style={{
              fontSize: "0.75rem",
              background: "rgba(255,255,255,0.05)",
              padding: "4px 8px",
              borderRadius: "6px",
              border: "1px solid var(--border-subtle)",
              color: "#38bdf8",
            }}
          >
            HB: #{heartbeat}
          </div>

          <button
            onClick={() => setShowLoginModal(true)}
            className="btn btn-secondary"
            style={{ fontSize: "0.8rem", padding: "6px 12px" }}
          >
            <UserCheck size={14} />
            <span style={{ textTransform: "capitalize" }}>{userRole}</span>
          </button>
        </div>
      </div>

      {/* Role Switcher Modal */}
      {showLoginModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
          onClick={() => setShowLoginModal(false)}
        >
          <div
            className="glass-panel"
            style={{ padding: "24px", maxWidth: "340px", width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginBottom: "12px", fontSize: "1.1rem" }}>Switch User Role</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "16px" }}>
              Select simulated authentication role to test RBAC permissions:
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {["operator", "admin", "camera"].map((role) => (
                <button
                  key={role}
                  className={`btn ${userRole === role ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => {
                    onLogin(role);
                    setShowLoginModal(false);
                  }}
                  style={{ justifyContent: "center", textTransform: "capitalize" }}
                >
                  {role} ({role === "admin" ? "All Endpoints" : role === "operator" ? "Twin + Override" : "Vision Ingest"})
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
