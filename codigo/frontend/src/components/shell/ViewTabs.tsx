import { Activity, BarChart3, Users } from "lucide-react";

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
        className={activeView === "pipeline" ? "active" : ""}
        type="button"
        onClick={() => onChange("pipeline")}
      >
        <Activity size={16} />
        Pipeline
      </button>
      <button
        className={activeView === "agents" ? "active" : ""}
        type="button"
        onClick={() => onChange("agents")}
      >
        <Users size={16} />
        Agentes
      </button>
      <button
        className={activeView === "visualization" ? "active" : ""}
        type="button"
        onClick={() => onChange("visualization")}
      >
        <BarChart3 size={16} />
        Visualizacion
      </button>
    </nav>
  );
}
