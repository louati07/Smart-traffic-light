import React, { useEffect, useState } from "react";
import { Siren, Clock, Flame, Shield, CheckCircle2 } from "lucide-react";
import { PriorityEvent } from "../types";

interface EventsViewProps {
  apiBase: string;
}

export const EventsView: React.FC<EventsViewProps> = ({ apiBase }) => {
  const [events, setEvents] = useState<PriorityEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${apiBase}/events?limit=50`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setEvents(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [apiBase]);

  const getClassIcon = (cls: string) => {
    if (cls === "fire_truck") return <Flame size={16} color="#f97316" />;
    if (cls === "police_car") return <Shield size={16} color="#3b82f6" />;
    return <Siren size={16} color="#ef4444" />;
  };

  return (
    <div style={{ padding: "0 24px" }}>
      <div className="glass-panel" style={{ padding: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>Emergency Priority Event History</h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Historical archive of all vehicle preemption activations from MongoDB
            </p>
          </div>
          <div className="font-mono" style={{ fontSize: "0.85rem", color: "var(--accent-blue)" }}>
            Total Events: {events.length}
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>Loading events...</div>
        ) : events.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>No priority events recorded yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-muted)", textAlign: "left" }}>
                  <th style={{ padding: "12px 16px" }}>Event ID</th>
                  <th style={{ padding: "12px 16px" }}>Class</th>
                  <th style={{ padding: "12px 16px" }}>Approach / Axis</th>
                  <th style={{ padding: "12px 16px" }}>Started At</th>
                  <th style={{ padding: "12px 16px" }}>Latency</th>
                  <th style={{ padding: "12px 16px" }}>Outcome</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev, i) => (
                  <tr key={ev.event_id || i} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <td className="font-mono" style={{ padding: "12px 16px", color: "var(--text-secondary)" }}>
                      {ev.event_id?.slice(0, 12)}...
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        {getClassIcon(ev.class)}
                        <span style={{ textTransform: "capitalize", fontWeight: 500 }}>
                          {ev.class?.replace("_", " ")}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span className="font-mono" style={{ background: "rgba(255,255,255,0.05)", padding: "2px 8px", borderRadius: "4px" }}>
                        Approach {ev.approach} ({ev.axis})
                      </span>
                    </td>
                    <td className="font-mono" style={{ padding: "12px 16px", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {new Date(ev.started_at).toLocaleTimeString()}
                    </td>
                    <td className="font-mono" style={{ padding: "12px 16px", color: "#38bdf8" }}>
                      {ev.light_change_latency_ms ? `${ev.light_change_latency_ms} ms` : "< 2.0 s"}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          padding: "4px 8px",
                          borderRadius: "6px",
                          background: ev.outcome === "completed" || ev.outcome === "auto_released" ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.15)",
                          color: ev.outcome === "completed" || ev.outcome === "auto_released" ? "#34d399" : "#38bdf8",
                        }}
                      >
                        {ev.outcome || "completed"}
                      </span>
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
