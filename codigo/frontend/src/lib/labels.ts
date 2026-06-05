import type { LLMStatusResponse } from "../types";

export function llmStatusLabel(status: LLMStatusResponse | null): string {
  if (status === null) {
    return "-";
  }
  if (!status.available) {
    return "offline";
  }
  return status.model_available ? status.model : "sin modelo";
}

export function runStatusLabel(currentStage: string, approved: boolean | null): string {
  if (currentStage === "completed" && approved === null) {
    return "diagnostico";
  }
  return currentStage;
}
