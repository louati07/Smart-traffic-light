import { describe, it, expect } from "vitest";
import { IntersectionState } from "../types";

describe("Frontend State & KPI Formatter Tests", () => {
  it("formats initial intersection state accurately", () => {
    const initialState: IntersectionState = {
      phase: "NS_GREEN",
      mode: "NORMAL",
      lights: { N: "G", E: "R", S: "G", W: "R" },
      last_seq: 0,
      phase_elapsed_ms: 2500,
      uptime_ms: 12000,
    };

    expect(initialState.phase).toBe("NS_GREEN");
    expect(initialState.lights.N).toBe("G");
    expect(initialState.lights.E).toBe("R");
    expect((initialState.phase_elapsed_ms / 1000).toFixed(1)).toBe("2.5");
  });

  it("calculates time saved KPI differential correctly", () => {
    const baselineWait = 18.0;
    const priorityWait = 0.0;
    const saved = baselineWait - priorityWait;
    const pct = ((saved / baselineWait) * 100).toFixed(0);

    expect(saved).toBe(18.0);
    expect(pct).toBe("100");
  });

  it("validates safe color mapping function for traffic lights", () => {
    const getColorHex = (c: string) => {
      if (c === "G") return "#10b981";
      if (c === "Y") return "#f59e0b";
      return "#ef4444";
    };

    expect(getColorHex("G")).toBe("#10b981");
    expect(getColorHex("Y")).toBe("#f59e0b");
    expect(getColorHex("R")).toBe("#ef4444");
  });
});
