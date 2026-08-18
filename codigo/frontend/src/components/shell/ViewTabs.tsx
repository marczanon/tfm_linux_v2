import { Activity, BarChart3, LayoutDashboard, MonitorPlay, Users } from "lucide-react";

import type { AppView } from "../../types/ui";

export function ViewTabs({
  activeView,
  onChange,
}: {
  activeView: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-tabs" aria-label="Vistas principales">
      <button
        aria-current={activeView === "cockpit" ? "page" : undefined}
        className={activeView === "cockpit" ? "active" : ""}
        type="button"
        onClick={() => onChange("cockpit")}
      >
        <LayoutDashboard size={16} />
        Inicio
      </button>
      <button
        aria-current={activeView === "pipeline" ? "page" : undefined}
        className={activeView === "pipeline" ? "active" : ""}
        type="button"
        onClick={() => onChange("pipeline")}
      >
        <Activity size={16} />
        Nueva run
      </button>
      <button
        aria-current={activeView === "monitoring" ? "page" : undefined}
        className={activeView === "monitoring" ? "active" : ""}
        type="button"
        onClick={() => onChange("monitoring")}
      >
        <MonitorPlay size={16} />
        Monitorización
      </button>
      <button
        aria-current={activeView === "agents" ? "page" : undefined}
        className={activeView === "agents" ? "active" : ""}
        type="button"
        onClick={() => onChange("agents")}
      >
        <Users size={16} />
        Agentes
      </button>
      <button
        aria-current={activeView === "visualization" ? "page" : undefined}
        className={activeView === "visualization" ? "active" : ""}
        type="button"
        onClick={() => onChange("visualization")}
      >
        <BarChart3 size={16} />
        Resultados
      </button>
    </nav>
  );
}
