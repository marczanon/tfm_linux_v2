import type {
  MonitoringTriggerLifecycle,
  MonitoringTriggerType,
} from "../types";

export type AppView =
  | "cockpit"
  | "pipeline"
  | "monitoring"
  | "agents"
  | "visualization";

export type MonitoringReturnTab = "status" | "replay" | "events";

export interface MonitoringAgentBridgeContext {
  sessionId: string;
  executionCursorAtOpen: number | null;
  inspectionCursor: number | null;
  triggerId: string;
  triggerType: MonitoringTriggerType;
  triggerLifecycleAtOpen: MonitoringTriggerLifecycle;
  childRunId: string;
  assetId: string | null;
  snapshotId: string | null;
  returnTab: MonitoringReturnTab;
}
