import type { PipelineRunStage, RunFilters } from "../types";

export const PIPELINE_STAGES: PipelineRunStage[] = [
  "manifest",
  "profiling",
  "cleaning",
  "structuring",
  "modeling",
  "evaluation",
  "reporting",
  "memory",
];

export const HUMAN_REVIEW_POINTS: PipelineRunStage[] = [
  "modeling",
  "evaluation",
  "memory",
];

export const STAGE_LABELS: Record<PipelineRunStage, string> = {
  manifest: "Manifest",
  profiling: "Perfilado",
  cleaning: "Limpieza",
  structuring: "Estructura",
  modeling: "Modelado",
  evaluation: "Evaluacion",
  reporting: "Informe",
  memory: "Memoria",
};

export const RUN_STAGE_FILTERS = ["completed", "failed", "reporting", "evaluation", "modeling"];

export const DEFAULT_RUN_FILTERS: RunFilters = {
  dataset: null,
  current_stage: null,
  approved: null,
};
