export function formatMetric(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 3,
  }).format(value);
}

export function formatSeconds(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${formatMetric(value)} s`;
}

export function confidenceText(value: number | null): string {
  if (value === null) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatEventTime(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
