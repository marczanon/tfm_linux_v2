import { RefreshCcw } from "lucide-react";

export function StatusHeader({
  loading,
  onRefresh,
}: {
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <header className="status-header">
      <div>
        <p className="eyebrow">Industrial Agentic Cockpit</p>
        <h2>Control de anomalias</h2>
      </div>
      <button
        className="secondary-button"
        type="button"
        onClick={onRefresh}
        disabled={loading}
      >
        <RefreshCcw size={17} />
        Actualizar
      </button>
    </header>
  );
}
