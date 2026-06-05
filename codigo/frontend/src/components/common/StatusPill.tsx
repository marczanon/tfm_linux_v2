import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

export function StatusPill({
  ok,
  label,
  muted = false,
}: {
  ok: boolean;
  label: string;
  muted?: boolean;
}) {
  const Icon = ok ? CheckCircle2 : muted ? AlertTriangle : XCircle;
  return (
    <span className={`status-pill ${ok ? "ok" : ""} ${muted ? "muted" : ""}`}>
      <Icon size={14} />
      {label}
    </span>
  );
}
