import {
  Brain,
  Database,
  FileSearch,
  Layers,
  Play,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";

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
  const llmReady =
    !request.use_llm ||
    (llmStatus?.available === true && llmStatus.model_available === true);
  const approvalReady =
    !approvalRequired || request.human_approval?.approved === true;
  const planLabel = planning
    ? "planificando"
    : activeJob || executing
      ? "en curso"
      : canExecutePlan
        ? "listo"
        : "pendiente";

  return (
    <form className="panel config-panel run-launcher" onSubmit={onSubmitDryRun}>
      <PanelTitle
        eyebrow="Nueva run"
        title="Preparar ejecucion"
        icon={<FileSearch size={19} />}
      />

      <fieldset
        className="launcher-controls"
        disabled={activeJob || executing || planning}
      >
      <div className="launcher-flow">
        <section className="launcher-step">
          <LauncherStepHeader index="1" icon={<Database size={17} />} title="Dataset" />
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
        </section>

        <section className="launcher-step">
          <LauncherStepHeader index="2" icon={<Layers size={17} />} title="Ejecucion" />
          <div className="launcher-mode-grid" role="group" aria-label="Modo de ejecucion">
            <ModeButton
              active={request.execution_mode === "full"}
              label="Full"
              onClick={() => onUpdateRequest("execution_mode", "full")}
            />
            <ModeButton
              active={request.execution_mode === "diagnostic"}
              label="Diagnostic"
              onClick={() => onUpdateRequest("execution_mode", "diagnostic")}
            />
          </div>

          <label className="field">
            <span>Run ID</span>
            <input
              value={request.run_id}
              onChange={(event) => onUpdateRequest("run_id", event.target.value)}
            />
          </label>
        </section>

        <section className="launcher-step">
          <LauncherStepHeader index="3" icon={<Brain size={17} />} title="Agentes" />
          <div className="launcher-toggle-grid">
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
                checked={request.use_memory}
                onChange={(event) => onUpdateRequest("use_memory", event.target.checked)}
              />
              <span>Memoria local</span>
            </label>
          </div>

          <LLMStatusPanel
            active={request.use_llm}
            status={llmStatus}
            onRefresh={onRefreshLlm}
          />

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

          <HumanReviewControls
            request={request}
            reasons={humanReviewReasons}
            approvalRequired={approvalRequired}
            onReviewerChange={onUpdateHumanReviewer}
            onTogglePoint={onToggleHumanReviewPoint}
            onApprovalChange={onUpdateHumanApproval}
          />
        </section>

        <section className="launcher-step">
          <LauncherStepHeader
            index="4"
            icon={<ShieldCheck size={17} />}
            title="Preflight"
          />
          <div className="launcher-readiness-grid">
            <ReadinessItem
              label="Plan"
              ok={canExecutePlan || activeJob || executing}
              muted={!canExecutePlan && !activeJob && !executing}
              value={planLabel}
            />
            <ReadinessItem
              label="LLM"
              ok={llmReady && request.use_llm}
              muted={!request.use_llm}
              value={
                request.use_llm
                  ? llmReady
                    ? "listo"
                    : "no disponible"
                  : "off"
              }
            />
            <ReadinessItem
              label="Review"
              ok={approvalReady}
              muted={!approvalRequired}
              value={approvalReady ? "lista" : "pendiente"}
            />
          </div>

          <div className="action-bar launcher-action-bar">
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
        </section>
      </div>

      <details className="advanced-options launcher-advanced-options">
        <summary>
          <SlidersHorizontal size={15} />
          Opciones avanzadas
        </summary>
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

        <label className="switch-row advanced-switch">
          <input
            type="checkbox"
            checked={request.allow_synthetic_labels}
            onChange={(event) =>
              onUpdateRequest("allow_synthetic_labels", event.target.checked)
            }
          />
          <span>Etiquetas sinteticas</span>
        </label>

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
      </fieldset>
    </form>
  );
}

function LauncherStepHeader({
  index,
  icon,
  title,
}: {
  index: string;
  icon: ReactNode;
  title: string;
}) {
  return (
    <div className="launcher-step-header">
      <span className="launcher-step-index">{index}</span>
      {icon}
      <h3>{title}</h3>
    </div>
  );
}

function ModeButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={`mode-button ${active ? "active" : ""}`}
      type="button"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function ReadinessItem({
  label,
  value,
  ok,
  muted,
}: {
  label: string;
  value: string;
  ok: boolean;
  muted: boolean;
}) {
  return (
    <div className="launcher-readiness-item">
      <span>{label}</span>
      <StatusPill ok={ok} muted={muted} label={value} />
    </div>
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
        <details className="compact-disclosure review-reasons-disclosure">
          <summary>Motivos · {reasons.length}</summary>
          <ul className="plain-list review-reasons">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
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
