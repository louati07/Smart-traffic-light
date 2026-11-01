import React, { useState, useEffect, useRef } from "react";
import { Navbar } from "./components/Navbar";
import { LiveTwin } from "./components/LiveTwin";
import { ArchitectureView } from "./components/ArchitectureView";
import { CompareBattle } from "./components/CompareBattle";
import { EventsView } from "./components/EventsView";
import { SecurityView } from "./components/SecurityView";
import { StatusView } from "./components/StatusView";
import { IntersectionState } from "./types";

const API_BASE = "http://localhost:8000/api/v1";
const WS_BASE = "ws://localhost:8000/api/v1/ws/state";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState("twin");
  const [isConnected, setIsConnected] = useState(false);
  const [stateFresh, setStateFresh] = useState(false);
  const [heartbeat, setHeartbeat] = useState(1);
  const [userRole, setUserRole] = useState("operator");

  const [state, setState] = useState<IntersectionState>({
    phase: "NS_GREEN",
    mode: "NORMAL",
    lights: { N: "G", E: "R", S: "G", W: "R" },
    last_seq: 0,
    phase_elapsed_ms: 0,
    uptime_ms: 0,
    rejected_cmds: 0,
    priority_approach: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const lastFreshStateAtRef = useRef(0);

  // Authenticate default operator role on mount
  useEffect(() => {
    fetch(`${API_BASE}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "operator", password: "operator123" }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.access_token) {
          localStorage.setItem("token", data.access_token);
        }
      })
      .catch(() => {});
  }, []);

  // WebSocket live feed with auto-reconnect and polling fallback
  useEffect(() => {
    let active = true;

    const connectWs = () => {
      try {
        const token = localStorage.getItem("token") || "";
        const ws = new WebSocket(`${WS_BASE}?token=${token}`);
        wsRef.current = ws;

        ws.onopen = () => {
          if (active) setIsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.state) setState(data.state);
            const fresh = Boolean(data.state_fresh);
            setStateFresh(fresh);
            if (fresh) lastFreshStateAtRef.current = Date.now();
            if (data.heartbeat) setHeartbeat(data.heartbeat);
          } catch (e) {
            console.error("Failed to parse WS state message:", e);
          }
        };

        ws.onclose = () => {
          if (active) {
            setIsConnected(false);
            setTimeout(connectWs, 2000);
          }
        };

        ws.onerror = () => {
          if (active) setIsConnected(false);
        };
      } catch (e) {
        setIsConnected(false);
      }
    };

    connectWs();

    // Recover from a WebSocket that stays open but stops delivering fresh state.
    const pollInterval = setInterval(() => {
      const wsFresh = wsRef.current?.readyState === WebSocket.OPEN &&
        Date.now() - lastFreshStateAtRef.current <= 1500;
      if (!wsFresh) {
        const token = localStorage.getItem("token") || "";
        fetch(`${API_BASE}/intersections/i1/state`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
          .then((r) => r.json())
          .then((data) => {
            if (data && data.phase) {
              setState(data);
              setStateFresh(Boolean(data.state_fresh));
              if (data.state_fresh) lastFreshStateAtRef.current = Date.now();
              setIsConnected(Boolean(wsRef.current?.readyState === WebSocket.OPEN) || Boolean(data.state_fresh));
            }
          })
          .catch(() => setIsConnected(false));
      }
    }, 1000);

    return () => {
      active = false;
      clearInterval(pollInterval);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Manual override handler
  const handleManualCommand = (cmd: "PRIORITY" | "CLEAR", axis?: "NS" | "EW", approach?: "N" | "E" | "S" | "W") => {
    const token = localStorage.getItem("token") || "";
    fetch(`${API_BASE}/intersections/i1/command`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        cmd,
        axis: cmd === "PRIORITY" ? axis || "NS" : undefined,
        approach: cmd === "PRIORITY" ? approach || (axis === "EW" ? "E" : "N") : undefined,
        ttl_s: 15,
      }),
    })
      .then((r) => r.json())
      .catch((err) => console.error("Manual command error:", err));
  };

  const handleRoleSwitch = (role: string) => {
    setUserRole(role);
    fetch(`${API_BASE}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: role, password: `${role}123` }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.access_token) {
          localStorage.setItem("token", data.access_token);
        }
      })
      .catch(() => {});
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isConnected={isConnected}
        heartbeat={heartbeat}
        userRole={userRole}
        onLogin={handleRoleSwitch}
      />

      <main style={{ flex: 1, paddingBottom: "32px" }}>
        {(!isConnected || !stateFresh) && (
          <div role="status" style={{ margin: "12px 24px", padding: "10px 14px", borderRadius: 8, background: "rgba(245, 158, 11, 0.14)", color: "#fbbf24", border: "1px solid rgba(245, 158, 11, 0.35)", fontSize: "0.85rem" }}>
            {!isConnected ? "Live connection lost. Signal display may be out of date." : "Controller state has not refreshed recently. Check the Wokwi to Firebase connection before relying on this display."}
          </div>
        )}
        {activeTab === "twin" && (
          <LiveTwin state={state} onManualCommand={handleManualCommand} userRole={userRole} />
        )}
        {activeTab === "architecture" && (
          <ArchitectureView apiBase={API_BASE} isConnected={isConnected} heartbeat={heartbeat} />
        )}
        {activeTab === "compare" && <CompareBattle apiBase={API_BASE} />}
        {activeTab === "events" && <EventsView apiBase={API_BASE} />}
        {activeTab === "security" && <SecurityView apiBase={API_BASE} />}
        {activeTab === "status" && <StatusView apiBase={API_BASE} heartbeat={heartbeat} />}
      </main>
    </div>
  );
};
