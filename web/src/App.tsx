import React, { useState, useEffect, useRef } from "react";
import { Navbar } from "./components/Navbar";
import { LiveTwin } from "./components/LiveTwin";
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
  });

  const wsRef = useRef<WebSocket | null>(null);

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

    // Polling fallback every 1s
    const pollInterval = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        const token = localStorage.getItem("token") || "";
        fetch(`${API_BASE}/intersections/i1/state`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
          .then((r) => r.json())
          .then((data) => {
            if (data && data.phase) {
              setState(data);
              setIsConnected(true);
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
  const handleManualCommand = (cmd: "PRIORITY" | "CLEAR", axis?: "NS" | "EW") => {
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
        {activeTab === "twin" && (
          <LiveTwin state={state} onManualCommand={handleManualCommand} userRole={userRole} />
        )}
        {activeTab === "compare" && <CompareBattle apiBase={API_BASE} />}
        {activeTab === "events" && <EventsView apiBase={API_BASE} />}
        {activeTab === "security" && <SecurityView apiBase={API_BASE} />}
        {activeTab === "status" && <StatusView apiBase={API_BASE} heartbeat={heartbeat} />}
      </main>
    </div>
  );
};
