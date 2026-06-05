import { FileSearch, Play } from "lucide-react";
import type { FormEvent } from "react";

import {
  HUMAN_REVIEW_POINTS,
  PIPELINE_STAGES,
  STAGE_LABELS,
} from "../../constants/pipeline";
import { emptyToNull } from "../../lib/forms";
import type {
  ApiRunRequest,
  DatasetAdapterInfo,
  HumanApproval,
  HumanReviewMode,
  LLMStatusResponse,
  PipelineRunStage,
} from "../../types";
import { PanelTitle } from "../common/PanelTitle";
import { StatusPill } from "../common/StatusPill";
import { LLMStatusPanel } from "../llm/LLMStatusPanel";

export function PipelineConfig({
  activeJob,
  adapters,
  approvalRequired,
  canExecutePlan,
  customStages,
  executing,
  humanReviewReasons,
  llmStatus,
  planning,
  request,
  selectedAdapter,
  selectedAdapterId,
  onApplyAdapter,
  onExecute,
  onRefreshLlm,
  onSubmitDryRun,
  onToggleCustomStages,
  onToggleHumanReviewPoint,
  onToggleStage,
  onUpdateHumanApproval,
  onUpdateHumanReviewMode,
  onUpdateHumanReviewer,
  onUpdateRequest,
}: {
  activeJob: boolean;
  adapters: DatasetAdapterInfo[];
  approvalRequired: boolean;
  canExecutePlan: boolean;
  customStages: boolean;
  executing: boolean;
  humanReviewReasons: string[];
  llmStatus: LLMStatusResponse | null;
  planning: boolean;
  request: ApiRunRequest;
  selectedAdapter: DatasetAdapterInfo;
  selectedAdapterId: string;
  onApplyAdapter: (adapterId: string) => void;
  onExecute: () => void;
  onRefreshLlm: () => void;
  onSubmitDryRun: (event: FormEvent<HTMLFormElement>) => void;
  onToggleCustomStages: (enabled: boolean) => void;
  onToggleHumanReviewPoint: (stage: PipelineRunStage) => void;
  onToggleStage: (stage: PipelineRunStage) => void;
  onUpdateHumanApproval: (update: Partial<HumanApproval>) => void;
  onUpdateHumanReviewMode: (mode: HumanReviewMode) => void;
  onUpdateHumanReviewer: (reviewer: string) => void;
  onUpdateRequest: <Key extends keyof ApiRunRequest>(
    key: Key,
    value: ApiRunRequest[Key],
  ) => void;
}) {
  return (
    <form className="panel config-panel" onSubmit={onSubmitDryRun}>
      <PanelTitle
        eyebrow="Configuracion"
        title="Nueva run"
        icon={<FileSearch size={19} />}
      />

      <div className="form-section">
        <label className="field">
          <span>Adaptador</span>
          <select
            value={selectedAdapterId}
            onChange={(event) => onApplyAdapter(event.target.value)}
          >
            {adapters.map((adapter) => (
              <option key={adapter.adapter_id} value={adapter.adapter_id}>
                {adapter.display_name}
              </option>
            ))}
          </select>
        </label>

        <div className="adapter-summary">
          <div>
            <span>Dataset</span>
            <strong>{selectedAdapter.dataset_id}</strong>
          </div>
          <div>
            <span>Formatos</span>
            <strong>{selectedAdapter.supported_source_formats.join(", ")}</strong>
          </div>
          <StatusPill
            ok={!selectedAdapter.is_experimental}
            label={selectedAdapter.is_experimental ? "experimental" : "estable"}
            muted={selectedAdapter.is_experimental}
          />
        </div>
      </div>

      <div className="form-section">
        <label className="field">
          <span>Run ID</span>
          <input
            value={request.run_id}
            onChange={(event) => onUpdateRequest("run_id", event.target.value)}
          />
        </label>
      </div>

      <div className="form-section form-grid">
        <label className="field">
          <span>Modo</span>
          <select
            value={request.execution_mode}
            onChange={(event) =>
              onUpdateRequest(
                "execution_mode",
                event.target.value as ApiRunRequest["execution_mode"],
              )
            }
          >
            <option value="full">Full</option>
            <option value="diagnostic">Diagnostic</option>
          </select>
        </label>

        <label className="field">
          <span>Human Review</span>
          <select
            value={request.human_review.mode}
            onChange={(event) =>
              onUpdateHumanReviewMode(event.target.value as HumanReviewMode)
            }
          >
            <option value="off">Off</option>
            <option value="passive">Passive</option>
            <option value="required">Required</option>
          </select>
        </label>
      </div>

      <HumanReviewControls
        request={request}
        reasons={humanReviewReasons}
        approvalRequired={approvalRequired}
        onReviewerChange={onUpdateHumanReviewer}
        onTogglePoint={onToggleHumanReviewPoint}
        onApprovalChange={onUpdateHumanApproval}
      />

      <div className="toggle-grid">
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.use_memory}
            onChange={(event) => onUpdateRequest("use_memory", event.target.checked)}
          />
          <span>Memoria local</span>
        </label>
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.use_llm}
            onChange={(event) => onUpdateRequest("use_llm", event.target.checked)}
          />
          <span>Agentes LLM</span>
        </label>
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.allow_synthetic_labels}
            onChange={(event) =>
              onUpdateRequest("allow_synthetic_labels", event.target.checked)
            }
          />
          <span>Etiquetas sinteticas</span>
        </label>
      </div>

      <LLMStatusPanel
        active={request.use_llm}
        status={llmStatus}
        onRefresh={onRefreshLlm}
      />

      <details className="advanced-options">
        <summary>Opciones avanzadas</summary>
        <div className="form-section form-grid">
          <label className="field">
            <span>Adapter ID</span>
            <input
              value={request.adapter_id ?? ""}
              onChange={(event) =>
                onUpdateRequest("adapter_id", emptyToNull(event.target.value))
              }
            />
          </label>
          <label className="field">
            <span>Policy ID</span>
            <input
              value={request.dataset_policy_id ?? ""}
              onChange={(event) =>
                onUpdateRequest("dataset_policy_id", emptyToNull(event.target.value))
              }
            />
          </label>
        </div>

        <section className="stage-section">
          <label className="switch-row">
            <input
              type="checkbox"
              checked={customStages}
              onChange={(event) => onToggleCustomStages(event.target.checked)}
            />
            <span>Fases manuales</span>
          </label>
          <div className="stage-grid" aria-disabled={!customStages}>
            {PIPELINE_STAGES.map((stage) => (
              <label className="stage-toggle" key={stage}>
                <input
                  type="checkbox"
                  checked={(request.requested_stages ?? []).includes(stage)}
                  onChange={() => onToggleStage(stage)}
                  disabled={!customStages}
                />
                <span>{STAGE_LABELS[stage]}</span>
              </label>
            ))}
          </div>
        </section>
      </details>

      <div className="action-bar">
        <button className="secondary-button" type="submit" disabled={planning || executing}>
          <FileSearch size={17} />
          {planning ? "Planificando" : "Planificar"}
        </button>
        <button
          className="primary-button"
          type="button"
          disabled={!canExecutePlan}
          onClick={onExecute}
        >
          <Play size={17} />
          {executing || activeJob ? "Ejecutando" : "Ejecutar"}
        </button>
      </div>
    </form>
  );
}

function HumanReviewControls({
  request,
  reasons,
  approvalRequired,
  onReviewerChange,
  onTogglePoint,
  onApprovalChange,
}: {
  request: ApiRunRequest;
  reasons: string[];
  approvalRequired: boolean;
  onReviewerChange: (reviewer: string) => void;
  onTogglePoint: (stage: PipelineRunStage) => void;
  onApprovalChange: (update: Partial<HumanApproval>) => void;
}) {
  if (request.human_review.mode === "off") {
    return null;
  }

  return (
    <section className="human-review-box">
      <div className="section-heading">
        <div>
          <h3>Revision humana</h3>
          <p>{request.human_review.mode}</p>
        </div>
        <StatusPill
          ok={!approvalRequired || request.human_approval?.approved === true}
          label={
            approvalRequired && request.human_approval?.approved !== true
              ? "pendiente"
              : "lista"
          }
          muted={!approvalRequired}
        />
      </div>

      <label className="field compact-field">
        <span>Revisor</span>
        <input
          value={request.human_review.reviewer ?? ""}
          onChange={(event) => onReviewerChange(event.target.value)}
        />
      </label>

      <div className="review-point-grid">
        {HUMAN_REVIEW_POINTS.map((stage) => (
          <label className="stage-toggle" key={stage}>
            <input
              type="checkbox"
              checked={request.human_review.required_decision_points.includes(stage)}
              onChange={() => onTogglePoint(stage)}
            />
            <span>{STAGE_LABELS[stage]}</span>
          </label>
        ))}
      </div>

      {reasons.length > 0 ? (
        <ul className="plain-list review-reasons">
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {request.human_review.mode === "required" && reasons.length > 0 ? (
        <div className="approval-form">
          <label className="switch-row">
            <input
              type="checkbox"
              checked={request.human_approval?.approved === true}
              onChange={(event) =>
                onApprovalChange({
                  approved: event.target.checked ? true : null,
                  reviewed_at: event.target.checked ? new Date().toISOString() : null,
                })
              }
            />
            <span>Aprobada</span>
          </label>
          <label className="field compact-field">
            <span>Motivo</span>
            <textarea
              value={request.human_approval?.reason ?? reasons.join("; ")}
              onChange={(event) => onApprovalChange({ reason: event.target.value })}
            />
          </label>
        </div>
      ) : null}
    </section>
  );
}
