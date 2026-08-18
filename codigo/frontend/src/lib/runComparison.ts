import { formatMetric, formatSeconds } from "./formatters";

export function metricLabel(metric: string): string {
  const labels: Record<string, string> = {
    precision: "Precision",
    recall: "Recall",
    f1_score: "F1",
    false_positive_rate: "FPR",
    degradation_persistent_alert_run_rate: "Alerta persistente por trayectoria",
    degradation_mean_first_persistent_alert_time_to_trajectory_end: "Intervalo al final registrado",
    degradation_mean_pre_monitoring_alert_rate: "Alertas premonitorizacion",
    degradation_detected_before_failure_rate: "Deteccion antes de fallo",
    degradation_mean_lead_time_to_failure: "Lead time medio",
    degradation_mean_false_alarm_rate_nominal: "FAR nominal medio",
    degradation_mean_score_trend_spearman: "Tendencia score",
    degradation_missed_runs: "Fallos perdidos",
    degradation_mean_initial_final_separation: "Separacion inicio-final",
  };
  return labels[metric] ?? metric;
}

export function formatComparisonMetric(metric: string, value: number | null): string {
  if (metric.includes("lead_time") || metric.includes("time_to_trajectory_end")) {
    return formatSeconds(value);
  }
  return formatMetric(value);
}
