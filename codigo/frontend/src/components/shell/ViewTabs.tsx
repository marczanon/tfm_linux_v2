import { Activity, BarChart3, LayoutDashboard, Users } from "lucide-react";

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
        className={activeView === "cockpit" ? "active" : ""}
        type="button"
        onClick={() => onChange("cockpit")}
      >
        <LayoutDashboard size={16} />
        Cockpit
      </button>
      <button
        className={activeView === "pipeline" ? "active" : ""}
        type="button"
        onClick={() => onChange("pipeline")}
      >
        <Activity size={16} />
        Nueva run
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
        Visual
      </button>
    </nav>
  );
}
