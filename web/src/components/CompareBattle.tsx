import React, { useState, useEffect, useRef } from "react";
import { Play, Pause, RotateCcw, FastForward, CheckCircle, Clock, Zap } from "lucide-react";
import { SimRun } from "../types";

interface CompareBattleProps {
  apiBase: string;
}

export const CompareBattle: React.FC<CompareBattleProps> = ({ apiBase }) => {
  const [runs, setRuns] = useState<SimRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [currentRun, setCurrentRun] = useState<SimRun | null>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackIdx, setPlaybackIdx] = useState(0);
  const [speed, setSpeed] = useState(1.0);
  const timerRef = useRef<any>(null);

  // Load available simulation runs
  useEffect(() => {
    const token = localStorage.getItem("token") || "";
    const authHeaders: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    fetch(`${apiBase}/events`, { headers: authHeaders })
      .catch(() => {});

    // Try to trigger or load runs from API
    fetch(`${apiBase}/kpi/summary`, { headers: authHeaders })
      .then((r) => r.json())
      .then(() => {
        // Run a default comparison if none exist
        fetch(`${apiBase}/sim/run`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${localStorage.getItem("token") || ""}`,
          },
          body: JSON.stringify({ seed: 999, scenario: "Demo Ambulance on N", duration_s: 60.0 }),
        })
          .then((r) => r.json())
          .then((data) => {
            if (data.run_id) {
              fetch(`${apiBase}/sim/runs/${data.run_id}`, {
                headers: { Authorization: `Bearer ${localStorage.getItem("token") || ""}` },
              })
                .then((r) => r.json())
                .then((fullRun) => {
                  setCurrentRun(fullRun);
                  setSelectedRunId(fullRun.run_id);
                  setRuns([fullRun]);
                });
            }
          })
          .catch(() => {});
      })
      .catch(() => {});
  }, [apiBase]);

  // Animation playback ticker
  useEffect(() => {
    if (isPlaying && currentRun && currentRun.baseline_trace) {
      const maxFrames = Math.min(
        currentRun.baseline_trace.length,
        currentRun.priority_trace ? currentRun.priority_trace.length : currentRun.baseline_trace.length
      );

      timerRef.current = setInterval(() => {
        setPlaybackIdx((prev) => {
          if (prev >= maxFrames - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 500 / speed);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, currentRun, speed]);

  const baseFrame = currentRun?.baseline_trace?.[playbackIdx];
  const prioFrame = currentRun?.priority_trace?.[playbackIdx];

  const bKpis = currentRun?.baseline_kpis;
  const pKpis = currentRun?.priority_kpis;
  const waitDiff = bKpis && pKpis ? (bKpis.ambulance_wait_s - pKpis.ambulance_wait_s).toFixed(1) : "0.0";

  return (
    <div style={{ padding: "0 24px" }}>
      {/* Header & KPI Summary Cards */}
      <div className="glass-panel" style={{ padding: "24px", marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px", marginBottom: "20px" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>A/B Battle Replay Arena</h2>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Side-by-side synchronized comparison: Fixed-Timer Baseline vs AI Priority Controller
            </p>
          </div>

          {/* Controls */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <button
              className="btn btn-primary"
              onClick={() => setIsPlaying(!isPlaying)}
            >
              {isPlaying ? <Pause size={16} /> : <Play size={16} />}
              <span>{isPlaying ? "Pause" : "Play Battle"}</span>
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setIsPlaying(false);
                setPlaybackIdx(0);
              }}
            >
              <RotateCcw size={16} />
              <span>Reset</span>
            </button>
            {[1.0, 2.0].map((s) => (
              <button
                key={s}
                className={`btn ${speed === s ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "6px 10px", fontSize: "0.8rem" }}
                onClick={() => setSpeed(s)}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>

        {/* Highlight KPI Diff Cards */}
        {bKpis && pKpis && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
            <div className="glass-card" style={{ padding: "16px", borderLeft: "4px solid #10b981" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
                <Clock size={14} color="#10b981" />
                <span>Ambulance Wait Reduction</span>
              </div>
              <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#10b981", margin: "6px 0" }}>
                −{waitDiff}s
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                Baseline: {bKpis.ambulance_wait_s}s → Priority: {pKpis.ambulance_wait_s}s
              </div>
            </div>

            <div className="glass-card" style={{ padding: "16px", borderLeft: "4px solid #38bdf8" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
                <Zap size={14} color="#38bdf8" />
                <span>Crossing Time</span>
              </div>
              <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#38bdf8", margin: "6px 0" }}>
                {pKpis.ambulance_crossing_time_s}s
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                Vs Baseline: {bKpis.ambulance_crossing_time_s}s
              </div>
            </div>

            <div className="glass-card" style={{ padding: "16px", borderLeft: "4px solid #f59e0b" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Extra Delay for Others</div>
              <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#f59e0b", margin: "6px 0" }}>
                +{pKpis.extra_delay_others_s}s
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Minimal civilian impact</div>
            </div>

            <div className="glass-card" style={{ padding: "16px", borderLeft: "4px solid #a855f7" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Network Recovery Time</div>
              <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#a855f7", margin: "6px 0" }}>
                {pKpis.recovery_time_s}s
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Time to balance queues</div>
            </div>
          </div>
        )}
      </div>

      {/* Side-by-Side Canvas Visualizer */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Baseline (Fixed Timer) */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#94a3b8" }}>
              A: Fixed-Timer Baseline
            </h3>
            <span className="font-mono" style={{ fontSize: "0.85rem", color: "#38bdf8" }}>
              Phase: {baseFrame?.phase || "NS_GREEN"}
            </span>
          </div>

          <div style={{ background: "#0c1322", padding: "16px", borderRadius: "14px", textAlign: "center" }}>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "8px" }}>
              Queue Lengths per Approach
            </div>
            <div style={{ display: "flex", justifyContent: "space-around", marginBottom: "16px" }}>
              {["N", "E", "S", "W"].map((app) => (
                <div key={app} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{app}</div>
                  <div style={{ width: "24px", height: "80px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", display: "flex", alignItems: "flex-end", margin: "6px 0" }}>
                    <div
                      style={{
                        width: "100%",
                        height: `${Math.min(100, ((baseFrame?.queues?.[app] || 0) / 10) * 100)}%`,
                        background: "#ef4444",
                        borderRadius: "4px",
                        transition: "height 0.2s",
                      }}
                    />
                  </div>
                  <div className="font-mono" style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                    {baseFrame?.queues?.[app] || 0}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ fontSize: "0.85rem", color: baseFrame?.ambulance?.status === "cleared" ? "#10b981" : "#f59e0b" }}>
              Ambulance: {baseFrame?.ambulance ? `${baseFrame.ambulance.status} (${(baseFrame.ambulance.distance_m ?? 0).toFixed(0)}m)` : "In approach queue"}
            </div>
          </div>
        </div>

        {/* Priority Controller */}
        <div className="glass-panel" style={{ padding: "20px", border: "1px solid rgba(56,189,248,0.4)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, color: "#38bdf8" }}>
              B: AI Priority Orchestrator
            </h3>
            <span className="font-mono" style={{ fontSize: "0.85rem", color: prioFrame?.mode === "PRIORITY" ? "#38bdf8" : "#10b981", fontWeight: 700 }}>
              {prioFrame?.mode} ({prioFrame?.phase})
            </span>
          </div>

          <div style={{ background: "#0c1322", padding: "16px", borderRadius: "14px", textAlign: "center" }}>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "8px" }}>
              Queue Lengths per Approach
            </div>
            <div style={{ display: "flex", justifyContent: "space-around", marginBottom: "16px" }}>
              {["N", "E", "S", "W"].map((app) => (
                <div key={app} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{app}</div>
                  <div style={{ width: "24px", height: "80px", background: "rgba(255,255,255,0.05)", borderRadius: "4px", display: "flex", alignItems: "flex-end", margin: "6px 0" }}>
                    <div
                      style={{
                        width: "100%",
                        height: `${Math.min(100, ((prioFrame?.queues?.[app] || 0) / 10) * 100)}%`,
                        background: app === "N" && prioFrame?.mode === "PRIORITY" ? "#10b981" : "#38bdf8",
                        borderRadius: "4px",
                        transition: "height 0.2s",
                      }}
                    />
                  </div>
                  <div className="font-mono" style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                    {prioFrame?.queues?.[app] || 0}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ fontSize: "0.85rem", color: prioFrame?.ambulance?.status === "cleared" ? "#10b981" : "#38bdf8", fontWeight: 600 }}>
              Ambulance: {prioFrame?.ambulance ? `${prioFrame.ambulance.status} (${(prioFrame.ambulance.distance_m ?? 0).toFixed(0)}m)` : "Granted green clearance"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
