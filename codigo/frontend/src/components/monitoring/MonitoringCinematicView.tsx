import { Activity, Gauge, Radio, ShieldCheck, Waves } from "lucide-react";
import { useMemo, useState } from "react";

import {
  buildMonitoringCinematicModel,
  type MonitoringCinematicAct,
  type MonitoringCinematicAgentCell,
  type MonitoringCinematicBearing,
  type MonitoringCinematicTelemetryPoint,
  type MonitoringCinematicTrendPoint,
} from "../../lib/monitoringCinematic";
import type {
  AgentRuntimeEvent,
  HealthState,
  MonitoringEvidenceCampaignView,
  MonitoringTriggerEvent,
  ReplayAssetSpec,
  ReplayTick,
} from "../../types";
import { healthStateLabel, triggerTypeLabel } from "./MonitoringReplayChart";

type CinematicBeatKind =
  | "tick"
  | "trigger"
  | "agent_decision"
  | "policy_proposal"
  | "final_verdict";

interface InjectedCinematicAsset {
  analysis_status: "modeled" | "telemetry_only" | "unavailable";
  asset_id: string;
  asset_label: string;
  channel_id: string;
  gap_detected: boolean;
  health_index: number | null;
  health_state: HealthState | null;
  health_state_label: string | null;
  risk_index: number | null;
  score: number | null;
  score_ratio: number | null;
  signal_peak_abs: number | null;
  signal_rms: number | null;
  threshold: number | null;
}

interface InjectedCinematicDecision {
  action_label: string;
  agent_name: string;
  confidence: number;
  evidence_handles: string[];
  expected_observation: string;
  falsification_criterion: string;
  generation_origin: string;
  generation_validation_status: string;
  hypothesis: string;
  recommended_action: string;
  role_label: string;
}

interface InjectedCinematicBeat {
  beat_index: number;
  campaign_id: string;
  child_run_id: string | null;
  cursor: number;
  decision_id: string | null;
  display_projection: {
    assets: InjectedCinematicAsset[];
    cursor: number;
    decision: InjectedCinematicDecision | null;
    phase: "pre_roll" | "agentic_window" | "closing";
    proposal: {
      action_counts: Record<string, number>;
      aggregate_action: string | null;
      agreement_label: string;
      agreement_status: string;
      application_status: "not_applied";
      human_review_recommended: boolean;
      status: string;
    } | null;
    source_time: string;
    subtitle: string;
    title: string;
    trigger: {
      cutoff_cursor: number;
      ordinal: 1 | 2 | 3 | 4;
      summary: string;
      trigger_type: string;
      trigger_type_label: string;
    } | null;
    verdict: {
      agentic: "passed" | "blocked";
      blockers: string[];
      evidence: "passed" | "blocked";
      operational: "passed" | "blocked";
    } | null;
  };
  duration_frames: number;
  event_id: string | null;
  kind: CinematicBeatKind;
  session_id: string;
  source_time: string;
  wall_time: string | null;
}

declare global {
  interface Window {
    __TFM_MONITORING_CINEMATIC_TIMELINE__?: InjectedCinematicBeat[];
  }
}

export function MonitoringCinematicView({
  assetSpecs,
  campaign,
  executionCursor,
  inspectionCursor,
  onInspect,
  onSelectTrigger,
  runEventsByChildId,
  ticks,
  triggers,
}: {
  assetSpecs: ReplayAssetSpec[];
  campaign: MonitoringEvidenceCampaignView | null;
  executionCursor: number | null;
  inspectionCursor: number | null;
  onInspect: (cursor: number) => void;
  onSelectTrigger: (trigger: MonitoringTriggerEvent) => void;
  runEventsByChildId: Record<string, AgentRuntimeEvent[]>;
  ticks: ReplayTick[];
  triggers: MonitoringTriggerEvent[];
}) {
  const injectedTimeline = useMemo(readInjectedTimeline, []);
  const [beatIndex, setBeatIndex] = useState(0);
  const beat = injectedTimeline?.[beatIndex] ?? null;
  const effectiveCursor = beat?.cursor ?? inspectionCursor;
  const model = useMemo(
    () => buildMonitoringCinematicModel({
      assetSpecs,
      campaign,
      inspectionCursor: effectiveCursor,
      runEventsByChildId: beat ? {} : runEventsByChildId,
      ticks,
      triggers,
    }),
    [assetSpecs, campaign, effectiveCursor, runEventsByChildId, ticks, triggers],
  );
  const bearings = beat
    ? beat.display_projection.assets.map(projectInjectedBearing)
    : model.bearings;
  const decision = beat?.display_projection.decision ?? null;
  const latestDecisionAtProposal = beat?.kind === "policy_proposal"
    ? [...(injectedTimeline?.slice(0, beatIndex + 1) ?? [])]
        .reverse()
        .find((item) => item.kind === "agent_decision" && item.cursor === beat.cursor)
        ?.display_projection.decision ?? null
    : null;
  const proposal = beat?.display_projection.proposal ?? null;
  const sourceTime = beat?.display_projection.source_time ?? model.currentSourceTime;
  const phase = beat?.display_projection.phase ?? model.phase;
  const isPreflight = Boolean(
    campaign?.campaign_id.includes("e2e") || beat?.campaign_id.includes("fixture"),
  );
  const latestModeled = bearings.find((bearing) => bearing.analysisStatus === "modeled") ?? null;

  return (
    <section className="monitoring-cinematic-shell" aria-labelledby="monitoring-cinematic-title">
      <div
        className="monitoring-cinematic-stage"
        data-beat-index={beat ? beatIndex : undefined}
        data-testid="monitoring-cinematic-stage"
      >
        <header className="monitoring-cinematic-header">
          <div>
            <span className="monitoring-cinematic-live">
              <Radio size={13} />{beat ? "reconstrucción auditable" : "observación causal"}
            </span>
            <h3 id="monitoring-cinematic-title">
              {beat?.display_projection.title ?? "Evolución del sistema de rodamientos"}
            </h3>
            <p>{beat?.display_projection.subtitle ?? stateNarrative(latestModeled)}</p>
          </div>
          <dl className="monitoring-cinematic-clocks">
            <div><dt>Tiempo NASA</dt><dd>{sourceTime ? sourceTime.replace("T", " ") : "Sin iniciar"}</dd></div>
            <div><dt>Cursor</dt><dd>{model.visibleCursor === null ? "—" : `${model.visibleCursor + 1}/689`}</dd></div>
            <div><dt>Fase</dt><dd>{phaseLabel(phase)}</dd></div>
            <div><dt>Pared real</dt><dd>{beat ? wallTimeLabel(beat.wall_time) : formatElapsed(campaign?.runtime_elapsed_seconds ?? 0)}</dd></div>
          </dl>
          <div className="monitoring-cinematic-badges">
            {isPreflight ? <strong>FIXTURE · PREFLIGHT</strong> : null}
            <span>Histórico · zona no declarada</span>
            <span>E## = selección; no confirmación causal</span>
          </div>
        </header>

        <div className="monitoring-cinematic-main">
          <section
            aria-label="Esquema de los cuatro rodamientos"
            className="monitoring-cinematic-rig"
            data-testid="monitoring-bearing-rig"
          >
            <div className="monitoring-cinematic-section-heading">
              <span><Gauge size={15} />Estado y telemetría observados</span>
              <small>Esquema, no gemelo digital</small>
            </div>
            <BearingRig bearings={bearings} />
            <div className="monitoring-bearing-readings" data-testid="monitoring-bearing-telemetry">
              {bearings.map((bearing) => (
                <article className={`analysis-${bearing.analysisStatus}`} key={bearing.assetId}>
                  <span>{bearing.label}</span>
                  <strong>{bearingHeadline(bearing)}</strong>
                  <small>{bearingReading(bearing)}</small>
                  <TelemetrySparkline
                    points={model.telemetrySeriesByAssetId[bearing.assetId] ?? []}
                  />
                </article>
              ))}
            </div>
            <small className="monitoring-bearing-scale-note">
              Tendencia RMS · escala propia por canal · unidad de fuente no declarada
            </small>
          </section>

          <section
            aria-label="Acto agéntico de la campaña"
            className="monitoring-cinematic-agent-act"
            data-testid="monitoring-agent-act"
          >
            <div className="monitoring-cinematic-section-heading">
              <span><Activity size={15} />Hipótesis y decisiones</span>
              <small>Declaraciones de agentes, no diagnóstico físico</small>
            </div>
            <CampaignStoryboard
              acts={model.storyboard}
              injectedPrefix={beat ? injectedTimeline!.slice(0, beatIndex + 1) : null}
            />
            <HypothesisPanel
              agent={beat ? null : model.activeAgent}
              decision={decision ?? latestDecisionAtProposal}
              review={model.activeAct}
            />
            <ProposalBanner
              injected={proposal}
              review={model.activeAct}
              verdict={beat?.display_projection.verdict ?? null}
            />
          </section>
        </div>

        <div className="monitoring-cinematic-bottom">
          <HealthRiskChart points={model.healthRiskSeries} />
          <ScoreRatioChart points={model.scoreRatioSeries} />
          <CausalActRail
            acts={model.storyboard}
            executionCursor={executionCursor}
            healthPoints={model.healthRiskSeries}
            onInspect={onInspect}
            onSelectTrigger={onSelectTrigger}
            triggers={model.visibleTriggers}
          />
        </div>
      </div>

      {injectedTimeline ? (
        <label className="monitoring-cinematic-capture-scrubber">
          <span>Acto exacto para captura</span>
          <input
            aria-label="Seleccionar acto de la cinemática"
            max={injectedTimeline.length - 1}
            min={0}
            onChange={(event) => setBeatIndex(Number(event.target.value))}
            step={1}
            type="range"
            value={beatIndex}
          />
          <strong>{beatIndex + 1}/{injectedTimeline.length}</strong>
        </label>
      ) : null}

      <p className="monitoring-cinematic-method-note">
        El índice de salud y el riesgo son indicadores del motor analítico, no porcentajes
        de daño. La confianza es declarada y no está calibrada como probabilidad. E## identifica
        registros seleccionados; no confirma soporte, causalidad ni verdad física.
      </p>
    </section>
  );
}

function BearingRig({ bearings }: { bearings: MonitoringCinematicBearing[] }) {
  return (
    <svg
      aria-label="Eje con cuatro puntos de medida; solo el rodamiento B1 tiene estado algorítmico"
      className="monitoring-bearing-rig-svg"
      role="img"
      viewBox="0 0 560 180"
    >
      <rect className="rig-base" height="19" rx="7" width="500" x="30" y="144" />
      <line className="rig-shaft" x1="58" x2="502" y1="82" y2="82" />
      <circle className="rig-rotor" cx="280" cy="82" r="37" />
      {bearings.map((bearing, index) => {
        const x = 95 + index * 123;
        return (
          <g
            className={`rig-bearing analysis-${bearing.analysisStatus}${bearing.healthState ? ` state-${bearing.healthState}` : ""}`}
            key={bearing.assetId}
            transform={`translate(${x} 82)`}
          >
            <circle className="rig-bearing-halo" r="30" />
            <circle className="rig-bearing-ring" r="21" />
            <circle className="rig-bearing-core" r="8" />
            <text textAnchor="middle" y="-40">{bearing.label}</text>
            <text className="rig-bearing-mode" textAnchor="middle" y="48">
              {bearing.analysisStatus === "modeled" ? "estado algorítmico" : "telemetría"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function CampaignStoryboard({
  acts,
  injectedPrefix,
}: {
  acts: MonitoringCinematicAct[];
  injectedPrefix: InjectedCinematicBeat[] | null;
}) {
  return (
    <div aria-label="Storyboard de cuatro revisiones por siete agentes" className="monitoring-agent-storyboard" data-testid="monitoring-evidence-heatmap">
      {acts.map((act) => {
        const injectedDecisions = injectedPrefix?.filter(
          (beat) => beat.kind === "agent_decision" && beat.cursor === act.cutoffCursor,
        ) ?? [];
        const injectedLifecycle = injectedPrefix
          ? injectedActLifecycle(injectedPrefix, act)
          : act.lifecycle;
        return (
          <article className={`lifecycle-${injectedLifecycle}`} data-lifecycle={injectedLifecycle} key={act.ordinal}>
            <header><span>Acto {act.ordinal}</span><strong>{shortTriggerLabel(act.triggerType)}</strong></header>
            <div
              aria-label={`${injectedPrefix ? injectedDecisions.length : act.agents.filter((agent) => agent.state !== "pending").length} de 7 agentes`}
              role="list"
            >
              {act.agents.map((agent) => {
                const injected = injectedDecisions.find(
                  (beat) => beat.display_projection.decision?.agent_name === agent.agentId,
                );
                const injectedDecision = injected?.display_projection.decision ?? null;
                const state = injectedDecision
                  ? injectedAgentState(injectedDecision)
                  : agent.state;
                const action = injectedDecision?.recommended_action ?? agent.recommendedAction;
                const evidence = injectedDecision?.evidence_handles ?? agent.evidenceHandles;
                const origin = injectedDecision?.generation_origin ?? agent.generationOrigin;
                return (
                  <span
                    aria-label={`${agent.agentLabel}; ${agentStateLabel(state)}; ${humanizeAction(action) || "sin acción"}; ${evidence.length ? `evidencia ${evidence.join(", ")}` : "sin evidencia E##"}`}
                    className={`monitoring-agent-heat-cell state-${state}`}
                    data-action={action ?? "pending"}
                    data-origin={origin ?? "pending"}
                    key={agent.agentId}
                    role="listitem"
                    title={`${agent.agentLabel}: ${agentStateLabel(state)} · ${humanizeAction(action)} · ${evidence.join(", ") || "sin E##"}`}
                  >
                    <i aria-hidden="true" />
                    <b>{evidence.length ? evidence.join("·") : "—"}</b>
                    <em>{actionGlyph(action)}</em>
                  </span>
                );
              })}
            </div>
            <small>cursor {act.cutoffCursor}</small>
          </article>
        );
      })}
    </div>
  );
}

function HypothesisPanel({
  agent,
  decision,
  review,
}: {
  agent: MonitoringCinematicAgentCell | null;
  decision: InjectedCinematicDecision | null;
  review: MonitoringCinematicAct | null;
}) {
  const name = decision?.role_label ?? agent?.agentLabel ?? null;
  const hypothesis = decision?.hypothesis ?? agent?.hypothesis ?? null;
  const expected = decision?.expected_observation ?? agent?.expectedObservation ?? null;
  const refutation = decision?.falsification_criterion ?? agent?.falsificationCriterion ?? null;
  const action = decision?.action_label ?? humanizeAction(agent?.recommendedAction ?? null);
  const confidence = decision?.confidence ?? agent?.confidence ?? null;
  const evidence = decision?.evidence_handles ?? agent?.evidenceHandles ?? [];
  if (!hypothesis) {
    return (
      <div className="monitoring-cinematic-thinking" data-testid="monitoring-hypothesis">
        <Waves size={17} />
        <span>
          <strong>{review?.lifecycle === "running" ? "Revisión en análisis" : "Sin hipótesis revelada"}</strong>
          <small>{review?.lifecycle === "running" ? "No se infiere actividad interna de Qwen." : "Aparecerá tras una decisión persistida."}</small>
        </span>
      </div>
    );
  }
  return (
    <article className="monitoring-cinematic-hypothesis" data-testid="monitoring-hypothesis">
      <header><span>{name}</span><strong>{action || "Acción no declarada"}</strong></header>
      <p>{hypothesis}</p>
      <div>
        <span><b>Esperaría</b>{expected || "No consta"}</span>
        <span><b>Se refutaría si</b>{refutation || "No consta"}</span>
      </div>
      <footer>
        <span>{confidence === null ? "Confianza no declarada" : `${Math.round(confidence * 100)}% confianza declarada`}</span>
        <span>{evidence.length ? `Acto ${review?.ordinal ?? "—"} · catálogo ${evidence.join(" · ")}` : "Sin handles E## declarados"}</span>
      </footer>
      <small className="monitoring-cinematic-grounding-limit">
        E## identifica registros seleccionados; no confirma soporte, causalidad ni verdad física.
      </small>
    </article>
  );
}

function ProposalBanner({
  injected,
  review,
  verdict,
}: {
  injected: InjectedCinematicBeat["display_projection"]["proposal"];
  review: MonitoringCinematicAct | null;
  verdict: InjectedCinematicBeat["display_projection"]["verdict"];
}) {
  if (verdict) {
    return (
      <div className={`monitoring-cinematic-proposal verdict-${verdict.evidence}`}>
        <ShieldCheck size={16} />
        <span><strong>Veredicto de evidencia: {verdict.evidence}</strong><small>Motor {verdict.operational} · agentes {verdict.agentic}</small></span>
        <em>{verdict.blockers.length ? `${verdict.blockers.length} bloqueos` : "sin bloqueos"}</em>
      </div>
    );
  }
  const proposal = injected ?? review?.proposal ?? null;
  if (!proposal) return null;
  const agreement = "agreement_label" in proposal
    ? proposal.agreement_label
    : {
        unanimous: "Acuerdo unánime",
        disagreement: "Desacuerdo visible",
        invalid_review: "Revisión no válida",
      }[proposal.agreementStatus] ?? "Estado de revisión no reconocido";
  const aggregateAction = "aggregate_action" in proposal
    ? proposal.aggregate_action
    : proposal.aggregateAction;
  const actionCounts = "action_counts" in proposal
    ? proposal.action_counts
    : proposal.actionCounts;
  const humanReview = "human_review_recommended" in proposal
    ? proposal.human_review_recommended
    : proposal.humanReviewRecommended;
  const actionSummary = aggregateAction
    ? humanizeAction(aggregateAction)
    : Object.entries(actionCounts)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([action, count]) => `${count}× ${humanizeAction(action)}`)
        .join(" · ");
  return (
    <div className="monitoring-cinematic-proposal">
      <ShieldCheck size={16} />
      <span>
        <strong>{agreement}</strong>
        <small>{actionSummary || "Sin acción agregable"} · {humanReview ? "revisión humana recomendada" : "sin solicitud de revisión humana"}</small>
      </span>
      <em>NO APLICADA</em>
    </div>
  );
}

function HealthRiskChart({ points }: { points: MonitoringCinematicTrendPoint[] }) {
  return (
    <figure className="monitoring-cinematic-chart" data-testid="monitoring-health-trend">
      <figcaption><strong>Salud y riesgo</strong><span>Índices 0–100</span></figcaption>
      <svg aria-label={`Tendencia de salud y riesgo con ${points.length} observaciones`} role="img" viewBox="0 0 420 130">
        <ChartGrid />
        {trendSegments(points).map((segment, index) => (
          <polyline className="health-line" key={`health-${index}`} points={linearPolyline(segment, (point) => point.healthIndex, 0, 100, points)} />
        ))}
        {trendSegments(points).map((segment, index) => (
          <polyline className="risk-line" key={`risk-${index}`} points={linearPolyline(segment, (point) => point.riskIndex, 0, 100, points)} />
        ))}
      </svg>
      <div><span><i className="health" />Salud</span><span><i className="risk" />Riesgo</span></div>
    </figure>
  );
}

function ScoreRatioChart({ points }: { points: MonitoringCinematicTrendPoint[] }) {
  const positive = points.map((point) => point.scoreRatio).filter((value) => value > 0);
  const minLog = Math.min(-2, ...positive.map((value) => Math.log10(value)));
  const maxLog = Math.max(2, ...positive.map((value) => Math.log10(value)));
  const thresholdY = chartY(0, minLog, maxLog);
  return (
    <figure className="monitoring-cinematic-chart" data-scale="log10" data-testid="monitoring-score-ratio-trend">
      <figcaption><strong>Distancia al umbral</strong><span>Escala log · 1× = umbral</span></figcaption>
      <svg aria-label={`Score relativo al umbral en escala logarítmica con ${points.length} observaciones`} role="img" viewBox="0 0 420 130">
        <ChartGrid />
        <line className="ratio-threshold" x1="28" x2="410" y1={thresholdY} y2={thresholdY} />
        <text className="ratio-threshold-label" x="32" y={thresholdY - 5}>1× umbral</text>
        {trendSegments(points).map((segment, index) => (
          <polyline className="ratio-line" key={`ratio-${index}`} points={logPolyline(segment, minLog, maxLog, points)} />
        ))}
      </svg>
      <div><span><i className="ratio" />Score / umbral</span><span>No es probabilidad</span></div>
    </figure>
  );
}

function CausalActRail({
  acts,
  executionCursor,
  healthPoints,
  onInspect,
  onSelectTrigger,
  triggers,
}: {
  acts: MonitoringCinematicAct[];
  executionCursor: number | null;
  healthPoints: MonitoringCinematicTrendPoint[];
  onInspect: (cursor: number) => void;
  onSelectTrigger: (trigger: MonitoringTriggerEvent) => void;
  triggers: MonitoringTriggerEvent[];
}) {
  const stateSegments = healthStateSegments(healthPoints);
  const suppressedCount = triggers.filter(
    (trigger) => ["suppressed", "coalesced"].includes(trigger.lifecycle_status),
  ).length;
  return (
    <section className="monitoring-cinematic-causal-rail" aria-label="Cuatro actos causales" data-testid="monitoring-act-rail">
      <header><strong>Actos causales</strong><span>Pre-roll 0–352</span></header>
      <div>
        {acts.map((act) => {
          const trigger = triggers.find((item) => item.trigger_id === act.triggerId) ?? null;
          const available = executionCursor !== null && act.cutoffCursor <= executionCursor;
          return (
            <button
              data-trigger-id={act.triggerId ?? undefined}
              disabled={!available}
              key={act.ordinal}
              onClick={() => trigger ? onSelectTrigger(trigger) : onInspect(act.cutoffCursor)}
              type="button"
            >
              <span>{act.ordinal}</span><strong>{shortTriggerLabel(act.triggerType)}</strong><small>{act.cutoffCursor}</small>
            </button>
          );
        })}
      </div>
      <div
        aria-label={`Banda de estado algorítmico B1 y ${triggers.length} triggers visibles, ${suppressedCount} suprimidos o agrupados`}
        className="monitoring-cinematic-state-track"
        role="img"
      >
        {stateSegments.map((segment) => (
          <span
            className={`state-${segment.state}`}
            key={`${segment.start}-${segment.state}`}
            style={{
              left: `${(segment.start / 688) * 100}%`,
              width: `${Math.max(((segment.end - segment.start + 1) / 689) * 100, 0.5)}%`,
            }}
            title={`${healthStateLabel(segment.state)} · cursores ${segment.start}–${segment.end}`}
          />
        ))}
        {triggers.map((trigger) => (
          <i
            className={`lifecycle-${trigger.lifecycle_status}`}
            key={trigger.trigger_id}
            style={{ left: `${((trigger.cutoff_cursor ?? 0) / 688) * 100}%` }}
            title={`${triggerTypeLabel(trigger.trigger_type)} · ${trigger.lifecycle_status} · ${trigger.reason}${trigger.suppression_reason ? ` · ${trigger.suppression_reason}` : ""}`}
          />
        ))}
      </div>
      <div className="monitoring-cinematic-track-legend">
        <span>Estado algorítmico B1</span><span>◆ ejecutado</span><span>⊘ suprimido/agrupado</span>
      </div>
      <p>Las decisiones se insertan como interludios; el reloj NASA no avanza durante ellos.</p>
    </section>
  );
}

function healthStateSegments(
  points: MonitoringCinematicTrendPoint[],
): Array<{ end: number; start: number; state: HealthState }> {
  return points.reduce<Array<{ end: number; start: number; state: HealthState }>>(
    (segments, point) => {
      const previous = segments[segments.length - 1];
      if (
        previous
        && !point.gapDetected
        && previous.state === point.healthState
        && previous.end + 1 === point.cursor
      ) previous.end = point.cursor;
      else segments.push({ end: point.cursor, start: point.cursor, state: point.healthState });
      return segments;
    },
    [],
  );
}

function ChartGrid() {
  return <>{[20, 62, 104].map((y) => <line className="cinematic-chart-grid" key={y} x1="28" x2="410" y1={y} y2={y} />)}</>;
}

function TelemetrySparkline({ points }: { points: MonitoringCinematicTelemetryPoint[] }) {
  const values = points.map((point) => point.signalRms);
  const minimum = values.length ? Math.min(...values) : 0;
  const maximum = values.length ? Math.max(...values) : 1;
  const segments = points.reduce<MonitoringCinematicTelemetryPoint[][]>((groups, point) => {
    const current = groups[groups.length - 1];
    if (!current || point.gapDetected) groups.push([point]);
    else current.push(point);
    return groups;
  }, []);
  return (
    <svg aria-label={`Tendencia RMS con ${points.length} observaciones`} className="monitoring-bearing-sparkline" role="img" viewBox="0 0 100 24">
      <line x1="1" x2="99" y1="22" y2="22" />
      {segments.map((segment, segmentIndex) => (
        <polyline
          key={segmentIndex}
          points={segment.map((point) => {
            const index = points.findIndex((candidate) => candidate.cursor === point.cursor);
            const x = 2 + (index / Math.max(1, points.length - 1)) * 96;
            const y = 21 - ((point.signalRms - minimum) / Math.max(Number.EPSILON, maximum - minimum)) * 18;
            return `${x},${y}`;
          }).join(" ")}
        />
      ))}
    </svg>
  );
}

function linearPolyline(
  points: MonitoringCinematicTrendPoint[],
  value: (point: MonitoringCinematicTrendPoint) => number,
  min: number,
  max: number,
  domainPoints: MonitoringCinematicTrendPoint[],
): string {
  return points.map((point) => {
    const index = domainPoints.findIndex((candidate) => candidate.cursor === point.cursor);
    const x = chartX(index, domainPoints.length);
    return `${x},${chartY(value(point), min, max)}`;
  }).join(" ");
}

function logPolyline(
  points: MonitoringCinematicTrendPoint[],
  min: number,
  max: number,
  domainPoints: MonitoringCinematicTrendPoint[],
): string {
  return points.filter((point) => point.scoreRatio > 0).map((point) => {
    const index = domainPoints.findIndex((candidate) => candidate.cursor === point.cursor);
    const x = chartX(index, domainPoints.length);
    return `${x},${chartY(Math.log10(point.scoreRatio), min, max)}`;
  }).join(" ");
}

function trendSegments(
  points: MonitoringCinematicTrendPoint[],
): MonitoringCinematicTrendPoint[][] {
  return points.reduce<MonitoringCinematicTrendPoint[][]>((segments, point) => {
    const current = segments[segments.length - 1];
    if (!current || point.gapDetected) segments.push([point]);
    else current.push(point);
    return segments;
  }, []);
}

function chartX(index: number, total: number): number {
  return 28 + (index / Math.max(1, total - 1)) * 382;
}

function chartY(value: number, min: number, max: number): number {
  return 104 - ((value - min) / Math.max(Number.EPSILON, max - min)) * 84;
}

function projectInjectedBearing(asset: InjectedCinematicAsset, index: number): MonitoringCinematicBearing {
  return {
    analysisStatus: asset.analysis_status,
    assetId: asset.asset_id,
    channelId: asset.channel_id,
    gapDetected: asset.gap_detected,
    healthIndex: asset.health_index,
    healthState: asset.health_state,
    label: asset.asset_label || `B${index + 1}`,
    riskIndex: asset.risk_index,
    scoreRatio: asset.score_ratio,
    signalPeakAbs: asset.signal_peak_abs,
    signalRms: asset.signal_rms,
  };
}

function readInjectedTimeline(): InjectedCinematicBeat[] | null {
  if (typeof window === "undefined") return null;
  const timeline = window.__TFM_MONITORING_CINEMATIC_TIMELINE__;
  if (!Array.isArray(timeline) || timeline.length === 0) return null;
  if (timeline.some((beat, index) => beat.beat_index !== index)) return null;
  return timeline;
}

function bearingHeadline(bearing: MonitoringCinematicBearing): string {
  if (bearing.analysisStatus === "modeled" && bearing.healthState) {
    return healthStateLabel(bearing.healthState);
  }
  if (bearing.analysisStatus === "telemetry_only") return "Solo telemetría";
  return "No disponible";
}

function bearingReading(bearing: MonitoringCinematicBearing): string {
  if (bearing.analysisStatus === "modeled") {
    return `HI ${formatNumber(bearing.healthIndex)} · riesgo ${formatNumber(bearing.riskIndex)}`;
  }
  return `RMS ${formatNumber(bearing.signalRms, 4)} · pico ${formatNumber(bearing.signalPeakAbs, 4)}`;
}

function stateNarrative(bearing: MonitoringCinematicBearing | null): string {
  if (!bearing?.healthState) return "Esperando la primera lectura del canal modelado.";
  return {
    nominal: "Para el motor analítico, el canal modelado permanece dentro del comportamiento esperado.",
    watch: "Para el motor analítico, conviene observar la tendencia; aún no declara una alerta.",
    warning: "Para el motor analítico, la desviación requiere atención; no demuestra daño físico.",
    critical: "Para el motor analítico, el indicador es crítico y requiere revisión causal.",
  }[bearing.healthState];
}

function injectedAgentState(
  decision: InjectedCinematicDecision,
): MonitoringCinematicAgentCell["state"] {
  if (
    [
      "guardrail_fallback",
      "deterministic",
      "protocol_restricted",
      "llm_protocol_restricted",
    ].includes(decision.generation_origin)
  ) return "fallback";
  if (decision.generation_validation_status === "repaired") return "repaired";
  if (
    decision.generation_origin !== "llm"
    || ["error", "invalid", "fallback_applied"].includes(
      decision.generation_validation_status,
    )
  ) return "error";
  return "first_pass";
}

function actionGlyph(action: string | null): string {
  return {
    maintain_policy: "M",
    intensify_observation: "I",
    request_human_review: "H",
    pause_replay: "P",
    insufficient_evidence: "?",
  }[action ?? ""] ?? "·";
}

function phaseLabel(phase: string): string {
  return {
    idle: "Esperando",
    pre_roll: "Pre-roll causal",
    agentic_window: "Ventana agéntica",
    closing: "Cierre",
    completed: "Recorrido cerrado",
  }[phase] ?? phase.replace(/_/g, " ");
}

function shortTriggerLabel(type: string): string {
  if (["state_transition", "persistent_alert", "session_close"].includes(type)) {
    return triggerTypeLabel(type as MonitoringTriggerEvent["trigger_type"]);
  }
  return type.replace(/_/g, " ");
}

function agentStateLabel(state: MonitoringCinematicAgentCell["state"]): string {
  return {
    pending: "pendiente",
    first_pass: "LLM primer intento",
    repaired: "reparada",
    fallback: "fallback",
    error: "error",
  }[state];
}

function humanizeAction(value: string | null): string {
  if (!value) return "";
  return {
    maintain_policy: "Mantener política",
    intensify_observation: "Intensificar observación",
    request_human_review: "Solicitar revisión humana",
    pause_replay: "Pausar replay",
    insufficient_evidence: "Evidencia insuficiente",
  }[value] ?? value.replace(/_/g, " ");
}

function formatNumber(value: number | null, digits = 1): string {
  return value === null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat("es-ES", { maximumFractionDigits: digits }).format(value);
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function wallTimeLabel(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").replace(/\.\d+(?=Z?$)/, "");
}

function injectedActLifecycle(
  prefix: InjectedCinematicBeat[],
  act: MonitoringCinematicAct,
): "pending" | "running" | "resolved" | "failed" {
  const beats = prefix.filter((beat) => beat.cursor === act.cutoffCursor);
  const proposalBeat = [...beats].reverse().find(
    (beat) => beat.kind === "policy_proposal",
  );
  if (proposalBeat?.display_projection.proposal?.status === "invalid_review") {
    return "failed";
  }
  if (proposalBeat) return "resolved";
  if (beats.some((beat) => ["trigger", "agent_decision"].includes(beat.kind))) return "running";
  return "pending";
}
