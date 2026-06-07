import type {
  HealthState,
  RunVisualizationData,
  TemporalRunSeries,
  TemporalSeriesPoint,
} from "../types";

export const STATE_COLORS: Record<HealthState, { css: string; three: number }> = {
  nominal: { css: "#0f766e", three: 0x0f766e },
  watch: { css: "#2563eb", three: 0x2563eb },
  warning: { css: "#d97706", three: 0xd97706 },
  critical: { css: "#dc2626", three: 0xdc2626 },
};

const MARKER_COLORS: Record<IndustrialTimelineMarker["kind"], number> = {
  failure: 0x991b1b,
  first_alert: 0x2563eb,
  persistent_alert: 0xd97706,
};

const TIMELINE_X_MIN = -3.15;
const TIMELINE_X_MAX = 3.15;
const TIMELINE_Z = 1.42;
const MAX_TIMELINE_POINTS = 180;

export interface IndustrialSceneState {
  cssColor: string;
  dataset: string;
  health: number | null;
  healthState: HealthState;
  modelName: string;
  points: number;
  risk: number | null;
  threeColor: number;
}

export interface IndustrialTimelinePoint {
  health: number | null;
  height: number;
  id: string;
  label: string | null;
  risk: number | null;
  score: number;
  state: HealthState;
  stateReason: string;
  temporalX: number;
  threeColor: number;
  timeToFailureSeconds: number | null;
  timestampStart: string | null;
  windowId: string;
  x: number;
  z: number;
}

export interface IndustrialTimelineMarker {
  color: number;
  kind: "failure" | "first_alert" | "persistent_alert";
  label: string;
  temporalX: number;
  timeToFailureSeconds: number | null;
  x: number;
  z: number;
}

export type IndustrialSceneSelection =
  | {
      health: number | null;
      id: string;
      kind: "point";
      label: string | null;
      risk: number | null;
      score: number;
      state: HealthState;
      stateReason: string;
      temporalX: number;
      timeToFailureSeconds: number | null;
      timestampStart: string | null;
      windowId: string;
    }
  | {
      id: string;
      kind: "marker";
      markerKind: IndustrialTimelineMarker["kind"];
      markerLabel: string;
      temporalX: number;
      timeToFailureSeconds: number | null;
    };

export interface IndustrialTimelineModel {
  domain: { max: number; min: number };
  markers: IndustrialTimelineMarker[];
  points: IndustrialTimelinePoint[];
  totalPoints: number;
  visiblePoints: number;
}

export function buildIndustrialSceneState(
  data: RunVisualizationData,
  run: TemporalRunSeries,
): IndustrialSceneState {
  const healthState = run.current_health_state;
  const colors = STATE_COLORS[healthState];
  return {
    cssColor: colors.css,
    dataset: data.dataset,
    health: run.current_health_index,
    healthState,
    modelName: data.model_name ?? "modelo",
    points: run.n_points_sampled,
    risk: run.current_risk_index,
    threeColor: colors.three,
  };
}

export function buildIndustrialTimeline(run: TemporalRunSeries): IndustrialTimelineModel {
  const domain = temporalDomain(run);
  const sampledPoints = sampleTimelinePoints(run.points);
  const points = sampledPoints.map((point) => ({
    health: point.health_index,
    height: riskHeight(point),
    id: point.window_id,
    label: point.label,
    risk: point.risk_index,
    score: point.anomaly_score,
    state: point.health_state,
    stateReason: point.state_reason,
    temporalX: point.x,
    threeColor: STATE_COLORS[point.health_state].three,
    timeToFailureSeconds: point.time_to_failure_seconds,
    timestampStart: point.timestamp_start,
    windowId: point.window_id,
    x: timelineX(point.x, domain),
    z: TIMELINE_Z,
  }));

  return {
    domain,
    markers: markerSpecs(run, domain),
    points,
    totalPoints: run.n_points_total,
    visiblePoints: points.length,
  };
}

export function healthStateSceneLabel(state: HealthState): string {
  const labels: Record<HealthState, string> = {
    nominal: "nominal",
    watch: "vigilancia",
    warning: "alerta",
    critical: "critico",
  };
  return labels[state];
}

export function supportsWebGL(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return false;
  }

  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")),
    );
  } catch {
    return false;
  }
}

function sampleTimelinePoints(points: TemporalSeriesPoint[]): TemporalSeriesPoint[] {
  if (points.length <= MAX_TIMELINE_POINTS) {
    return points;
  }

  const step = Math.ceil(points.length / MAX_TIMELINE_POINTS);
  return points.filter((_, index) => index % step === 0);
}

function riskHeight(point: TemporalSeriesPoint): number {
  if (point.risk_index !== null) {
    return 0.08 + Math.max(0, Math.min(100, point.risk_index)) / 100 * 1.15;
  }

  if (point.score_ratio !== null) {
    return 0.08 + Math.max(0, Math.min(8, point.score_ratio)) / 8 * 1.15;
  }

  return 0.16;
}

function markerSpecs(
  run: TemporalRunSeries,
  domain: { max: number; min: number },
): IndustrialTimelineMarker[] {
  const markers: Array<IndustrialTimelineMarker | null> = [
    run.first_alert_x === null
      ? null
      : {
          color: MARKER_COLORS.first_alert,
          kind: "first_alert" as const,
          label: "primer pico",
          temporalX: run.first_alert_x,
          timeToFailureSeconds: run.first_alert_time_to_failure_seconds,
          x: timelineX(run.first_alert_x, domain),
          z: TIMELINE_Z - 0.42,
        },
    run.first_persistent_alert_x === null
      ? null
      : {
          color: MARKER_COLORS.persistent_alert,
          kind: "persistent_alert" as const,
          label: "aviso sostenido",
          temporalX: run.first_persistent_alert_x,
          timeToFailureSeconds: run.first_persistent_alert_time_to_failure_seconds,
          x: timelineX(run.first_persistent_alert_x, domain),
          z: TIMELINE_Z - 0.22,
        },
    run.failure_x === null
      ? null
      : {
          color: MARKER_COLORS.failure,
          kind: "failure" as const,
          label: "fallo",
          temporalX: run.failure_x,
          timeToFailureSeconds: null,
          x: timelineX(run.failure_x, domain),
          z: TIMELINE_Z,
        },
  ];
  return markers.filter((marker): marker is IndustrialTimelineMarker => marker !== null);
}

function temporalDomain(run: TemporalRunSeries): { max: number; min: number } {
  const values = [
    ...run.points.map((point) => point.x),
    ...(run.first_alert_x !== null ? [run.first_alert_x] : []),
    ...(run.first_persistent_alert_x !== null ? [run.first_persistent_alert_x] : []),
    ...(run.failure_x !== null ? [run.failure_x] : []),
  ];
  if (values.length === 0) {
    return { max: 1, min: 0 };
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  return min === max ? { max: max + 0.5, min: min - 0.5 } : { max, min };
}

function timelineX(value: number, domain: { max: number; min: number }): number {
  const ratio = (value - domain.min) / (domain.max - domain.min);
  return TIMELINE_X_MIN + Math.max(0, Math.min(1, ratio)) * (TIMELINE_X_MAX - TIMELINE_X_MIN);
}
