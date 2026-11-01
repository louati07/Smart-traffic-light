import React, { useState, useEffect } from "react";
import {
  Cpu,
  Database,
  Server,
  Monitor,
  Wifi,
  Shield,
  Zap,
  Eye,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Radio,
  Cloud,
  Brain,
  Lock,
  Activity,
  Video,
} from "lucide-react";

interface ArchitectureViewProps {
  apiBase: string;
  isConnected: boolean;
  heartbeat: number;
}

interface HealthData {
  firebase_ok: boolean;
  mongo_ok: boolean;
  esp32_ok: boolean;
  uptime_s: number;
  mode: string;
}

interface NodeProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  color: string;
  glowColor: string;
  details: string[];
  tech: string[];
  status?: "online" | "offline" | "warning";
  pulseActive?: boolean;
}

const ArchNode: React.FC<NodeProps> = ({
  title,
  subtitle,
  icon,
  color,
  glowColor,
  details,
  tech,
  status = "online",
  pulseActive = false,
}) => (
  <div
    className="glass-panel"
    style={{
      padding: "20px",
      borderRadius: "16px",
      border: `1px solid ${color}33`,
      position: "relative",
      overflow: "hidden",
      transition: "all 0.3s ease",
    }}
  >
    {/* Subtle gradient overlay */}
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `linear-gradient(135deg, ${color}08 0%, transparent 60%)`,
        pointerEvents: "none",
      }}
    />

    {/* Status Indicator */}
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", position: "relative" }}>
      <div
        style={{
          width: "46px",
          height: "46px",
          borderRadius: "12px",
          background: `linear-gradient(135deg, ${color}30, ${color}10)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          border: `1px solid ${color}40`,
          boxShadow: pulseActive ? `0 0 20px ${glowColor}` : "none",
          transition: "box-shadow 0.5s",
        }}
      >
        {icon}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: status === "online" ? "#10b981" : status === "warning" ? "#f59e0b" : "#ef4444",
            boxShadow: status === "online" ? "0 0 8px #10b981" : status === "warning" ? "0 0 8px #f59e0b" : "0 0 8px #ef4444",
            animation: pulseActive ? "pulse 1.5s ease-in-out infinite" : "none",
          }}
        />
        <span style={{ fontSize: "0.7rem", color: status === "online" ? "#10b981" : status === "warning" ? "#f59e0b" : "#ef4444", fontWeight: 600, textTransform: "uppercase", letterSpacing: "1px" }}>
          {status}
        </span>
      </div>
    </div>

    <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "2px", position: "relative" }}>{title}</h3>
    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "12px", position: "relative" }}>{subtitle}</p>

    {/* Details */}
    <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginBottom: "12px", position: "relative" }}>
      {details.map((d, i) => (
        <div key={i} style={{ fontSize: "0.78rem", color: "var(--text-secondary)", display: "flex", alignItems: "flex-start", gap: "6px" }}>
          <CheckCircle2 size={12} color={color} style={{ marginTop: "2px", flexShrink: 0 }} />
          <span>{d}</span>
        </div>
      ))}
    </div>

    {/* Tech Badges */}
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", position: "relative" }}>
      {tech.map((t, i) => (
        <span
          key={i}
          style={{
            fontSize: "0.68rem",
            padding: "2px 8px",
            borderRadius: "6px",
            background: `${color}15`,
            color,
            border: `1px solid ${color}30`,
            fontWeight: 600,
          }}
        >
          {t}
        </span>
      ))}
    </div>
  </div>
);

/* ── Data Flow Arrow ── */
const FlowArrow: React.FC<{ label: string; protocol: string; color: string; active?: boolean; direction?: "right" | "down" | "bidirectional" }> = ({
  label,
  protocol,
  color,
  active = true,
  direction = "right",
}) => (
  <div
    style={{
      display: "flex",
      flexDirection: direction === "down" ? "column" : "row",
      alignItems: "center",
      justifyContent: "center",
      gap: "4px",
      padding: direction === "down" ? "8px 0" : "0 6px",
      minWidth: direction === "right" ? "100px" : undefined,
    }}
  >
    <div
      style={{
        height: direction === "down" ? "40px" : "2px",
        width: direction === "down" ? "2px" : "100%",
        background: active
          ? `linear-gradient(${direction === "down" ? "to bottom" : "to right"}, ${color}80, ${color})`
          : `${color}30`,
        position: "relative",
        borderRadius: "1px",
      }}
    >
      {/* Animated pulse dot */}
      {active && (
        <div
          style={{
            position: "absolute",
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: color,
            boxShadow: `0 0 12px ${color}`,
            animation: direction === "down" ? "flowDown 2s ease-in-out infinite" : "flowRight 2s ease-in-out infinite",
            top: direction === "down" ? "0" : "-3px",
            left: direction === "down" ? "-3px" : "0",
          }}
        />
      )}
    </div>
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "0.65rem", color, fontWeight: 700, whiteSpace: "nowrap" }}>{label}</div>
      <div style={{ fontSize: "0.6rem", color: "var(--text-muted)", fontWeight: 500 }}>{protocol}</div>
    </div>
  </div>
);

export const ArchitectureView: React.FC<ArchitectureViewProps> = ({ apiBase, isConnected, heartbeat }) => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [tick, setTick] = useState(0);

  // Fetch health status
  useEffect(() => {
    const fetchHealth = () => {
      const token = localStorage.getItem("token") || "";
      fetch(`${apiBase}/health`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => r.json())
        .then((data) => setHealth(data))
        .catch(() => {});
    };
    fetchHealth();
    const iv = setInterval(fetchHealth, 5000);
    return () => clearInterval(iv);
  }, [apiBase]);

  // Tick for animations
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(iv);
  }, []);

  const firebaseOk = Boolean(health?.firebase_ok ?? (health as any)?.firebase ?? false);
  const mongoOk = Boolean(health?.mongo_ok ?? (health as any)?.mongo ?? false);
  const esp32Ok = Boolean(health?.esp32_ok ?? (heartbeat > 0));

  return (
    <div style={{ padding: "0 24px" }}>
      {/* Inline keyframes for animations */}
      <style>{`
        @keyframes flowRight {
          0% { left: 0; opacity: 0; }
          20% { opacity: 1; }
          80% { opacity: 1; }
          100% { left: calc(100% - 8px); opacity: 0; }
        }
        @keyframes flowDown {
          0% { top: 0; opacity: 0; }
          20% { opacity: 1; }
          80% { opacity: 1; }
          100% { top: calc(100% - 8px); opacity: 0; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.5); }
        }
        @keyframes dataStreamH {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>

      {/* Page Header */}
      <div className="glass-panel" style={{ padding: "24px", marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700, display: "flex", alignItems: "center", gap: "10px" }}>
              <Brain size={24} color="#a855f7" />
              System Architecture & Live Data Flow
            </h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Roadside video → AI detection → priority command → ESP32 signal control → live dashboard
            </p>
          </div>

          {/* Live Connection Summary */}
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            {[
              { label: "WebSocket", ok: isConnected, icon: <Wifi size={14} /> },
              { label: "Firebase", ok: firebaseOk, icon: <Cloud size={14} /> },
              { label: "MongoDB", ok: mongoOk, icon: <Database size={14} /> },
              { label: "ESP32", ok: esp32Ok, icon: <Cpu size={14} /> },
            ].map((s) => (
              <div
                key={s.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "8px",
                  background: s.ok ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                  border: `1px solid ${s.ok ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`,
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  color: s.ok ? "#10b981" : "#ef4444",
                }}
              >
                {s.icon}
                {s.label}
                <span
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: s.ok ? "#10b981" : "#ef4444",
                    boxShadow: s.ok ? "0 0 6px #10b981" : "0 0 6px #ef4444",
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Planned real-world camera-to-controller path */}
      <section
        className="glass-panel"
        aria-label="Roadside camera deployment path"
        style={{
          padding: "22px",
          marginBottom: "24px",
          border: "1px solid rgba(56, 189, 248, 0.38)",
          background: "linear-gradient(120deg, rgba(8, 47, 73, 0.42), rgba(30, 27, 75, 0.32))",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", flexWrap: "wrap", marginBottom: "16px" }}>
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 750, display: "flex", alignItems: "center", gap: "9px" }}>
              <Video size={20} color="#38bdf8" />
              Roadside Camera to Traffic Signal
            </h3>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "4px" }}>
              Deployment path: existing highway/intersection cameras feed the AI host; the ESP32 remains the local signal controller.
            </p>
          </div>
          <span style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.7px", color: "#fbbf24", border: "1px solid rgba(251,191,36,0.4)", background: "rgba(251,191,36,0.1)", padding: "6px 10px", borderRadius: "999px" }}>
            CAMERA INTEGRATION: PLANNED
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "stretch", gap: "8px", flexWrap: "wrap" }}>
          {[
            { icon: <Video size={19} color="#38bdf8" />, title: "Roadside cameras", body: "Existing CCTV or network video stream (for example, RTSP)." },
            { icon: <Eye size={19} color="#a78bfa" />, title: "AI vision host", body: "YOLO detects emergency vehicles; temporal debounce confirms the approach." },
            { icon: <Brain size={19} color="#c084fc" />, title: "Priority engine", body: "Confirmed approach becomes a safe, sequenced priority command." },
            { icon: <Cloud size={19} color="#fb923c" />, title: "Firebase mailbox", body: "Carries the command to the intersection controller." },
            { icon: <Cpu size={19} color="#34d399" />, title: "ESP32 signal circuit", body: "Runs the local FSM and drives the four approach lights." },
          ].map((step, index, steps) => (
            <React.Fragment key={step.title}>
              <div style={{ flex: "1 1 155px", minWidth: 0, padding: "13px", borderRadius: "12px", background: "rgba(15,23,42,0.58)", border: "1px solid rgba(148,163,184,0.18)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "7px" }}>
                  {step.icon}
                  <span style={{ fontSize: "0.8rem", fontWeight: 750 }}>{step.title}</span>
                </div>
                <p style={{ fontSize: "0.72rem", lineHeight: 1.45, color: "var(--text-muted)" }}>{step.body}</p>
              </div>
              {index < steps.length - 1 && <ArrowRight size={16} color="#64748b" style={{ alignSelf: "center", flexShrink: 0 }} />}
            </React.Fragment>
          ))}
        </div>

        <p style={{ fontSize: "0.72rem", color: "#cbd5e1", marginTop: "13px" }}>
          Current demo: recorded detection replay/manual dispatch and a Wokwi ESP32 simulation. No roadside camera is connected yet; the camera stream terminates at the AI host, not at the ESP32 GPIO pins.
        </p>
      </section>

      {/* ── Main Architecture Flow (Horizontal Pipeline) ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr auto 1fr auto 1fr", alignItems: "stretch", gap: "0", marginBottom: "24px" }}>
        {/* Layer 1: ESP32 (IoT Edge) */}
        <ArchNode
          title="ESP32 DevKit V1"
          subtitle="IoT Edge Controller (Wokwi Simulation)"
          icon={<Cpu size={24} color="#f59e0b" />}
          color="#f59e0b"
          glowColor="rgba(245,158,11,0.4)"
          status={esp32Ok ? "online" : "warning"}
          pulseActive={tick % 3 === 0}
          details={[
            "Local FSM with 7 safety invariants (S1-S7)",
            "millis()-based safety FSM",
            "Sequenced priority command validation",
            "12 LED GPIOs (4 directions × RGB)",
            "Heartbeat watchdog → fallback mode",
            "Polls Firebase commands; uploads state asynchronously",
          ]}
          tech={["C++", "Arduino", "WiFi", "REST", "HMAC-SHA256"]}
        />

        {/* Arrow: ESP32 → Firebase */}
        <div style={{ display: "flex", alignItems: "center", padding: "0 4px" }}>
          <FlowArrow
            label="State + Heartbeat"
            protocol="HTTPS PUT/GET"
            color="#f59e0b"
            active={esp32Ok || true}
          />
        </div>

        {/* Layer 2: Firebase RTDB */}
        <ArchNode
          title="Firebase Realtime DB"
          subtitle="Cloud Middleware & Mailbox Broker"
          icon={<Cloud size={24} color="#fb923c" />}
          color="#fb923c"
          glowColor="rgba(251,146,60,0.4)"
          status={firebaseOk ? "online" : "warning"}
          pulseActive={tick % 4 === 1}
          details={[
            "/intersections/i1/state → current FSM",
            "/intersections/i1/command → priority cmds",
            "/intersections/i1/heartbeat → liveness",
            "Acts as mailbox between ESP32 ↔ Server",
            "REST API with database secret auth",
            "REST mailbox; cloud latency varies with network conditions",
          ]}
          tech={["Firebase RTDB", "REST API", "JSON", "Auth Token"]}
        />

        {/* Arrow: Firebase → Server */}
        <div style={{ display: "flex", alignItems: "center", padding: "0 4px" }}>
          <FlowArrow
            label="Commands + State"
            protocol="REST Poll (700ms)"
            color="#a855f7"
            active={isConnected}
          />
        </div>

        {/* Layer 3: Python AI Server */}
        <ArchNode
          title="FastAPI Priority Server"
          subtitle="Confirmed detections and signal commands"
          icon={<Brain size={24} color="#a855f7" />}
          color="#a855f7"
          glowColor="rgba(168,85,247,0.4)"
          status={isConnected ? "online" : "offline"}
          pulseActive={tick % 2 === 0}
          details={[
            "AI Priority Engine (FSM orchestrator)",
            "Receives confirmed detections from the vision worker",
            "A/B Simulation comparisons",
            "JWT RBAC (operator/admin/camera)",
            "Rate limiting and role-based access",
            "Deterministic traffic simulator",
          ]}
          tech={["Python 3.12", "FastAPI", "Priority Engine", "JWT", "WebSocket"]}
        />

        {/* Arrow: Server → Frontend */}
        <div style={{ display: "flex", alignItems: "center", padding: "0 4px" }}>
          <FlowArrow
            label="Live State Stream"
            protocol="WebSocket"
            color="#38bdf8"
            active={isConnected}
          />
        </div>

        {/* Layer 4: React Dashboard */}
        <ArchNode
          title="React Dashboard"
          subtitle="Real-time Digital Twin & Analytics"
          icon={<Monitor size={24} color="#38bdf8" />}
          color="#38bdf8"
          glowColor="rgba(56,189,248,0.4)"
          status={isConnected ? "online" : "warning"}
          pulseActive={tick % 3 === 2}
          details={[
            "2D animated intersection simulation",
            "Emergency dispatch with visual feedback",
            "A/B battle comparison with replay",
            "Priority event log & security audit",
            "WebSocket live feed + polling fallback",
            "Role-based UI controls (RBAC)",
          ]}
          tech={["React 18", "TypeScript", "Vite", "SVG", "WebSocket"]}
        />
      </div>

      {/* ── Key Features Grid ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        {/* Security */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Shield size={18} color="#10b981" />
            Security & Authentication
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {[
              { icon: <Lock size={13} />, text: "JWT bearer tokens with role-based access control", color: "#10b981" },
              { icon: <Shield size={13} />, text: "HMAC-SHA256 command signing (ESP32 ↔ Server)", color: "#38bdf8" },
              { icon: <AlertTriangle size={13} />, text: "Rate limiting: 10 req/s + burst 20 per client", color: "#f59e0b" },
              { icon: <Eye size={13} />, text: "Full security audit log with IP tracking", color: "#a855f7" },
            ].map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "8px", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                <span style={{ color: item.color, marginTop: "1px" }}>{item.icon}</span>
                <span>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* AI & Vision */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
            <Eye size={18} color="#f59e0b" />
            AI & Computer Vision
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {[
              { icon: <Zap size={13} />, text: "YOLOv8 real-time emergency vehicle detection", color: "#f59e0b" },
              { icon: <Brain size={13} />, text: "Debounced detection: 5/8 frame confirmation window", color: "#a855f7" },
              { icon: <Activity size={13} />, text: "Deterministic A/B simulation engine with KPI tracking", color: "#38bdf8" },
              { icon: <CheckCircle2 size={13} />, text: "Conf threshold 0.55, min bbox area ratio 0.005", color: "#10b981" },
            ].map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "8px", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                <span style={{ color: item.color, marginTop: "1px" }}>{item.icon}</span>
                <span>{item.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Safety Invariants */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={18} color="#ef4444" />
            Safety Invariants (S1–S7)
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {[
              { code: "S1", text: "NS and EW never green simultaneously" },
              { code: "S2", text: "No G→G or R→G without Y+ALL_RED transition" },
              { code: "S3", text: "Normal clearance 3s + 2s; emergency demo clearance 2s + 1s after minimum green" },
              { code: "S4", text: "MIN_GREEN 5s before any preemption" },
              { code: "S5", text: "PRIORITY watchdog max 30s hold" },
              { code: "S6", text: "Heartbeat timeout → FALLBACK mode" },
              { code: "S7", text: "Safe clearance transition out of priority" },
            ].map((inv, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "8px", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                <span
                  style={{
                    fontSize: "0.65rem",
                    padding: "1px 6px",
                    borderRadius: "4px",
                    background: "rgba(239,68,68,0.15)",
                    color: "#ef4444",
                    fontWeight: 700,
                    fontFamily: "monospace",
                    flexShrink: 0,
                  }}
                >
                  {inv.code}
                </span>
                <span>{inv.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Data Path Summary ── */}
      <div className="glass-panel" style={{ padding: "24px" }}>
        <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
          <Radio size={18} color="#38bdf8" />
          Live Data Path Summary
        </h3>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
            padding: "16px",
            background: "rgba(0,0,0,0.3)",
            borderRadius: "12px",
          }}
        >
          {[
            { label: "ESP32 Firmware", sub: "12 GPIO LEDs", color: "#f59e0b", icon: <Cpu size={20} /> },
            { label: "Firebase RTDB", sub: "REST Mailbox", color: "#fb923c", icon: <Cloud size={20} /> },
            { label: "FastAPI Server", sub: "AI + Priority", color: "#a855f7", icon: <Server size={20} /> },
            { label: "WebSocket", sub: `HB #${heartbeat}`, color: "#38bdf8", icon: <Wifi size={20} /> },
            { label: "React Dashboard", sub: "Live Twin", color: "#6366f1", icon: <Monitor size={20} /> },
          ].map((node, i, arr) => (
            <React.Fragment key={i}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div
                  style={{
                    width: "40px",
                    height: "40px",
                    borderRadius: "10px",
                    background: `${node.color}20`,
                    border: `1px solid ${node.color}40`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: node.color,
                  }}
                >
                  {node.icon}
                </div>
                <div>
                  <div style={{ fontSize: "0.8rem", fontWeight: 700 }}>{node.label}</div>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{node.sub}</div>
                </div>
              </div>
              {i < arr.length - 1 && (
                <ArrowRight size={20} color="#475569" style={{ flexShrink: 0 }} />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Metrics row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginTop: "16px" }}>
          <div className="glass-card" style={{ padding: "12px", textAlign: "center" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Poll Interval</div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#f59e0b" }}>700ms</div>
          </div>
          <div className="glass-card" style={{ padding: "12px", textAlign: "center" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>WebSocket Feed</div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#38bdf8" }}>Real-time</div>
          </div>
          <div className="glass-card" style={{ padding: "12px", textAlign: "center" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Heartbeat Counter</div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#10b981" }}>#{heartbeat}</div>
          </div>
          <div className="glass-card" style={{ padding: "12px", textAlign: "center" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Server Uptime</div>
            <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#a855f7" }}>
              {health?.uptime_s ? `${(health.uptime_s / 60).toFixed(1)}m` : "—"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
