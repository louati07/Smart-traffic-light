import React, { useState } from "react";
import { IntersectionState, Mode } from "../types";
import { Siren, ShieldAlert, CheckCircle2, Play, AlertTriangle } from "lucide-react";

interface LiveTwinProps {
  state: IntersectionState;
  onManualCommand: (cmd: "PRIORITY" | "CLEAR", axis?: "NS" | "EW") => void;
  userRole: string;
}

export const LiveTwin: React.FC<LiveTwinProps> = ({ state, onManualCommand, userRole }) => {
  const [selectedAxis, setSelectedAxis] = useState<"NS" | "EW">("NS");

  const lights = state.lights || { N: "R", E: "R", S: "R", W: "R" };
  const phase = state.phase || "NS_GREEN";
  const mode = state.mode || "NORMAL";

  const getColorHex = (c: string) => {
    if (c === "G") return "#10b981";
    if (c === "Y") return "#f59e0b";
    return "#ef4444";
  };

  const getGlowFilter = (c: string) => {
    if (c === "G") return "drop-shadow(0 0 10px #10b981)";
    if (c === "Y") return "drop-shadow(0 0 10px #f59e0b)";
    return "drop-shadow(0 0 10px #ef4444)";
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "24px", padding: "0 24px" }}>
      {/* 2D Digital Twin Canvas */}
      <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>
        
        {/* Mode Status Banner */}
        <div style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>2D Digital Twin View</h2>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Sub-second synchronized telemetry</p>
          </div>

          <div>
            {mode === "PRIORITY" && (
              <div className="siren-badge">
                <Siren size={18} />
                <span>EMERGENCY PRIORITY ACTIVE</span>
              </div>
            )}
            {mode === "FALLBACK" && (
              <div style={{ background: "rgba(239, 68, 68, 0.2)", border: "1px solid #ef4444", color: "#f87171", padding: "4px 12px", borderRadius: "9999px", display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
                <AlertTriangle size={18} />
                <span>FALLBACK MODE (HEARTBEAT LOST)</span>
              </div>
            )}
            {mode === "NORMAL" && (
              <div style={{ background: "rgba(16, 185, 129, 0.15)", border: "1px solid #10b981", color: "#34d399", padding: "4px 12px", borderRadius: "9999px", display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
                <CheckCircle2 size={18} />
                <span>NORMAL TIMER CYCLE</span>
              </div>
            )}
          </div>
        </div>

        {/* Top-Down 2D SVG Intersection */}
        <svg
          viewBox="-250 -250 500 500"
          style={{
            width: "100%",
            maxWidth: "520px",
            height: "auto",
            background: "#0d1527",
            borderRadius: "20px",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            boxShadow: "0 12px 36px rgba(0,0,0,0.6)",
          }}
        >
          {/* Grass / Ground background */}
          <rect x="-250" y="-250" width="500" height="500" fill="#0c1322" />

          {/* North-South Road */}
          <rect x="-60" y="-250" width="120" height="500" fill="#1e293b" />
          {/* East-West Road */}
          <rect x="-250" y="-60" width="500" height="120" fill="#1e293b" />

          {/* Road center dividers (dashed yellow/white) */}
          <line x1="0" y1="-250" x2="0" y2="-60" stroke="#f59e0b" strokeWidth="2" strokeDasharray="8 8" />
          <line x1="0" y1="60" x2="0" y2="250" stroke="#f59e0b" strokeWidth="2" strokeDasharray="8 8" />
          <line x1="-250" y1="0" x2="-60" y2="0" stroke="#f59e0b" strokeWidth="2" strokeDasharray="8 8" />
          <line x1="60" y1="0" x2="250" y2="0" stroke="#f59e0b" strokeWidth="2" strokeDasharray="8 8" />

          {/* Zebra Crossings */}
          {[-45, -30, -15, 0, 15, 30, 45].map((offset) => (
            <React.Fragment key={offset}>
              {/* North crossing */}
              <rect x={offset - 4} y="-75" width="8" height="12" fill="#94a3b8" opacity="0.6" />
              {/* South crossing */}
              <rect x={offset - 4} y="63" width="8" height="12" fill="#94a3b8" opacity="0.6" />
              {/* East crossing */}
              <rect x="63" y={offset - 4} width="12" height="8" fill="#94a3b8" opacity="0.6" />
              {/* West crossing */}
              <rect x="-75" y={offset - 4} width="12" height="8" fill="#94a3b8" opacity="0.6" />
            </React.Fragment>
          ))}

          {/* Central Intersection Box */}
          <rect x="-60" y="-60" width="120" height="120" fill="#182234" opacity="0.9" />

          {/* --- TRAFFIC LIGHT HEADS --- */}

          {/* North Signal Head */}
          <g transform="translate(68, -85)">
            <rect x="-10" y="-30" width="20" height="60" rx="6" fill="#0b0f19" stroke="#334155" strokeWidth="2" />
            <circle cx="0" cy="-18" r="6" fill={lights.N === "R" ? getColorHex("R") : "#331111"} style={{ filter: lights.N === "R" ? getGlowFilter("R") : "none" }} />
            <circle cx="0" cy="0" r="6" fill={lights.N === "Y" ? getColorHex("Y") : "#332a11"} style={{ filter: lights.N === "Y" ? getGlowFilter("Y") : "none" }} />
            <circle cx="0" cy="18" r="6" fill={lights.N === "G" ? getColorHex("G") : "#113322"} style={{ filter: lights.N === "G" ? getGlowFilter("G") : "none" }} />
            <text x="14" y="4" fill="#94a3b8" fontSize="10" fontFamily="sans-serif" fontWeight="700">N</text>
          </g>

          {/* South Signal Head */}
          <g transform="translate(-68, 85)">
            <rect x="-10" y="-30" width="20" height="60" rx="6" fill="#0b0f19" stroke="#334155" strokeWidth="2" />
            <circle cx="0" cy="-18" r="6" fill={lights.S === "R" ? getColorHex("R") : "#331111"} style={{ filter: lights.S === "R" ? getGlowFilter("R") : "none" }} />
            <circle cx="0" cy="0" r="6" fill={lights.S === "Y" ? getColorHex("Y") : "#332a11"} style={{ filter: lights.S === "Y" ? getGlowFilter("Y") : "none" }} />
            <circle cx="0" cy="18" r="6" fill={lights.S === "G" ? getColorHex("G") : "#113322"} style={{ filter: lights.S === "G" ? getGlowFilter("G") : "none" }} />
            <text x="-24" y="4" fill="#94a3b8" fontSize="10" fontFamily="sans-serif" fontWeight="700">S</text>
          </g>

          {/* East Signal Head */}
          <g transform="translate(85, 68)">
            <rect x="-30" y="-10" width="60" height="20" rx="6" fill="#0b0f19" stroke="#334155" strokeWidth="2" />
            <circle cx="-18" cy="0" r="6" fill={lights.E === "R" ? getColorHex("R") : "#331111"} style={{ filter: lights.E === "R" ? getGlowFilter("R") : "none" }} />
            <circle cx="0" cy="0" r="6" fill={lights.E === "Y" ? getColorHex("Y") : "#332a11"} style={{ filter: lights.E === "Y" ? getGlowFilter("Y") : "none" }} />
            <circle cx="18" cy="0" r="6" fill={lights.E === "G" ? getColorHex("G") : "#113322"} style={{ filter: lights.E === "G" ? getGlowFilter("G") : "none" }} />
            <text x="-4" y="22" fill="#94a3b8" fontSize="10" fontFamily="sans-serif" fontWeight="700">E</text>
          </g>

          {/* West Signal Head */}
          <g transform="translate(-85, -68)">
            <rect x="-30" y="-10" width="60" height="20" rx="6" fill="#0b0f19" stroke="#334155" strokeWidth="2" />
            <circle cx="-18" cy="0" r="6" fill={lights.W === "R" ? getColorHex("R") : "#331111"} style={{ filter: lights.W === "R" ? getGlowFilter("R") : "none" }} />
            <circle cx="0" cy="0" r="6" fill={lights.W === "Y" ? getColorHex("Y") : "#332a11"} style={{ filter: lights.W === "Y" ? getGlowFilter("Y") : "none" }} />
            <circle cx="18" cy="0" r="6" fill={lights.W === "G" ? getColorHex("G") : "#113322"} style={{ filter: lights.W === "G" ? getGlowFilter("G") : "none" }} />
            <text x="-4" y="-14" fill="#94a3b8" fontSize="10" fontFamily="sans-serif" fontWeight="700">W</text>
          </g>

          {/* Emergency Vehicle (Ambulance) if Priority Active */}
          {mode === "PRIORITY" && (
            <g transform="translate(-32, -180)">
              <rect x="-14" y="-24" width="28" height="48" rx="6" fill="#ffffff" stroke="#ef4444" strokeWidth="2" />
              {/* Red cross on roof */}
              <rect x="-8" y="-3" width="16" height="6" fill="#ef4444" />
              <rect x="-3" y="-8" width="6" height="16" fill="#ef4444" />
              {/* Flashing strobe bar */}
              <circle cx="-7" cy="-16" r="4" fill="#3b82f6" className="pulse-glow" />
              <circle cx="7" cy="-16" r="4" fill="#ef4444" className="pulse-glow" />
              <text x="-20" y="38" fill="#38bdf8" fontSize="9" fontWeight="700">AMBULANCE</text>
            </g>
          )}

          {/* Simulated Ordinary Traffic Cars */}
          <g transform="translate(28, 140)">
            <rect x="-10" y="-18" width="20" height="36" rx="4" fill="#38bdf8" opacity="0.8" />
          </g>
          <g transform="translate(-160, 26)">
            <rect x="-18" y="-10" width="36" height="20" rx="4" fill="#a855f7" opacity="0.8" />
          </g>
        </svg>

        {/* Current Phase Bar */}
        <div style={{ marginTop: "16px", display: "flex", alignItems: "center", gap: "12px", width: "100%", justifyContent: "center" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Current Phase:</span>
          <span className="font-mono" style={{ background: "rgba(56, 189, 248, 0.15)", color: "#38bdf8", padding: "4px 12px", borderRadius: "8px", fontWeight: 600 }}>
            {phase}
          </span>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Elapsed:</span>
          <span className="font-mono" style={{ color: "#ffffff", fontWeight: 600 }}>
            {(state.phase_elapsed_ms / 1000).toFixed(1)}s
          </span>
        </div>
      </div>

      {/* Sidebar: Telemetry & Manual Override */}
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        
        {/* Telemetry Card */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "14px", display: "flex", alignItems: "center", gap: "8px" }}>
            <CheckCircle2 size={18} color="#10b981" />
            <span>FSM Status (i1)</span>
          </h3>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "0.85rem" }}>
            <div className="glass-card" style={{ padding: "10px" }}>
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Mode</div>
              <div style={{ fontWeight: 700, color: mode === "PRIORITY" ? "#38bdf8" : mode === "FALLBACK" ? "#ef4444" : "#10b981" }}>
                {mode}
              </div>
            </div>

            <div className="glass-card" style={{ padding: "10px" }}>
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Last Seq</div>
              <div className="font-mono" style={{ fontWeight: 700, color: "#ffffff" }}>
                #{state.last_seq}
              </div>
            </div>

            <div className="glass-card" style={{ padding: "10px" }}>
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Rejected Cmds</div>
              <div className="font-mono" style={{ fontWeight: 700, color: state.rejected_cmds ? "#ef4444" : "#10b981" }}>
                {state.rejected_cmds || 0}
              </div>
            </div>

            <div className="glass-card" style={{ padding: "10px" }}>
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Uptime</div>
              <div className="font-mono" style={{ fontWeight: 700, color: "#ffffff" }}>
                {(state.uptime_ms / 1000).toFixed(0)}s
              </div>
            </div>
          </div>
        </div>

        {/* Manual Override Controls */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
            <ShieldAlert size={18} color="#f59e0b" />
            <span>Manual Override (Operator)</span>
          </h3>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "16px" }}>
            Trigger priority directly or safely clear active hold via frozen REST contracts.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                className={`btn ${selectedAxis === "NS" ? "btn-primary" : "btn-secondary"}`}
                style={{ flex: 1, justifyContent: "center" }}
                onClick={() => setSelectedAxis("NS")}
              >
                Axis NS (N/S)
              </button>
              <button
                className={`btn ${selectedAxis === "EW" ? "btn-primary" : "btn-secondary"}`}
                style={{ flex: 1, justifyContent: "center" }}
                onClick={() => setSelectedAxis("EW")}
              >
                Axis EW (E/W)
              </button>
            </div>

            <button
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              onClick={() => onManualCommand("PRIORITY", selectedAxis)}
            >
              <Siren size={16} />
              <span>Grant Priority ({selectedAxis})</span>
            </button>

            <button
              className="btn btn-secondary"
              style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              onClick={() => onManualCommand("CLEAR")}
            >
              <CheckCircle2 size={16} />
              <span>Clear Priority Hold</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
