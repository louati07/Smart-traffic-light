export type Phase =
  | "NS_GREEN"
  | "NS_YELLOW"
  | "ALL_RED_TO_EW"
  | "EW_GREEN"
  | "EW_YELLOW"
  | "ALL_RED_TO_NS";

export type Mode = "NORMAL" | "PRIORITY" | "FALLBACK";

export interface LightsState {
  N: "R" | "Y" | "G";
  E: "R" | "Y" | "G";
  S: "R" | "Y" | "G";
  W: "R" | "Y" | "G";
}

export interface IntersectionState {
  phase: Phase;
  mode: Mode;
  lights: LightsState;
  last_seq: number;
  phase_elapsed_ms: number;
  uptime_ms: number;
  rejected_cmds?: number;
}

export interface PriorityEvent {
  event_id: string;
  approach: "N" | "E" | "S" | "W";
  axis: "NS" | "EW";
  class: "ambulance" | "fire_truck" | "police_car" | "manual";
  started_at: string;
  released_at?: string | null;
  light_change_latency_ms?: number | null;
  outcome: "in_progress" | "completed" | "auto_released" | "manual_cleared";
}

export interface SecurityEvent {
  ts: string;
  source_ip: string;
  reason: string;
  endpoint: string;
  details: string;
}

export interface SimKPIs {
  ambulance_wait_s: number;
  ambulance_crossing_time_s: number;
  avg_other_delay_s: number;
  max_queue_len: number;
  extra_delay_others_s: number;
  recovery_time_s: number;
  total_vehicles_served: number;
}

export interface ReplayFrame {
  time_s: number;
  phase: string;
  mode: string;
  lights: Record<string, string>;
  queues: Record<string, number>;
  ambulance?: {
    approach: string;
    distance_m: number;
    speed_mps: number;
    status: string;
  } | null;
}

export interface SimRun {
  run_id: string;
  seed: number;
  scenario: string;
  created_at: string;
  baseline_kpis: SimKPIs;
  priority_kpis: SimKPIs;
  baseline_trace?: ReplayFrame[];
  priority_trace?: ReplayFrame[];
}

export interface KPISummary {
  total_runs: number;
  avg_ambulance_wait_baseline_s: number;
  avg_ambulance_wait_priority_s: number;
  avg_time_saved_s: number;
  avg_extra_delay_others_s: number;
  avg_recovery_time_s: number;
  pct_wait_reduction: number;
}
