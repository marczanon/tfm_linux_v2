import type { AgentMemoryTarget, MemoryRecordSummary } from "../types";

export function memoryTargetForAgent(agentId: string): AgentMemoryTarget {
  if (
    agentId === "cleaner" ||
    agentId === "structurer" ||
    agentId === "modeler" ||
    agentId === "evaluator" ||
    agentId === "report_writer"
  ) {
    return agentId;
  }
  return "shared_methodology";
}

export function roleLabel(role: string): string {
  const labels: Record<string, string> = {
    positive_example: "positivo",
    negative_example: "negativo",
    boundary_case: "frontera",
    warning: "advertencia",
    methodology: "metodologia",
    evidence: "evidencia",
    excluded: "excluido",
  };
  return labels[role] ?? role;
}

export function sourceTypeLabel(sourceType: string): string {
  const labels: Record<string, string> = {
    decision_episode: "episodio",
    memory_candidate: "candidato",
    reasoning_postmortem: "post-mortem",
    human_review: "revision humana",
    memory_usage_audit: "auditoria",
    experiment_summary: "experimento",
    technical_documentation: "documentacion",
    methodology_note: "metodologia",
  };
  return labels[sourceType] ?? sourceType;
}

export function outcomeLabel(outcome: string | null): string {
  const labels: Record<string, string> = {
    validated: "validado",
    supported: "soportado",
    partially_supported: "parcial",
    overcorrected: "sobrecorregido",
    contradicted: "contradicho",
    inconclusive: "inconcluso",
  };
  return outcome === null ? "-" : labels[outcome] ?? outcome;
}

export function verdictLabel(verdict: string | null): string {
  const labels: Record<string, string> = {
    correct: "correcto",
    partially_correct: "parcial",
    incorrect: "incorrecto",
    unsafe: "inseguro",
    needs_more_evidence: "mas evidencia",
  };
  return verdict === null ? "sin veredicto" : labels[verdict] ?? verdict;
}

export function recordStateLabel(record: MemoryRecordSummary): string {
  if (record.exclude_from_context || record.memory_role === "excluded") {
    return "excluido";
  }
  if (record.reusable_as_context) {
    return "habilitado en indice";
  }
  return "indexado";
}
