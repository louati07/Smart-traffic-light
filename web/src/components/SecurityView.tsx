import React, { useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck, AlertOctagon } from "lucide-react";
import { SecurityEvent } from "../types";

interface SecurityViewProps {
  apiBase: string;
}

export const SecurityView: React.FC<SecurityViewProps> = ({ apiBase }) => {
  const [secEvents, setSecEvents] = useState<SecurityEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Attempt fetch with admin auth
    fetch(`${apiBase}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "admin", password: "admin123" }),
    })
      .then((r) => r.json())
      .then((tok) => {
        return fetch(`${apiBase}/security-events?limit=50`, {
          headers: { Authorization: `Bearer ${tok.access_token}` },
        });
      })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSecEvents(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [apiBase]);

  return (
    <div style={{ padding: "0 24px" }}>
      <div className="glass-panel" style={{ padding: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>Security Audit & Intrusion Monitor</h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Audit log of rejected and rate-limited requests. HMAC command verification is supported by the software mock when enabled; the ESP32 firmware does not currently verify HMAC signatures.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(16, 185, 129, 0.15)", color: "#10b981", padding: "6px 12px", borderRadius: "8px", fontSize: "0.8rem", fontWeight: 600 }}>
            <ShieldCheck size={16} />
            <span>JWT access checks + detection rate limit</span>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>Loading security events...</div>
        ) : secEvents.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>No security violations recorded. System secure.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)", textAlign: "left" }}>
                  <th style={{ padding: "12px 16px" }}>Timestamp</th>
                  <th style={{ padding: "12px 16px" }}>Source IP</th>
                  <th style={{ padding: "12px 16px" }}>Violation Reason</th>
                  <th style={{ padding: "12px 16px" }}>Endpoint</th>
                  <th style={{ padding: "12px 16px" }}>Audit Details</th>
                </tr>
              </thead>
              <tbody>
                {secEvents.map((item, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <td className="font-mono" style={{ padding: "12px 16px", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {new Date(item.ts).toLocaleTimeString()}
                    </td>
                    <td className="font-mono" style={{ padding: "12px 16px", color: "var(--accent-blue)" }}>
                      {item.source_ip}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          padding: "4px 8px",
                          borderRadius: "6px",
                          background: item.reason.includes("rate_limit") ? "rgba(245, 158, 11, 0.15)" : "rgba(239, 68, 68, 0.15)",
                          color: item.reason.includes("rate_limit") ? "#f59e0b" : "#ef4444",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                        }}
                      >
                        <AlertOctagon size={12} />
                        {item.reason}
                      </span>
                    </td>
                    <td className="font-mono" style={{ padding: "12px 16px", color: "var(--text-secondary)" }}>
                      {item.endpoint}
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      {item.details}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
