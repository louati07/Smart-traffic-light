import React, { useState, useEffect, useRef, useCallback } from "react";
import { IntersectionState, Mode, LightsState } from "../types";
import { Siren, ShieldAlert, CheckCircle2, AlertTriangle } from "lucide-react";

interface LiveTwinProps {
  state: IntersectionState;
  onManualCommand: (cmd: "PRIORITY" | "CLEAR", axis?: "NS" | "EW", approach?: Dir) => void;
  userRole: string;
}

/* ── tiny traffic simulation ────────────────────────────────── */

type Dir = "N" | "S" | "E" | "W";

interface Car {
  id: number;
  dir: Dir;
  pos: number;          // 0‑1 along the approach (0=far, 1=passed intersection)
  speed: number;        // units/frame
  color: string;
  isEmergency: boolean;
  width: number;
  height: number;
  lateralOffset?: number; // steers toward right shoulder/curb to let emergency vehicle pass
}

const CAR_COLORS = ["#38bdf8", "#a855f7", "#f97316", "#34d399", "#fb7185", "#facc15", "#818cf8", "#22d3ee", "#3b82f6", "#10b981"];
const VIEW_HALF = 480;             // Total road span = 960 units (from -480 to +480)
const STOP_LINE_POS = 0.420;       // Center of car stops here (bumper stops 6px before -58 stop line)
const INTERSECTION_ENTER = 0.440;  // Once past this, car has entered intersection and clears it
const DESPAWN_POS = 1.06;

let nextId = 1;

function spawnCar(dir: Dir, isEmergency = false): Car {
  return {
    id: nextId++,
    dir,
    pos: -0.05,
    speed: isEmergency ? 0.0032 : 0.0016,
    color: isEmergency ? "#ffffff" : CAR_COLORS[Math.floor(Math.random() * CAR_COLORS.length)],
    isEmergency,
    width: 13,
    height: 24,
    lateralOffset: 0,
  };
}

function getInitialCars(): Car[] {
  const initial: Car[] = [];
  const dirs: Dir[] = ["N", "S", "E", "W"];
  dirs.forEach(d => {
    initial.push({
      id: nextId++,
      dir: d,
      pos: 0.12 + Math.random() * 0.08,
      speed: 0.0016,
      color: CAR_COLORS[Math.floor(Math.random() * CAR_COLORS.length)],
      isEmergency: false,
      width: 13,
      height: 24,
      lateralOffset: 0,
    });
    initial.push({
      id: nextId++,
      dir: d,
      pos: 0.28 + Math.random() * 0.08,
      speed: 0.0012,
      color: CAR_COLORS[Math.floor(Math.random() * CAR_COLORS.length)],
      isEmergency: false,
      width: 13,
      height: 24,
      lateralOffset: 0,
    });
  });
  return initial;
}

/* ── SVG helpers ────────────────────────────────────────────── */

function isPerpendicular(d1: Dir, d2: Dir): boolean {
  const isV1 = d1 === "N" || d1 === "S";
  const isV2 = d2 === "N" || d2 === "S";
  return isV1 !== isV2;
}

function carTransform(car: Car): { x: number; y: number; rot: number } {
  // Right-hand traffic lane offset from road center (curb is further outward)
  const baseLaneOff = 22;
  const laneOff = baseLaneOff + (car.lateralOffset || 0);

  // SVG road spans from -480 to +480 (960 units)
  switch (car.dir) {
    case "N": {
      // Enters from top (y=-480), drives south (downward). Right curb is negative X (-58)
      const y = -480 + car.pos * 960;
      return { x: -laneOff, y, rot: 180 };
    }
    case "S": {
      // Enters from bottom (y=+480), drives north (upward). Right curb is positive X (+58)
      const y = 480 - car.pos * 960;
      return { x: laneOff, y, rot: 0 };
    }
    case "E": {
      // Enters from right (x=+480), drives west (leftward). Right curb is negative Y (-58)
      const x = 480 - car.pos * 960;
      return { x, y: -laneOff, rot: 270 };
    }
    case "W": {
      // Enters from left (x=-480), drives east (rightward). Right curb is positive Y (+58)
      const x = -480 + car.pos * 960;
      return { x, y: laneOff, rot: 90 };
    }
  }
}

/* ── component ──────────────────────────────────────────────── */

export const LiveTwin: React.FC<LiveTwinProps> = ({ state, onManualCommand, userRole }) => {
  const [selectedApproach, setSelectedApproach] = useState<Dir>("N");
  const [selectedAxis, setSelectedAxis] = useState<"NS" | "EW">("NS");
  const [cars, setCars] = useState<Car[]>(() => getInitialCars());
  const [strobeOn, setStrobeOn] = useState(false);
  const lightsRef = useRef(state.lights || { N: "R", E: "R", S: "R", W: "R" });
  const modeRef = useRef(state.mode || "NORMAL");
  const emergencyDirRef = useRef<Dir>("N");
  const animRef = useRef<number>(0);
  const spawnTimerRef = useRef(0);
  const emergencySpawned = useRef(false);

  const rawLights = state.lights || { N: "R", E: "R", S: "R", W: "R" };
  const phase = state.phase || "NS_GREEN";
  const mode = state.mode || "NORMAL";

  // Direct 1:1 hardware reflection: Digital Twin faithfully mirrors the ESP32 state
  const lights: LightsState = { ...rawLights };

  // Keep refs in sync
  useEffect(() => { lightsRef.current = lights; }, [lights.N, lights.S, lights.E, lights.W]);
  useEffect(() => {
    modeRef.current = mode;
    if (mode !== "PRIORITY") {
      emergencySpawned.current = false;
    }
  }, [mode]);

  // Guaranteed instant dispatch on click
  const handleDispatchEmergency = (dir: Dir, axis: "NS" | "EW") => {
    emergencyDirRef.current = dir;
    // Immediately spawn emergency vehicle on that approach and replace any finished ones
    setCars(prev => {
      const remaining = prev.filter(c => !c.isEmergency);
      return [...remaining, spawnCar(dir, true)];
    });
    emergencySpawned.current = true;
    onManualCommand("PRIORITY", axis, dir);
  };

  const handleClearHold = () => {
    emergencySpawned.current = false;
    onManualCommand("CLEAR");
  };

  // Strobe effect for emergency vehicle
  useEffect(() => {
    const iv = setInterval(() => setStrobeOn(s => !s), 300);
    return () => clearInterval(iv);
  }, []);

  // Main animation loop
  useEffect(() => {
    const tick = () => {
      setCars(prev => {
        let next = [...prev];
        const curMode = modeRef.current;

        // Spawn new traffic cars frequently to keep longer roads populated
        spawnTimerRef.current++;
        if (spawnTimerRef.current % 45 === 0) {
          const dirs: Dir[] = ["N", "S", "E", "W"];
          const dir = dirs[Math.floor(Math.random() * 4)];

          // Never spawn civilian cars into the active emergency lane during PRIORITY mode
          const isEmergencyLane = curMode === "PRIORITY" && dir === emergencyDirRef.current;

          if (!isEmergencyLane) {
            const countInDir = next.filter(c => c.dir === dir && !c.isEmergency).length;
            const anyNearSpawn = next.some(c => c.dir === dir && c.pos < 0.10);
            if (countInDir < 5 && !anyNearSpawn) {
              next.push(spawnCar(dir));
            }
          }
        }

        // Spawn emergency vehicle when PRIORITY activates externally (e.g. from backend replay)
        if (curMode === "PRIORITY" && !emergencySpawned.current && !next.some(c => c.isEmergency)) {
          emergencySpawned.current = true;
          next.push(spawnCar(emergencyDirRef.current, true));
        }

        // Sort cars by descending pos so front cars are evaluated first in each approach
        next.sort((a, b) => b.pos - a.pos);

        // Find active emergency vehicle approaching or in intersection
        const emergencyVeh = next.find(c => c.isEmergency && c.pos < 0.65);

        // True signal colors from physical ESP32 controller
        const curLights: LightsState = { ...lightsRef.current };

        // Update each vehicle's kinematics with barrier checking & yielding logic
        for (const car of next) {
          const light = curLights[car.dir] || "R";

          if (car.isEmergency) {
            // 1. Follow car ahead if it hasn't pulled over to shoulder yet
            let blockedAhead = false;
            let leaderSpeed = 0.0016;

            for (const other of next) {
              if (other.id === car.id || other.dir !== car.dir) continue;
              if (other.pos > car.pos && (other.pos - car.pos) < 0.065) {
                if ((other.lateralOffset || 0) < 8) {
                  blockedAhead = true;
                  leaderSpeed = other.speed;
                  break;
                }
              }
            }

            // 2. Stop barrier:
            // Check if cross-traffic actually has an active green light:
            const crossAxis = (car.dir === "N" || car.dir === "S") ? "EW" : "NS";
            const crossHasGreen = crossAxis === "NS"
              ? (curLights.N === "G" || curLights.S === "G")
              : (curLights.E === "G" || curLights.W === "G");

            // The ambulance ONLY yields if cross-traffic has Green:
            let maxPos = 999.0;
            if (crossHasGreen && car.pos < INTERSECTION_ENTER) {
              maxPos = STOP_LINE_POS;
            }

            const distToStop = maxPos - car.pos;

            if (blockedAhead) {
              car.speed = Math.max(leaderSpeed, 0.0012);
              car.pos += car.speed;
            } else if (crossHasGreen && distToStop <= 0) {
              // Yielding briefly for perpendicular cars to finish clearing
              car.pos = maxPos;
              car.speed = 0;
            } else if (crossHasGreen && distToStop < 0.08) {
              // Decelerate approaching active cross-traffic
              const desiredSpeed = Math.min(0.0022, distToStop * 0.03);
              car.speed = Math.max(car.speed * 0.88, desiredSpeed);
              car.pos += car.speed;
            } else {
              // Cross traffic stopped or all-red/green: roar forward with emergency siren speed!
              const targetSpeed = light === "G" ? 0.0042 : 0.0032;
              car.speed = Math.min(car.speed + 0.0002, targetSpeed);
              car.pos += car.speed;
            }
            continue;
          }

          // --- Civilian Vehicle Logic ---
          // Check if an emergency vehicle is approaching behind this car in the same lane
          const isAmbulanceBehind = emergencyVeh &&
            emergencyVeh.dir === car.dir &&
            emergencyVeh.pos < car.pos &&
            (car.pos - emergencyVeh.pos) < 0.35;

          if (isAmbulanceBehind) {
            // Pull over toward the right shoulder to yield to approaching sirens
            car.lateralOffset = Math.min((car.lateralOffset || 0) + 0.6, 14);

            // If light is Green or car is inside the intersection, accelerate forward to clear the lane!
            if (light === "G" || car.pos >= INTERSECTION_ENTER) {
              const clearSpeed = 0.0024;
              car.speed = Math.min(car.speed + 0.0001, clearSpeed);
              car.pos += car.speed;
              continue;
            }
          } else if ((car.lateralOffset || 0) > 0) {
            // Gradually steer back into normal lane center when no emergency
            car.lateralOffset = Math.max((car.lateralOffset || 0) - 0.2, 0);
          }

          // 1. Determine stop barrier position
          let maxPos = 999.0;

          // If light is Red or Yellow and the car has not yet entered the intersection:
          if ((light === "R" || light === "Y") && car.pos < INTERSECTION_ENTER) {
            maxPos = STOP_LINE_POS;
          }

          // 2. Queue behind car directly ahead in the same approach lane
          for (const other of next) {
            if (other.id === car.id || other.dir !== car.dir) continue;
            if (other.pos > car.pos) {
              const queueBarrier = other.pos - 0.045;
              if (queueBarrier < maxPos) {
                maxPos = queueBarrier;
              }
            }
          }

          // 3. Movement kinematics
          const distToStop = maxPos - car.pos;

          if (distToStop <= 0) {
            // Already at or reached stop barrier: full stop, zero creep!
            car.pos = maxPos;
            car.speed = 0;
          } else if (distToStop < 0.10) {
            // Approaching barrier: decelerate smoothly to zero right at the stop mark
            const desiredSpeed = Math.min(0.0016, distToStop * 0.018);
            if (desiredSpeed < 0.00015) {
              car.speed = 0;
              car.pos = maxPos;
            } else {
              car.speed = Math.max(car.speed * 0.90, desiredSpeed);
              car.pos += car.speed;
              if (car.pos > maxPos) {
                car.pos = maxPos;
                car.speed = 0;
              }
            }
          } else {
            // Open road: cruise forward smoothly on Green
            const targetSpeed = 0.0016;
            car.speed = Math.min(car.speed + 0.00008, targetSpeed);
            car.pos += car.speed;
          }
        }

        // Remove despawned cars
        const filtered = next.filter(c => c.pos < DESPAWN_POS);
        // If emergency vehicle despawned, allow next dispatch
        if (next.some(c => c.isEmergency) && !filtered.some(c => c.isEmergency)) {
          emergencySpawned.current = false;
        }
        return filtered;
      });
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, []);

  const getColorHex = (c: string) => {
    if (c === "G") return "#10b981";
    if (c === "Y") return "#f59e0b";
    return "#ef4444";
  };

  const getGlow = (c: string) => {
    if (c === "G") return "drop-shadow(0 0 12px #10b981) drop-shadow(0 0 4px #10b981)";
    if (c === "Y") return "drop-shadow(0 0 12px #f59e0b) drop-shadow(0 0 4px #f59e0b)";
    return "drop-shadow(0 0 12px #ef4444) drop-shadow(0 0 4px #ef4444)";
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "24px", padding: "0 24px" }}>
      {/* 2D Digital Twin Canvas */}
      <div className="glass-panel" style={{ padding: "24px", display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>

        {/* Mode Status Banner */}
        <div style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700 }}>2D Digital Twin — Live Simulation</h2>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Real-time animated traffic with AI priority control</p>
          </div>

          <div>
            {mode === "PRIORITY" && (
              <div className="siren-badge">
                <Siren size={18} />
                <span>
                  EMERGENCY PRIORITY ACTIVE — {emergencyDirRef.current === "N" ? "NORTH" : emergencyDirRef.current === "S" ? "SOUTH" : emergencyDirRef.current === "E" ? "EAST" : "WEST"} APPROACH
                </span>
              </div>
            )}
            {mode === "FALLBACK" && (
              <div style={{ background: "rgba(239, 68, 68, 0.2)", border: "1px solid #ef4444", color: "#f87171", padding: "4px 12px", borderRadius: "9999px", display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
                <AlertTriangle size={18} />
                <span>FALLBACK MODE</span>
              </div>
            )}
            {mode === "NORMAL" && (
              <div style={{ background: "rgba(16, 185, 129, 0.15)", border: "1px solid #10b981", color: "#34d399", padding: "4px 12px", borderRadius: "9999px", display: "flex", alignItems: "center", gap: "6px", fontWeight: 600 }}>
                <CheckCircle2 size={18} />
                <span>NORMAL CYCLE</span>
              </div>
            )}
          </div>
        </div>

        {/* Top-Down 2D SVG Intersection */}
        <svg
          viewBox="-480 -480 960 960"
          style={{
            width: "100%",
            maxWidth: "620px",
            height: "auto",
            background: "linear-gradient(135deg, #0a0f1e 0%, #0d1527 100%)",
            borderRadius: "20px",
            border: "1px solid rgba(255, 255, 255, 0.06)",
            boxShadow: "0 16px 48px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.05)",
          }}
        >
          {/* Ground */}
          <rect x="-480" y="-480" width="960" height="960" fill="#0a1120" />

          {/* Sidewalks / curb areas (lighter strips along roads) */}
          <rect x="-62" y="-480" width="4" height="960" fill="#1a2438" />
          <rect x="58" y="-480" width="4" height="960" fill="#1a2438" />
          <rect x="-480" y="-62" width="960" height="4" fill="#1a2438" />
          <rect x="-480" y="58" width="960" height="4" fill="#1a2438" />

          {/* North-South Road */}
          <rect x="-58" y="-480" width="116" height="960" fill="#1e293b" />
          {/* East-West Road */}
          <rect x="-480" y="-58" width="960" height="116" fill="#1e293b" />

          {/* Lane dividers */}
          <line x1="0" y1="-480" x2="0" y2="-58" stroke="#f59e0b" strokeWidth="2" strokeDasharray="12 10" opacity="0.7" />
          <line x1="0" y1="58" x2="0" y2="480" stroke="#f59e0b" strokeWidth="2" strokeDasharray="12 10" opacity="0.7" />
          <line x1="-480" y1="0" x2="-58" y2="0" stroke="#f59e0b" strokeWidth="2" strokeDasharray="12 10" opacity="0.7" />
          <line x1="58" y1="0" x2="480" y2="0" stroke="#f59e0b" strokeWidth="2" strokeDasharray="12 10" opacity="0.7" />

          {/* Zebra Crossings */}
          {[-42, -28, -14, 0, 14, 28, 42].map(off => (
            <React.Fragment key={off}>
              <rect x={off - 4} y="-74" width="8" height="12" fill="#94a3b8" opacity="0.4" rx="1" />
              <rect x={off - 4} y="62" width="8" height="12" fill="#94a3b8" opacity="0.4" rx="1" />
              <rect x="62" y={off - 4} width="12" height="8" fill="#94a3b8" opacity="0.4" rx="1" />
              <rect x="-74" y={off - 4} width="12" height="8" fill="#94a3b8" opacity="0.4" rx="1" />
            </React.Fragment>
          ))}

          {/* Central Intersection Box */}
          <rect x="-58" y="-58" width="116" height="116" fill="#151d2f" />

          {/* Stop lines */}
          <line x1="-58" y1="-58" x2="0" y2="-58" stroke="#e2e8f0" strokeWidth="3" opacity="0.6" />
          <line x1="0" y1="58" x2="58" y2="58" stroke="#e2e8f0" strokeWidth="3" opacity="0.6" />
          <line x1="58" y1="-58" x2="58" y2="0" stroke="#e2e8f0" strokeWidth="3" opacity="0.6" />
          <line x1="-58" y1="0" x2="-58" y2="58" stroke="#e2e8f0" strokeWidth="3" opacity="0.6" />

          {/* ─── APPROACH LABELS ─── */}
          <text x="0" y="-450" textAnchor="middle" fill="#64748b" fontSize="13" fontWeight="800" letterSpacing="3" fontFamily="sans-serif">NORTH</text>
          <polygon points="-6,-434 6,-434 0,-424" fill="#475569" opacity="0.5" />

          <text x="0" y="465" textAnchor="middle" fill="#64748b" fontSize="13" fontWeight="800" letterSpacing="3" fontFamily="sans-serif">SOUTH</text>
          <polygon points="-6,434 6,434 0,444" fill="#475569" opacity="0.5" />

          <text x="450" y="4" textAnchor="middle" fill="#64748b" fontSize="13" fontWeight="800" letterSpacing="3" fontFamily="sans-serif">EAST</text>
          <polygon points="424,-6 424,6 434,0" fill="#475569" opacity="0.5" />

          <text x="-450" y="4" textAnchor="middle" fill="#64748b" fontSize="13" fontWeight="800" letterSpacing="3" fontFamily="sans-serif">WEST</text>
          <polygon points="-424,-6 -424,6 -434,0" fill="#475569" opacity="0.5" />

          {/* ─── TRAFFIC LIGHTS ─── */}

          {/* North light (right side of N-S road, above intersection) */}
          <g transform="translate(38, -90)">
            <rect x="-2" y="0" width="4" height="20" fill="#334155" />
            <rect x="-13" y="-48" width="26" height="50" rx="6" fill="#0b0f19" stroke="#475569" strokeWidth="1.5" />
            <circle cx="0" cy="-34" r="7" fill={lights.N === "R" ? getColorHex("R") : "#1a0808"} style={{ filter: lights.N === "R" ? getGlow("R") : "none", transition: "all 0.4s" }} />
            <circle cx="0" cy="-17" r="7" fill={lights.N === "Y" ? getColorHex("Y") : "#1a1408"} style={{ filter: lights.N === "Y" ? getGlow("Y") : "none", transition: "all 0.4s" }} />
            <circle cx="0" cy="0" r="7" fill={lights.N === "G" ? getColorHex("G") : "#081a10"} style={{ filter: lights.N === "G" ? getGlow("G") : "none", transition: "all 0.4s" }} />
            <rect x="-10" y="4" width="20" height="13" rx="3" fill={lights.N === "G" ? "rgba(16,185,129,0.3)" : lights.N === "Y" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.25)"} style={{ transition: "fill 0.4s" }} />
            <text x="0" y="14" textAnchor="middle" fill="#e2e8f0" fontSize="9" fontWeight="800">N</text>
          </g>

          {/* South light */}
          <g transform="translate(-38, 90)">
            <rect x="-2" y="-20" width="4" height="20" fill="#334155" />
            <rect x="-13" y="-2" width="26" height="50" rx="6" fill="#0b0f19" stroke="#475569" strokeWidth="1.5" />
            <circle cx="0" cy="12" r="7" fill={lights.S === "R" ? getColorHex("R") : "#1a0808"} style={{ filter: lights.S === "R" ? getGlow("R") : "none", transition: "all 0.4s" }} />
            <circle cx="0" cy="29" r="7" fill={lights.S === "Y" ? getColorHex("Y") : "#1a1408"} style={{ filter: lights.S === "Y" ? getGlow("Y") : "none", transition: "all 0.4s" }} />
            <circle cx="0" cy="46" r="7" fill={lights.S === "G" ? getColorHex("G") : "#081a10"} style={{ filter: lights.S === "G" ? getGlow("G") : "none", transition: "all 0.4s" }} />
            <rect x="-10" y="-16" width="20" height="13" rx="3" fill={lights.S === "G" ? "rgba(16,185,129,0.3)" : lights.S === "Y" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.25)"} style={{ transition: "fill 0.4s" }} />
            <text x="0" y="-6" textAnchor="middle" fill="#e2e8f0" fontSize="9" fontWeight="800">S</text>
          </g>

          {/* East light */}
          <g transform="translate(90, 38)">
            <rect x="-20" y="-2" width="20" height="4" fill="#334155" />
            <rect x="-2" y="-13" width="50" height="26" rx="6" fill="#0b0f19" stroke="#475569" strokeWidth="1.5" />
            <circle cx="12" cy="0" r="7" fill={lights.E === "R" ? getColorHex("R") : "#1a0808"} style={{ filter: lights.E === "R" ? getGlow("R") : "none", transition: "all 0.4s" }} />
            <circle cx="29" cy="0" r="7" fill={lights.E === "Y" ? getColorHex("Y") : "#1a1408"} style={{ filter: lights.E === "Y" ? getGlow("Y") : "none", transition: "all 0.4s" }} />
            <circle cx="46" cy="0" r="7" fill={lights.E === "G" ? getColorHex("G") : "#081a10"} style={{ filter: lights.E === "G" ? getGlow("G") : "none", transition: "all 0.4s" }} />
            <rect x="-16" y="-10" width="13" height="20" rx="3" fill={lights.E === "G" ? "rgba(16,185,129,0.3)" : lights.E === "Y" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.25)"} style={{ transition: "fill 0.4s" }} />
            <text x="-9" y="4" textAnchor="middle" fill="#e2e8f0" fontSize="9" fontWeight="800">E</text>
          </g>

          {/* West light */}
          <g transform="translate(-90, -38)">
            <rect x="0" y="-2" width="20" height="4" fill="#334155" />
            <rect x="-50" y="-13" width="50" height="26" rx="6" fill="#0b0f19" stroke="#475569" strokeWidth="1.5" />
            <circle cx="-38" cy="0" r="7" fill={lights.W === "G" ? getColorHex("G") : "#081a10"} style={{ filter: lights.W === "G" ? getGlow("G") : "none", transition: "all 0.4s" }} />
            <circle cx="-21" cy="0" r="7" fill={lights.W === "Y" ? getColorHex("Y") : "#1a1408"} style={{ filter: lights.W === "Y" ? getGlow("Y") : "none", transition: "all 0.4s" }} />
            <circle cx="-4" cy="0" r="7" fill={lights.W === "R" ? getColorHex("R") : "#1a0808"} style={{ filter: lights.W === "R" ? getGlow("R") : "none", transition: "all 0.4s" }} />
            <rect x="4" y="-10" width="13" height="20" rx="3" fill={lights.W === "G" ? "rgba(16,185,129,0.3)" : lights.W === "Y" ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.25)"} style={{ transition: "fill 0.4s" }} />
            <text x="11" y="4" textAnchor="middle" fill="#e2e8f0" fontSize="9" fontWeight="800">W</text>
          </g>

          {/* ─── ANIMATED CARS ─── */}
          {cars.map(car => {
            const t = carTransform(car);
            if (car.isEmergency) {
              // High-visibility Emergency Ambulance
              const w = 15;
              const h = 32;
              return (
                <g key={car.id} transform={`translate(${t.x}, ${t.y}) rotate(${t.rot})`} style={{ transition: "none" }}>
                  {/* Siren pulse ring */}
                  <circle cx="0" cy="-6" r={strobeOn ? 24 : 14} fill="none" stroke="#ef4444" strokeWidth="1.5" opacity={strobeOn ? 0.6 : 0.15} />
                  {/* Drop shadow */}
                  <rect x={-w / 2 + 1} y={-h / 2 + 1} width={w} height={h} rx="4" fill="#000000" opacity="0.4" />
                  {/* Ambulance body */}
                  <rect x={-w / 2} y={-h / 2} width={w} height={h} rx="4" fill="#ffffff" stroke="#ef4444" strokeWidth="1.5" />
                  {/* Red cross on roof */}
                  <rect x="-4" y="-2" width="8" height="3" rx="0.5" fill="#ef4444" />
                  <rect x="-1.5" y="-4.5" width="3" height="8" rx="0.5" fill="#ef4444" />
                  {/* Windshield */}
                  <rect x={-w / 2 + 1.5} y={-h / 2 + 4} width={w - 3} height={3.5} rx="1" fill="#0284c7" opacity="0.75" />
                  {/* Strobe lights on roof bar */}
                  <circle cx={-3.5} cy={-h / 2 + 11} r={2.8} fill={strobeOn ? "#3b82f6" : "#1e3a8a"} style={{ filter: strobeOn ? "drop-shadow(0 0 10px #3b82f6)" : "none" }} />
                  <circle cx={3.5} cy={-h / 2 + 11} r={2.8} fill={!strobeOn ? "#ef4444" : "#7f1d1d"} style={{ filter: !strobeOn ? "drop-shadow(0 0 10px #ef4444)" : "none" }} />
                  {/* Label */}
                  {car.speed < 0.0003 && car.pos > 0.35 && car.pos < 0.45 ? (
                    <g transform="translate(0, 24)">
                      <rect x="-46" y="-8" width="92" height="15" rx="3" fill="rgba(15, 23, 42, 0.92)" stroke="#f59e0b" strokeWidth="1" />
                      <text x="0" y="2.5" textAnchor="middle" fill="#f59e0b" fontSize="7" fontWeight="800">WAITING FOR GREEN</text>
                    </g>
                  ) : (
                    <text x="0" y={h / 2 + 12} textAnchor="middle" fill="#38bdf8" fontSize="8" fontWeight="800" letterSpacing="0.8">AMBULANCE</text>
                  )}
                </g>
              );
            }

            // Normal civilian car: 13px wide across lane, 24px long along lane
            // Since rotate(${t.rot}) already turns the vehicle, no conditional swapping needed!
            const w = 13;
            const h = 24;
            return (
              <g key={car.id} transform={`translate(${t.x}, ${t.y}) rotate(${t.rot})`}>
                {/* Shadow */}
                <rect x={-w / 2 + 1} y={-h / 2 + 1} width={w} height={h} rx="3" fill="#000000" opacity="0.35" />
                {/* Body */}
                <rect x={-w / 2} y={-h / 2} width={w} height={h} rx="3" fill={car.color} opacity="0.9" />
                {/* Cabin roof */}
                <rect x={-w / 2 + 1.5} y={-h / 2 + 5} width={w - 3} height={h - 9} rx="2" fill="rgba(0, 0, 0, 0.4)" />
                {/* Front Windshield */}
                <rect x={-w / 2 + 2} y={-h / 2 + 5} width={w - 4} height={2.5} rx="1" fill="#38bdf8" opacity="0.65" />
                {/* Headlights (front) */}
                <circle cx={-w / 2 + 2} cy={-h / 2 + 1} r={1.2} fill="#fef08a" />
                <circle cx={w / 2 - 2} cy={-h / 2 + 1} r={1.2} fill="#fef08a" />
                {/* Rear Taillights */}
                <rect x={-w / 2 + 1.5} y={h / 2 - 1.5} width={2.5} height={1} rx="0.5" fill="#ef4444" opacity="0.9" />
                <rect x={w / 2 - 4} y={h / 2 - 1.5} width={2.5} height={1} rx="0.5" fill="#ef4444" opacity="0.9" />
              </g>
            );
          })}

          {/* Axis legend */}
          <g transform="translate(340, 360)">
            <rect x="-70" y="-28" width="140" height="56" rx="8" fill="rgba(11,15,25,0.9)" stroke="#334155" strokeWidth="1" />
            <text x="0" y="-14" textAnchor="middle" fill="#94a3b8" fontSize="8" fontWeight="700" letterSpacing="1">ACTIVE AXIS</text>
            <circle cx="-40" cy="6" r="6" fill={(lights.N === "G" || lights.N === "Y") ? "#10b981" : "#1e293b"} style={{ filter: (lights.N === "G" || lights.N === "Y") ? "drop-shadow(0 0 4px #10b981)" : "none", transition: "all 0.4s" }} />
            <text x="-24" y="10" fill="#e2e8f0" fontSize="10" fontWeight="600">N-S</text>
            <circle cx="16" cy="6" r="6" fill={(lights.E === "G" || lights.E === "Y") ? "#10b981" : "#1e293b"} style={{ filter: (lights.E === "G" || lights.E === "Y") ? "drop-shadow(0 0 4px #10b981)" : "none", transition: "all 0.4s" }} />
            <text x="32" y="10" fill="#e2e8f0" fontSize="10" fontWeight="600">E-W</text>
          </g>
        </svg>

        {/* Active Emergency / Preemption Banner */}
        {(() => {
          const activeEmergency = cars.find(c => c.isEmergency);
          if (!activeEmergency && mode !== "PRIORITY") return null;
          const eDir = activeEmergency?.dir || emergencyDirRef.current;
          const isGreen = lights[eDir] === "G";
          return (
            <div
              style={{
                marginTop: "14px",
                padding: "10px 18px",
                borderRadius: "10px",
                background: isGreen
                  ? "linear-gradient(90deg, rgba(16, 185, 129, 0.18), rgba(6, 78, 59, 0.35))"
                  : "linear-gradient(90deg, rgba(239, 68, 68, 0.18), rgba(127, 29, 29, 0.35))",
                border: isGreen ? "1px solid rgba(16, 185, 129, 0.5)" : "1px solid rgba(239, 68, 68, 0.5)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
                boxShadow: isGreen ? "0 0 16px rgba(16, 185, 129, 0.15)" : "0 0 16px rgba(239, 68, 68, 0.15)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{ fontSize: "1.3rem" }}>🚨</span>
                <div>
                  <div style={{ fontWeight: 800, fontSize: "0.85rem", color: isGreen ? "#34d399" : "#fca5a5" }}>
                    {isGreen ? "EMERGENCY GREEN WAVE ACTIVE" : "PREEMPTION CLEARANCE IN PROGRESS"}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {isGreen
                      ? `Approach ${eDir} granted exclusive green priority. Cross-traffic held.`
                      : `Opposing traffic light switching to RED. Ambulance holding safely at stop line.`}
                  </div>
                </div>
              </div>
              <span
                className="font-mono"
                style={{
                  padding: "4px 10px",
                  borderRadius: "6px",
                  background: isGreen ? "rgba(16, 185, 129, 0.25)" : "rgba(239, 68, 68, 0.25)",
                  fontWeight: 700,
                  fontSize: "0.75rem",
                  color: isGreen ? "#34d399" : "#fca5a5",
                  border: `1px solid ${isGreen ? "#10b981" : "#ef4444"}`,
                }}
              >
                APPROACH {eDir}: {isGreen ? "GREEN" : lights[eDir] === "Y" ? "YELLOW" : "RED"}
              </span>
            </div>
          );
        })()}

        {/* Current Phase Bar */}
        <div style={{ marginTop: "16px", display: "flex", alignItems: "center", gap: "12px", width: "100%", justifyContent: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Phase:</span>
          <span className="font-mono" style={{ background: "rgba(56, 189, 248, 0.15)", color: "#38bdf8", padding: "4px 12px", borderRadius: "8px", fontWeight: 600 }}>
            {phase}
          </span>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Elapsed:</span>
          <span className="font-mono" style={{ color: "#ffffff", fontWeight: 600 }}>
            {(state.phase_elapsed_ms / 1000).toFixed(1)}s
          </span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>
            {mode === "PRIORITY" && state.priority_approach
              ? `Priority: ${state.priority_approach} green only; all other approaches red`
              : mode === "PRIORITY"
                ? "Priority requested; completing safe clearance before granting green"
              : "Normal cycle: N+S share NS; E+W share EW"}
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
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Controller</div>
              <div style={{ fontWeight: 700, color: "#ffffff" }}>
                {state.controller_id || "unknown"}
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

        {/* Light Status Grid */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px" }}>Traffic Light States</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
            {(["N", "S", "E", "W"] as Dir[]).map(d => (
              <div key={d} className="glass-card" style={{ padding: "10px", display: "flex", alignItems: "center", gap: "10px" }}>
                <div style={{
                  width: 14, height: 14, borderRadius: "50%",
                  background: getColorHex(lights[d]),
                  filter: getGlow(lights[d]),
                  transition: "all 0.4s",
                }} />
                <div>
                  <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{d === "N" ? "North" : d === "S" ? "South" : d === "E" ? "East" : "West"}</div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {lights[d] === "G" ? "GREEN" : lights[d] === "Y" ? "YELLOW" : "RED"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Manual Override Controls */}
        <div className="glass-panel" style={{ padding: "20px" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
            <ShieldAlert size={18} color="#f59e0b" />
            <span>Manual Override (Operator)</span>
          </h3>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "16px" }}>
            Trigger priority directly or safely clear active hold.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "-4px" }}>
              Emergency Approach Direction:
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              <button
                id="btn-approach-n"
                className={`btn ${selectedApproach === "N" ? "btn-primary" : "btn-secondary"}`}
                style={{ justifyContent: "center", padding: "8px" }}
                onClick={() => {
                  setSelectedApproach("N");
                  setSelectedAxis("NS");
                  emergencyDirRef.current = "N";
                }}
              >
                ⬆ North (NS)
              </button>
              <button
                id="btn-approach-s"
                className={`btn ${selectedApproach === "S" ? "btn-primary" : "btn-secondary"}`}
                style={{ justifyContent: "center", padding: "8px" }}
                onClick={() => {
                  setSelectedApproach("S");
                  setSelectedAxis("NS");
                  emergencyDirRef.current = "S";
                }}
              >
                ⬇ South (NS)
              </button>
              <button
                id="btn-approach-e"
                className={`btn ${selectedApproach === "E" ? "btn-primary" : "btn-secondary"}`}
                style={{ justifyContent: "center", padding: "8px" }}
                onClick={() => {
                  setSelectedApproach("E");
                  setSelectedAxis("EW");
                  emergencyDirRef.current = "E";
                }}
              >
                ⬅ East (EW)
              </button>
              <button
                id="btn-approach-w"
                className={`btn ${selectedApproach === "W" ? "btn-primary" : "btn-secondary"}`}
                style={{ justifyContent: "center", padding: "8px" }}
                onClick={() => {
                  setSelectedApproach("W");
                  setSelectedAxis("EW");
                  emergencyDirRef.current = "W";
                }}
              >
                ➡ West (EW)
              </button>
            </div>

            <button
              id="btn-dispatch-emergency"
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              onClick={() => handleDispatchEmergency(selectedApproach, selectedAxis)}
            >
              <Siren size={16} />
              <span>
                Dispatch Emergency ({selectedApproach === "N" ? "North" : selectedApproach === "S" ? "South" : selectedApproach === "E" ? "East" : "West"})
              </span>
            </button>

            <button
              id="btn-clear-hold"
              className="btn btn-secondary"
              style={{ width: "100%", justifyContent: "center", padding: "10px" }}
              onClick={handleClearHold}
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
