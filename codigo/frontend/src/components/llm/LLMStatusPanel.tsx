import { Brain, RefreshCcw } from "lucide-react";

import type { LLMStatusResponse } from "../../types";
import { StatusPill } from "../common/StatusPill";

export function LLMStatusPanel({
  active,
  status,
  onRefresh,
}: {
  active: boolean;
  status: LLMStatusResponse | null;
  onRefresh: () => void;
}) {
  const ready = status?.available === true && status.model_available === true;
  return (
    <section className={`llm-box ${active ? "active" : ""}`}>
      <div>
        <div className="llm-box-title">
          <Brain size={16} />
          <strong>{status?.model ?? "qwen3.5:4b"}</strong>
          <StatusPill
            ok={ready}
            muted={!active}
            label={active ? (ready ? "listo" : "no disponible") : "inactivo"}
          />
        </div>
        <p>{status?.host ?? "http://127.0.0.1:11434"}</p>
        {status?.detail ? <small>{status.detail}</small> : null}
      </div>
      <button
        className="icon-button"
        type="button"
        onClick={onRefresh}
        title="Actualizar estado LLM"
        aria-label="Actualizar estado LLM"
      >
        <RefreshCcw size={16} />
      </button>
    </section>
  );
}
