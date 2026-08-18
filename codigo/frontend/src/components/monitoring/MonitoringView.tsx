import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  Gauge,
  History,
  Pause,
  Play,
  Radar,
  RefreshCw,
  ShieldCheck,
  StepForward,
  Waves,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiClientError,
  createMonitoringSession,
  dispatchMonitoringReview,
  getCurrentMonitoringReviewGate,
  getMonitoringSession,
  listMonitoringSources,
  stepMonitoringSession,
} from "../../api";
import type {
  AgentActivationPolicyKind,
  MonitoringFrame,
  MonitoringChildRunAttempt,
  MonitoringReviewGateCase,
  MonitoringReviewGateOutcomeCounts,
  MonitoringReviewGateView,
  MonitoringReplaySourceSummary,
  MonitoringReviewDispatchOutcome,
  MonitoringSessionView,
  MonitoringTriggerEvent,
  ReplayAssetSpec,
  ReplayStepOutcome,
  ReplayTick,
} from "../../types";
import type {
  MonitoringAgentBridgeContext,
  MonitoringReturnTab,
} from "../../types/ui";
import {
  healthStateLabel,
  MonitoringReplayChart,
  triggerLifecycleGlyph,
  triggerLifecycleLabel,
  triggerTypeLabel,
} from "./MonitoringReplayChart";

type MonitoringTab = MonitoringReturnTab;

const PLAYBACK_RATES = [
  { value: 1, label: "x1", delayMs: 1400 },
  { value: 2, label: "x2", delayMs: 720 },
  { value: 5, label: "x5", delayMs: 320 },
] as const;

export function MonitoringView({
  bridgeContext = null,
  onBridgeRestored,
  onOpenAgentRun,
}: {
  bridgeContext?: MonitoringAgentBridgeContext | null;
  onBridgeRestored?: () => void;
  onOpenAgentRun?: (context: MonitoringAgentBridgeContext) => void;
}) {
  const [sources, setSources] = useState<MonitoringReplaySourceSummary[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [activationPolicyKind, setActivationPolicyKind] = useState<AgentActivationPolicyKind>("P3");
  const [session, setSession] = useState<MonitoringSessionView | null>(null);
  const [activeTab, setActiveTab] = useState<MonitoringTab>("status");
  const [selectedAssetKey, setSelectedAssetKey] = useState<string | null>(null);
  const [selectedTriggerId, setSelectedTriggerId] = useState<string | null>(null);
  const [inspectionCursor, setInspectionCursor] = useState<number | null>(null);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [loadingSources, setLoadingSources] = useState(true);
  const [creating, setCreating] = useState(false);
  const [stepping, setStepping] = useState(false);
  const [dispatchingTriggerId, setDispatchingTriggerId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [triggerAnnouncement, setTriggerAnnouncement] = useState<string | null>(null);
  const [reviewGate, setReviewGate] = useState<MonitoringReviewGateView | null>(null);
  const [reviewGateState, setReviewGateState] = useState<
    "loading" | "published" | "absent" | "error"
  >("loading");
  const [reviewGateError, setReviewGateError] = useState<string | null>(null);
  const [reviewGateExpanded, setReviewGateExpanded] = useState(false);
  const [pendingRestoreFocus, setPendingRestoreFocus] =
    useState<{ tab: MonitoringTab; triggerId: string } | null>(null);
  const restoredBridgeRef = useRef<string | null>(null);
  const dispatchCommandIdsRef = useRef(new Map<string, string>());
  const dispatchInFlightRef = useRef(new Set<string>());

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    setError(null);
    try {
      const payload = await listMonitoringSources();
      setSources(payload);
      setSelectedScenarioId((current) => {
        if (payload.some((source) => source.scenario_id === current)) {
          return current;
        }
        return payload.find((source) => source.available)?.scenario_id ?? payload[0]?.scenario_id ?? "";
      });
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoadingSources(false);
    }
  }, []);

  const loadReviewGate = useCallback(async () => {
    setReviewGateState("loading");
    setReviewGateError(null);
    try {
      const payload = await getCurrentMonitoringReviewGate();
      setReviewGate(payload);
      setReviewGateState("published");
    } catch (caught) {
      setReviewGate(null);
      if (caught instanceof ApiClientError && caught.status === 404) {
        setReviewGateState("absent");
        return;
      }
      setReviewGateState("error");
      setReviewGateError(errorText(caught));
    }
  }, []);

  useEffect(() => {
    void loadSources();
    void loadReviewGate();
  }, [loadReviewGate, loadSources]);

  useEffect(() => {
    if (bridgeContext === null) {
      restoredBridgeRef.current = null;
      return;
    }
    const restoreKey = `${bridgeContext.sessionId}:${bridgeContext.triggerId}`;
    if (restoredBridgeRef.current === restoreKey) {
      return;
    }
    restoredBridgeRef.current = restoreKey;
    let cancelled = false;

    async function restoreMonitoringContext() {
      setPlaying(false);
      setError(null);
      try {
        const restored = await getMonitoringSession(bridgeContext!.sessionId);
        if (cancelled) {
          return;
        }
        const histories = groupTriggerHistories(restored.triggers);
        const trigger = histories.find(
          (history) => history.triggerId === bridgeContext!.triggerId,
        )?.latest ?? null;
        const requestedCursor = bridgeContext!.inspectionCursor;
        const restoredCursor =
          tickAtCursor(restored.ticks, requestedCursor)?.cursor ??
          tickAtCursor(restored.ticks, trigger?.cutoff_cursor ?? null)?.cursor ??
          restored.state.execution_cursor;
        const triggerAsset = trigger?.asset_id
          ? restored.config.asset_specs.find(
              (asset) => asset.asset_id === trigger.asset_id,
            ) ?? null
          : null;
        const primaryAsset =
          triggerAsset ??
          restored.config.asset_specs.find(
            (asset) => asset.analysis_status === "modeled",
          ) ??
          restored.config.asset_specs[0] ??
          null;
        setSession(restored);
        setSelectedScenarioId(restored.source.scenario_id);
        setActivationPolicyKind(restored.config.activation_policy_kind);
        setSelectedAssetKey(primaryAsset ? assetKey(primaryAsset) : null);
        setSelectedTriggerId(bridgeContext!.triggerId);
        setInspectionCursor(restoredCursor);
        setActiveTab(bridgeContext!.returnTab);
        setNotice("Contexto del trigger restaurado sin avanzar el replay.");
        setPendingRestoreFocus({
          tab: bridgeContext!.returnTab,
          triggerId: bridgeContext!.triggerId,
        });
      } catch (caught) {
        restoredBridgeRef.current = null;
        if (!cancelled) {
          setError(errorText(caught));
        }
      }
    }

    void restoreMonitoringContext();
    return () => {
      cancelled = true;
    };
  }, [bridgeContext]);

  useEffect(() => {
    if (pendingRestoreFocus === null || session === null) {
      return;
    }
    const frameId = window.requestAnimationFrame(() => {
      const matching = [...document.querySelectorAll<HTMLElement>("[data-trigger-id]")]
        .find((element) => element.dataset.triggerId === pendingRestoreFocus.triggerId);
      const target = pendingRestoreFocus.tab === "events"
        ? matching?.querySelector<HTMLElement>("summary") ?? matching
        : matching;
      target?.focus();
      setPendingRestoreFocus(null);
      onBridgeRestored?.();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [onBridgeRestored, pendingRestoreFocus, session]);

  const selectedSource = useMemo(
    () => sources.find((source) => source.scenario_id === selectedScenarioId) ?? null,
    [selectedScenarioId, sources],
  );
  useEffect(() => {
    if (!selectedSource) {
      return;
    }
    setActivationPolicyKind((current) => {
      const available = selectedSource.available_activation_policy_kinds;
      if (available.includes(current)) {
        return current;
      }
      return available.includes("P3") ? "P3" : (available[0] ?? "P0");
    });
  }, [selectedSource]);
  const sortedTicks = useMemo(
    () => [...(session?.ticks ?? [])].sort((left, right) => left.cursor - right.cursor),
    [session?.ticks],
  );
  const triggerHistories = useMemo(
    () => groupTriggerHistories(session?.triggers ?? []),
    [session?.triggers],
  );
  const latestTriggers = useMemo(
    () => triggerHistories.map((history) => history.latest),
    [triggerHistories],
  );
  const modeledAsset = useMemo(
    () => session?.config.asset_specs.find((asset) => asset.analysis_status === "modeled") ?? null,
    [session?.config.asset_specs],
  );
  const selectedAsset = useMemo(() => {
    const assets = session?.config.asset_specs ?? [];
    return assets.find((asset) => assetKey(asset) === selectedAssetKey) ?? modeledAsset ?? assets[0] ?? null;
  }, [modeledAsset, selectedAssetKey, session?.config.asset_specs]);
  const executionTick = tickAtCursor(sortedTicks, session?.state.execution_cursor ?? null);
  const inspectedTick = tickAtCursor(sortedTicks, inspectionCursor) ?? executionTick;
  const selectedFrame = selectedAsset ? frameForAsset(inspectedTick, selectedAsset) : null;
  const inspectedCursor = inspectionCursor ?? session?.state.execution_cursor ?? null;
  const triggersAtInspection = useMemo(
    () => latestTriggers.filter((event) => event.cutoff_cursor === inspectedCursor),
    [inspectedCursor, latestTriggers],
  );
  const selectedTrigger = useMemo(() => {
    const explicit = latestTriggers.find((event) => event.trigger_id === selectedTriggerId) ?? null;
    if (explicit?.cutoff_cursor === inspectedCursor) {
      return explicit;
    }
    return preferredTrigger(triggersAtInspection, selectedAsset?.asset_id ?? null);
  }, [inspectedCursor, latestTriggers, selectedAsset?.asset_id, selectedTriggerId, triggersAtInspection]);
  const selectedTriggerHistory = selectedTrigger
    ? triggerHistories.find(
        (history) => history.triggerId === selectedTrigger.trigger_id,
      ) ?? null
    : null;
  const selectedTriggerRunId = linkedChildRunId(
    selectedTriggerHistory?.events ?? [],
    session?.child_runs ?? [],
  );
  const followsExecution =
    session !== null &&
    (inspectionCursor === null || inspectionCursor === session.state.execution_cursor);
  const playbackConfig = PLAYBACK_RATES.find((rate) => rate.value === playbackRate) ?? PLAYBACK_RATES[0];

  const advanceSession = useCallback(async () => {
    if (!session || stepping || session.state.status === "completed" || session.state.status === "failed") {
      return;
    }
    const currentSession = session;
    const followAfterStep =
      inspectionCursor === null || inspectionCursor === currentSession.state.execution_cursor;
    setStepping(true);
    setError(null);
    setNotice(null);
    try {
      const response = await stepMonitoringSession(currentSession.config.session_id, {
        command_id: `mon-step-${crypto.randomUUID()}`,
        expected_revision: currentSession.state.revision,
      });
      if (response.receipt.outcome === "applied" || response.receipt.outcome === "idempotent_replay") {
        const responseTriggers = latestTriggerTransitions(response.triggers);
        const responseTrigger = preferredTrigger(responseTriggers, selectedAsset?.asset_id ?? null);
        setSession((current) => current && current.config.session_id === currentSession.config.session_id
          ? {
              ...current,
              state: response.state,
              ticks: mergeTicks(current.ticks, response.tick),
              triggers: mergeTriggers(current.triggers, response.triggers),
            }
          : current);
        if (followAfterStep) {
          setInspectionCursor(response.state.execution_cursor);
          setSelectedTriggerId(responseTrigger?.trigger_id ?? null);
        }
        setNotice(playing ? null : receiptLabel(response.receipt.outcome));
        setTriggerAnnouncement(
          monitoringAnnouncement(currentSession, response.tick, responseTriggers, response.state.status),
        );
        if (response.state.status === "completed") {
          setPlaying(false);
        }
      } else {
        setPlaying(false);
        setNotice(response.receipt.reason ?? receiptLabel(response.receipt.outcome));
        const refreshed = await getMonitoringSession(currentSession.config.session_id);
        setSession(refreshed);
        setInspectionCursor(refreshed.state.execution_cursor);
      }
    } catch (caught) {
      setPlaying(false);
      setError(errorText(caught));
      if (caught instanceof ApiClientError && caught.status === 409) {
        try {
          const refreshed = await getMonitoringSession(currentSession.config.session_id);
          setSession(refreshed);
          setInspectionCursor(refreshed.state.execution_cursor);
          setNotice("La sesión cambió en otra operación; se ha sincronizado su revisión actual.");
        } catch {
          // El error original conserva el contexto más útil para el usuario.
        }
      }
    } finally {
      setStepping(false);
    }
  }, [inspectionCursor, playing, selectedAsset?.asset_id, session, stepping]);

  useEffect(() => {
    if (!playing || stepping || !session) {
      return;
    }
    if (session.state.status === "completed" || session.state.status === "failed") {
      setPlaying(false);
      return;
    }
    const timeoutId = window.setTimeout(() => void advanceSession(), playbackConfig.delayMs);
    return () => window.clearTimeout(timeoutId);
  }, [advanceSession, playbackConfig.delayMs, playing, session, stepping]);

  async function createSession() {
    if (!selectedSource?.available) {
      return;
    }
    setCreating(true);
    setPlaying(false);
    setError(null);
    setNotice(null);
    setTriggerAnnouncement(null);
    try {
      const created = await createMonitoringSession({
        activation_policy_kind: activationPolicyKind,
        scenario_id: selectedSource.scenario_id,
      });
      const primaryAsset =
        created.config.asset_specs.find((asset) => asset.analysis_status === "modeled") ??
        created.config.asset_specs[0] ??
        null;
      setSession(created);
      setSelectedAssetKey(primaryAsset ? assetKey(primaryAsset) : null);
      setSelectedTriggerId(null);
      setDispatchingTriggerId(null);
      dispatchCommandIdsRef.current.clear();
      dispatchInFlightRef.current.clear();
      setInspectionCursor(created.state.execution_cursor);
      setActiveTab("status");
      setNotice("Sesión histórica preparada. La reproducción permanece pausada.");
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setCreating(false);
    }
  }

  function inspectPrevious() {
    const current = inspectionCursor ?? session?.state.execution_cursor ?? null;
    if (current === null) {
      return;
    }
    const previous = [...sortedTicks].reverse().find((tick) => tick.cursor < current);
    if (previous) {
      setInspectionCursor(previous.cursor);
      setSelectedTriggerId(null);
      setPlaying(false);
    }
  }

  function inspectNext() {
    const current = inspectionCursor;
    if (current === null) {
      return;
    }
    const next = sortedTicks.find((tick) => tick.cursor > current);
    if (next) {
      setInspectionCursor(next.cursor);
      setSelectedTriggerId(null);
      setPlaying(false);
    }
  }

  function inspectCursor(cursor: number) {
    const tick = tickAtCursor(sortedTicks, cursor);
    if (!tick) {
      return;
    }
    setInspectionCursor(tick.cursor);
    setSelectedTriggerId(null);
    setPlaying(false);
  }

  function selectTrigger(trigger: MonitoringTriggerEvent) {
    if (trigger.cutoff_cursor === null) {
      setSelectedTriggerId(trigger.trigger_id);
      setPlaying(false);
      return;
    }
    const tick = tickAtCursor(sortedTicks, trigger.cutoff_cursor);
    if (!tick) {
      return;
    }
    setInspectionCursor(tick.cursor);
    setSelectedTriggerId(trigger.trigger_id);
    if (trigger.asset_id) {
      const triggerAsset = session?.config.asset_specs.find(
        (asset) => asset.asset_id === trigger.asset_id,
      );
      if (triggerAsset) {
        setSelectedAssetKey(assetKey(triggerAsset));
      }
    }
    setPlaying(false);
  }

  function openAgentRun(
    trigger: MonitoringTriggerEvent,
    linkedRunId: string,
  ) {
    if (!session || !onOpenAgentRun) {
      return;
    }
    onOpenAgentRun({
      assetId: trigger.asset_id,
      childRunId: linkedRunId,
      executionCursorAtOpen: session.state.execution_cursor,
      inspectionCursor: trigger.cutoff_cursor ?? inspectedCursor,
      returnTab: activeTab,
      sessionId: session.config.session_id,
      snapshotId: trigger.snapshot_end_id,
      triggerId: trigger.trigger_id,
      triggerLifecycleAtOpen: trigger.lifecycle_status,
      triggerType: trigger.trigger_type,
    });
    setPlaying(false);
  }

  async function dispatchTrigger(trigger: MonitoringTriggerEvent) {
    if (!session || dispatchInFlightRef.current.size > 0) {
      return;
    }
    const history = triggerHistories.find(
      (candidate) => candidate.triggerId === trigger.trigger_id,
    );
    const linkedRunId = linkedChildRunId(
      history?.events ?? [trigger],
      session.child_runs,
    );
    if (!isDispatchableTrigger(trigger, linkedRunId, session)) {
      return;
    }

    const currentSession = session;
    const preservedInspectionCursor = inspectionCursor;
    const commandId = dispatchCommandIdsRef.current.get(trigger.trigger_id) ??
      `mon-dispatch-${crypto.randomUUID()}`;
    dispatchCommandIdsRef.current.set(trigger.trigger_id, commandId);
    dispatchInFlightRef.current.add(trigger.trigger_id);
    setDispatchingTriggerId(trigger.trigger_id);
    setPlaying(false);
    setError(null);
    setNotice(null);
    try {
      const response = await dispatchMonitoringReview(
        currentSession.config.session_id,
        trigger.trigger_id,
        {
          command_id: commandId,
          expected_child_revision: currentSession.child_revision,
        },
      );
      setSession(response.session);
      setInspectionCursor(preservedInspectionCursor);
      setSelectedTriggerId(trigger.trigger_id);
      dispatchCommandIdsRef.current.delete(trigger.trigger_id);
      setNotice(dispatchReceiptLabel(response.receipt.outcome, response.receipt.error));
      const latest = latestTriggerForId(response.session.triggers, trigger.trigger_id);
      setTriggerAnnouncement(
        latest
          ? `Trigger actualizado: ${triggerTypeLabel(latest.trigger_type)}, ${triggerLifecycleLabel(latest.lifecycle_status)}.`
          : "Solicitud de revisión registrada.",
      );
    } catch (caught) {
      setError(errorText(caught));
      if (caught instanceof ApiClientError && caught.status === 409) {
        dispatchCommandIdsRef.current.delete(trigger.trigger_id);
        try {
          const refreshed = await getMonitoringSession(currentSession.config.session_id);
          setSession(refreshed);
          setInspectionCursor(preservedInspectionCursor);
          setSelectedTriggerId(trigger.trigger_id);
          setNotice("El ledger cambió; se ha sincronizado antes de volver a intentarlo.");
        } catch {
          // El error original conserva el contexto más útil para el usuario.
        }
      }
    } finally {
      dispatchInFlightRef.current.delete(trigger.trigger_id);
      setDispatchingTriggerId((current) => current === trigger.trigger_id ? null : current);
    }
  }

  const canInspectPrevious = sortedTicks.some(
    (tick) => tick.cursor < (inspectionCursor ?? session?.state.execution_cursor ?? 0),
  );
  const canInspectNext = sortedTicks.some(
    (tick) => tick.cursor > (inspectionCursor ?? session?.state.execution_cursor ?? -1),
  );
  const canStep =
    session !== null &&
    !stepping &&
    session.state.status !== "completed" &&
    session.state.status !== "failed";
  const policyAvailable = selectedSource?.available_activation_policy_kinds.includes(
    activationPolicyKind,
  ) ?? false;

  function openReviewGateCase(gateCase: MonitoringReviewGateCase) {
    if (
      !onOpenAgentRun ||
      !gateCase.session_id ||
      !gateCase.trigger_id ||
      !gateCase.child_run_id ||
      !gateCase.bridge_lifecycle_status
    ) {
      return;
    }
    onOpenAgentRun({
      assetId: null,
      childRunId: gateCase.child_run_id,
      executionCursorAtOpen: gateCase.cutoff_cursor,
      inspectionCursor: gateCase.cutoff_cursor,
      returnTab: "events",
      sessionId: gateCase.session_id,
      snapshotId: null,
      triggerId: gateCase.trigger_id,
      triggerLifecycleAtOpen: gateCase.bridge_lifecycle_status,
      triggerType: gateCase.trigger_type,
    });
  }

  return (
    <section className="monitoring-view" aria-labelledby="monitoring-title">
      <header className="monitoring-identity-band">
        <div className="monitoring-identity-icon" aria-hidden="true"><History size={21} /></div>
        <div>
          <p className="monitoring-replay-label">REPLAY HISTÓRICO · no tiempo real</p>
          <h2 id="monitoring-title">Centro de monitorización NASA</h2>
          <p>Reproducción causal de snapshots sincronizados. El futuro permanece oculto.</p>
        </div>
        <span className="monitoring-mode-badge"><Clock3 size={14} />Histórico</span>
      </header>

      <MonitoringReviewGatePanel
        expanded={reviewGateExpanded}
        gate={reviewGate}
        loadState={reviewGateState}
        loadError={reviewGateError}
        onOpenCase={openReviewGateCase}
        onRetry={() => void loadReviewGate()}
        onToggle={() => setReviewGateExpanded((current) => !current)}
      />

      <section className="monitoring-source-panel" aria-labelledby="monitoring-source-title">
        <div className="monitoring-source-copy">
          <p className="eyebrow">Fuente registrada</p>
          <h3 id="monitoring-source-title">Selecciona el escenario de replay</h3>
          {selectedSource ? (
            <p>{selectedSource.source_label} · {selectedSource.total_monitoring_ticks} snapshots de monitorización</p>
          ) : (
            <p>La API todavía no ha publicado una fuente disponible.</p>
          )}
        </div>
        <label className="monitoring-field">
          <span>Escenario</span>
          <select
            disabled={loadingSources || creating || sources.length === 0}
            onChange={(event) => setSelectedScenarioId(event.target.value)}
            value={selectedScenarioId}
          >
            {sources.length === 0 ? <option value="">Sin fuentes</option> : null}
            {sources.map((source) => (
              <option key={source.scenario_id} value={source.scenario_id}>
                {source.title}{source.available ? "" : " · no disponible"}
              </option>
            ))}
          </select>
        </label>
        <label className="monitoring-field">
          <span>Política de activación</span>
          <select
            disabled={loadingSources || creating || !selectedSource}
            onChange={(event) => setActivationPolicyKind(event.target.value as AgentActivationPolicyKind)}
            value={activationPolicyKind}
          >
            {(selectedSource?.available_activation_policy_kinds ?? []).map((kind) => (
              <option key={kind} value={kind}>{activationPolicyOptionLabel(kind)}</option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          disabled={!selectedSource?.available || !policyAvailable || creating}
          onClick={() => void createSession()}
          type="button"
        >
          {creating ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
          {session ? "Nueva sesión" : "Preparar sesión"}
        </button>
        {loadingSources ? <span className="monitoring-source-loading">Consultando fuentes…</span> : null}
        {!loadingSources && error && sources.length === 0 ? (
          <button className="secondary-button" onClick={() => void loadSources()} type="button">
            <RefreshCw size={15} />Reintentar
          </button>
        ) : null}
      </section>

      {selectedSource && !selectedSource.available ? (
        <div className="monitoring-inline-alert" role="status">
          <AlertTriangle size={17} />
          <span><strong>Fuente no disponible.</strong> {selectedSource.unavailable_reason}</span>
        </div>
      ) : null}
      {error ? (
        <div className="monitoring-inline-alert danger" role="alert">
          <AlertTriangle size={17} /><span>{error}</span>
        </div>
      ) : null}

      {session ? (
        <>
          <MonitoringSessionBar
            session={session}
            executionTick={executionTick}
            inspectedTick={inspectedTick}
            inspectionCursor={inspectionCursor}
            followsExecution={followsExecution}
          />

          <section className="monitoring-transport" aria-label="Controles de reproducción histórica">
            <div className="monitoring-transport-buttons" role="group" aria-label="Navegación por snapshots">
              <button
                aria-label="Snapshot anterior para inspección"
                className="secondary-button"
                disabled={!canInspectPrevious}
                onClick={inspectPrevious}
                type="button"
              ><ArrowLeft size={16} />Anterior</button>
              <button
                aria-label="Snapshot siguiente ya ejecutado para inspección"
                className="secondary-button"
                disabled={!canInspectNext}
                onClick={inspectNext}
                type="button"
              >Siguiente visible<ArrowRight size={16} /></button>
              <button
                aria-label={playing ? "Pausar reproducción" : "Reproducir mediante pasos causales"}
                aria-pressed={playing}
                className="primary-button"
                disabled={!canStep}
                onClick={() => setPlaying((current) => !current)}
                type="button"
              >{playing ? <Pause size={16} /> : <Play size={16} />}{playing ? "Pausar" : "Reproducir"}</button>
              <button
                className="secondary-button monitoring-step-button"
                disabled={!canStep || playing}
                onClick={() => void advanceSession()}
                type="button"
              ><StepForward size={16} />{stepping ? "Aplicando…" : "Ejecutar un paso"}</button>
            </div>
            <label className="monitoring-rate-field">
              <span>Ritmo visual</span>
              <select
                aria-label="Ritmo visual de reproducción"
                disabled={stepping}
                onChange={(event) => setPlaybackRate(Number(event.target.value))}
                value={playbackRate}
              >
                {PLAYBACK_RATES.map((rate) => (
                  <option key={rate.value} value={rate.value}>{rate.label}</option>
                ))}
              </select>
            </label>
            <button
              className="monitoring-follow-button"
              disabled={followsExecution || session.state.execution_cursor === null}
              onClick={() => {
                setInspectionCursor(session.state.execution_cursor);
                setSelectedTriggerId(null);
                setPlaying(false);
              }}
              type="button"
            >
              <Radar size={15} />Volver al cursor de ejecución
            </button>
          </section>

          <label className="monitoring-cursor-control">
            <span>Cursor de inspección</span>
            <input
              aria-valuetext={cursorAccessibleText(inspectedTick, session.total_monitoring_ticks)}
              disabled={session.state.execution_cursor === null}
              max={Math.max(session.state.execution_cursor ?? 0, 0)}
              min={0}
              onChange={(event) => inspectCursor(Number(event.target.value))}
              step={1}
              type="range"
              value={inspectionCursor ?? 0}
            />
            <strong>{inspectionCursor === null ? "Sin iniciar" : `${inspectionCursor + 1} / ${session.total_monitoring_ticks}`}</strong>
          </label>

          <div className="monitoring-live-status">
            {playing ? "Reproducción histórica en curso…" : stepping ? "Aplicando el siguiente tick causal…" : notice}
          </div>
          <div aria-atomic="true" aria-live="polite" className="sr-only" role="status">
            {triggerAnnouncement}
          </div>

          <AssetCards
            assets={session.config.asset_specs}
            tick={inspectedTick}
            triggers={triggersAtInspection}
            selectedAssetKey={selectedAsset ? assetKey(selectedAsset) : null}
            onSelect={setSelectedAssetKey}
          />

          <div
            aria-label="Secciones de monitorización"
            aria-orientation="horizontal"
            className="monitoring-section-tabs"
            role="tablist"
          >
            <MonitoringTabButton activeTab={activeTab} id="status" onSelect={setActiveTab}>Estado</MonitoringTabButton>
            <MonitoringTabButton activeTab={activeTab} id="replay" onSelect={setActiveTab}>Replay 2D</MonitoringTabButton>
            <MonitoringTabButton activeTab={activeTab} id="events" onSelect={setActiveTab}>Eventos</MonitoringTabButton>
          </div>

          {activeTab === "status" ? (
            <div aria-labelledby="monitoring-tab-status" id="monitoring-panel-status" role="tabpanel" tabIndex={0}>
              <StatusPanel
                canDispatchReview={selectedTrigger !== null &&
                  (dispatchingTriggerId === null || dispatchingTriggerId === selectedTrigger.trigger_id) &&
                  isDispatchableTrigger(selectedTrigger, selectedTriggerRunId, session)}
                dispatching={selectedTrigger?.trigger_id === dispatchingTriggerId}
                frame={selectedFrame}
                tick={inspectedTick}
                trigger={selectedTrigger}
                linkedRunId={selectedTriggerRunId}
                selectedAsset={selectedAsset}
                policyVersion={session.state.active_policy_refs.activation_version}
                onOpenEvents={() => setActiveTab("events")}
                onOpenAgentRun={openAgentRun}
                onDispatchReview={dispatchTrigger}
              />
            </div>
          ) : null}
          {activeTab === "replay" ? (
            <div aria-labelledby="monitoring-tab-replay" id="monitoring-panel-replay" role="tabpanel" tabIndex={0}>
              <MonitoringReplayChart
                executionCursor={session.state.execution_cursor}
                inspectionCursor={inspectionCursor}
                modeledAsset={modeledAsset}
                onInspect={inspectCursor}
                onSelectTrigger={selectTrigger}
                selectedTriggerId={selectedTrigger?.trigger_id ?? null}
                ticks={sortedTicks}
                totalTicks={session.total_monitoring_ticks}
                triggers={latestTriggers}
              />
            </div>
          ) : null}
          {activeTab === "events" ? (
            <div aria-labelledby="monitoring-tab-events" id="monitoring-panel-events" role="tabpanel" tabIndex={0}>
              <EventsPanel
                childRuns={session.child_runs}
                dispatchingTriggerId={dispatchingTriggerId}
                events={session.triggers}
                selectedTriggerId={selectedTrigger?.trigger_id ?? null}
                onInspect={(event) => {
                selectTrigger(event);
                setActiveTab("replay");
              }}
                onOpenAgentRun={openAgentRun}
                onDispatchReview={dispatchTrigger}
                session={session}
              />
            </div>
          ) : null}
        </>
      ) : (
        <section className="monitoring-empty-state">
          <Radar size={26} />
          <div>
            <h3>El replay todavía no ha comenzado</h3>
            <p>Prepara una sesión para avanzar snapshot a snapshot sin recalcular ni revelar el futuro.</p>
          </div>
        </section>
      )}
    </section>
  );
}

function MonitoringReviewGatePanel({
  expanded,
  gate,
  loadState,
  loadError,
  onOpenCase,
  onRetry,
  onToggle,
}: {
  expanded: boolean;
  gate: MonitoringReviewGateView | null;
  loadState: "loading" | "published" | "absent" | "error";
  loadError: string | null;
  onOpenCase: (gateCase: MonitoringReviewGateCase) => void;
  onRetry: () => void;
  onToggle: () => void;
}) {
  const published = loadState === "published" && gate !== null;
  const verdictLabel = gate?.verdict === "passed"
    ? "Gate agentivo superado"
    : gate?.verdict === "blocked"
      ? "Gate agentivo bloqueado"
      : loadState === "loading"
        ? "Comprobando gate publicado"
        : loadState === "error"
          ? "Gate publicado no verificable"
          : "Sin gate publicado";
  return (
    <section
      aria-labelledby="monitoring-review-gate-title"
      className={`monitoring-review-gate tone-${gate?.verdict ?? loadState}`}
    >
      <header className="monitoring-review-gate-band">
        <span className="monitoring-review-gate-icon" aria-hidden="true">
          {gate?.verdict === "passed" ? <ShieldCheck size={21} /> : <Activity size={21} />}
        </span>
        <div className="monitoring-review-gate-heading">
          <span className="eyebrow">Batería trigger → siete agentes</span>
          <h3 id="monitoring-review-gate-title">{verdictLabel}</h3>
        </div>
        {published ? (
          <div className="monitoring-review-gate-facts" aria-label="Identidad del gate publicado">
            <span><strong>{gate.model}</strong><small>{gate.provider}</small></span>
            <span><strong>Memoria OFF</strong><small>sin RAG</small></span>
            <span>
              <strong>{gate.complete_repetition_count}/{gate.expected_repetition_count}</strong>
              <small>repeticiones</small>
            </span>
            <span>
              <strong>{gate.resolved_child_run_count}/{gate.expected_child_run_count}</strong>
              <small>runs resueltas</small>
            </span>
            <span>
              <strong>{gate.outcomes.observed_count}/{gate.outcomes.expected_count}</strong>
              <small>decisiones</small>
            </span>
          </div>
        ) : null}
        {published ? (
          <button
            aria-expanded={expanded}
            className="secondary-button monitoring-review-gate-toggle"
            onClick={onToggle}
            type="button"
          >
            {expanded ? "Ocultar batería" : "Ver batería"}
            <ChevronDown className={expanded ? "expanded" : undefined} size={16} />
          </button>
        ) : loadState === "error" ? (
          <button className="secondary-button" onClick={onRetry} type="button">
            <RefreshCw size={15} />Verificar de nuevo
          </button>
        ) : null}
      </header>

      {loadState === "absent" ? (
        <p className="monitoring-review-gate-state">Todavía no se ha publicado una batería canónica.</p>
      ) : null}
      {loadState === "error" ? (
        <p className="monitoring-review-gate-state danger" role="alert">
          La publicación existe, pero no supera la verificación de integridad.
          {loadError ? <span className="sr-only"> {loadError}</span> : null}
        </p>
      ) : null}
      {published && expanded ? (
        <div className="monitoring-review-gate-body">
          <GateRoleBars gate={gate} />
          <GateCaseMatrix gate={gate} onOpenCase={onOpenCase} />
          <GateCoverage gate={gate} />
          <details className="monitoring-disclosure monitoring-review-gate-scope">
            <summary>Alcance del resultado</summary>
            <p>
              Mide contrato, procedencia y evidencia causal. No confirma la verdad física
              de las hipótesis ni la utilidad de memoria RAG.
            </p>
            {gate.verdict === "blocked" ? (
              <span>{gate.blockers.length} {gate.blockers.length === 1 ? "condición bloqueante" : "condiciones bloqueantes"}.</span>
            ) : null}
          </details>
        </div>
      ) : null}
    </section>
  );
}

function GateRoleBars({ gate }: { gate: MonitoringReviewGateView }) {
  return (
    <section aria-labelledby="monitoring-gate-role-title" className="monitoring-gate-role-chart">
      <div className="monitoring-gate-subheading">
        <div><span className="eyebrow">Procedencia por rol</span><h4 id="monitoring-gate-role-title">Los siete agentes</h4></div>
        <div className="monitoring-gate-legend" aria-label="Leyenda de procedencia">
          <span className="first-pass">Primer intento</span>
          <span className="repaired">Reparación</span>
          <span className="fallback">Fallback</span>
          <span className="error">Fallo</span>
          <span className="missing">Ausente</span>
        </div>
      </div>
      <div className="monitoring-gate-role-rows">
        {gate.roles.map((role) => (
          <div className="monitoring-gate-role-row" key={role.agent_name}>
            <span>{monitoringRoleLabel(role.agent_name)}</span>
            <GateOutcomeTrack counts={role.outcomes} />
            <strong>{role.outcomes.observed_count}/{role.outcomes.expected_count}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

function GateOutcomeTrack({ counts }: { counts: MonitoringReviewGateOutcomeCounts }) {
  const segments = [
    ["first-pass", counts.first_pass_count, "Primer intento"],
    ["repaired", counts.repaired_count, "Reparación LLM"],
    ["fallback", counts.fallback_count, "Fallback"],
    ["error", counts.non_agentic_count + counts.error_count, "No agéntica o error"],
    ["missing", counts.missing_count, "Ausente"],
  ] as const;
  return (
    <div className="monitoring-gate-outcome-track">
      {segments.map(([tone, value, label]) => value > 0 ? (
        <i
          className={tone}
          key={tone}
          style={{ width: `${(value / Math.max(1, counts.expected_count)) * 100}%` }}
          title={`${label}: ${value}`}
        />
      ) : null)}
    </div>
  );
}

function GateCaseMatrix({
  gate,
  onOpenCase,
}: {
  gate: MonitoringReviewGateView;
  onOpenCase: (gateCase: MonitoringReviewGateCase) => void;
}) {
  const contexts = [...new Map(
    gate.cases.map((item) => [item.context_ordinal, item]),
  ).values()].sort((left, right) => left.context_ordinal - right.context_ordinal);
  const repetitions = Array.from(
    { length: gate.expected_repetition_count },
    (_, index) => index + 1,
  );
  return (
    <section aria-labelledby="monitoring-gate-matrix-title" className="monitoring-gate-matrix-section">
      <div className="monitoring-gate-subheading">
        <div><span className="eyebrow">Variedad y repetición</span><h4 id="monitoring-gate-matrix-title">Contextos auditados</h4></div>
        <span>{gate.cases.length} runs planificadas</span>
      </div>
      <div
        className="monitoring-gate-matrix"
        style={{ gridTemplateColumns: `minmax(9.5rem, 1.15fr) repeat(${repetitions.length}, minmax(7rem, 1fr))` }}
      >
        <span className="monitoring-gate-matrix-corner">Trigger causal</span>
        {repetitions.map((repetition) => (
          <strong className="monitoring-gate-matrix-header" key={repetition}>Repetición {repetition}</strong>
        ))}
        {contexts.flatMap((context) => {
          const rowCases = repetitions.map((repetition) => gate.cases.find(
            (item) => item.context_id === context.context_id && item.repetition === repetition,
          ) ?? null);
          return [
            <div className="monitoring-gate-context-label" key={`${context.context_id}:label`}>
              <strong>{triggerTypeLabel(context.trigger_type)}</strong>
              <small>cursor {context.cutoff_cursor + 1}</small>
            </div>,
            ...rowCases.map((gateCase, index) => gateCase ? (
              <GateCaseButton
                gateCase={gateCase}
                key={gateCase.case_id}
                onOpen={() => onOpenCase(gateCase)}
              />
            ) : (
              <span className="monitoring-gate-case missing" key={`${context.context_id}:${index}:missing`}>Sin observación</span>
            )),
          ];
        })}
      </div>
      <div className="monitoring-gate-action-legend" aria-label="Leyenda de acciones propuestas">
        <span className="maintain-policy">Mantener</span>
        <span className="intensify-observation">Intensificar</span>
        <span className="request-human-review">Revisión humana</span>
        <span className="pause-replay">Pausar</span>
        <span className="insufficient-evidence">Evidencia insuficiente</span>
      </div>
    </section>
  );
}

function GateCaseButton({
  gateCase,
  onOpen,
}: {
  gateCase: MonitoringReviewGateCase;
  onOpen: () => void;
}) {
  const linked = Boolean(
    gateCase.session_id && gateCase.trigger_id && gateCase.child_run_id && gateCase.bridge_lifecycle_status,
  );
  const exceptional = gateCase.role_results.some(
    (item) => ["fallback", "non_agentic", "error", "missing"].includes(item.outcome),
  );
  const repaired = gateCase.role_results.some((item) => item.outcome === "llm_repaired");
  const accessibleRoles = gateCase.role_results.map(
    (item) => `${monitoringRoleLabel(item.agent_name)}: ${gateActionLabel(item.recommended_action)}, ${gateOutcomeLabel(item.outcome)}`,
  ).join(". ");
  return (
    <button
      aria-label={`${triggerTypeLabel(gateCase.trigger_type)}, repetición ${gateCase.repetition}. ${accessibleRoles}`}
      className={`monitoring-gate-case${exceptional ? " exceptional" : repaired ? " repaired" : " clean"}`}
      disabled={!linked}
      onClick={onOpen}
      title={linked ? `Abrir ${gateCase.child_run_id} en Agentes` : "Run no disponible"}
      type="button"
    >
      <span className="monitoring-gate-role-strips" aria-hidden="true">
        {gateCase.role_results.map((item) => (
          <i
            className={`action-${item.recommended_action?.replace(/_/g, "-") ?? "missing"} outcome-${item.outcome.replace(/_/g, "-")}`}
            key={item.agent_name}
            title={`${monitoringRoleLabel(item.agent_name)} · ${gateActionLabel(item.recommended_action)}`}
          />
        ))}
      </span>
      <span>{gateCase.observed_role_count}/{gateCase.expected_role_count} roles</span>
      <small>{repaired ? "con reparación" : exceptional ? "requiere auditoría" : "primer intento"}</small>
    </button>
  );
}

function GateCoverage({ gate }: { gate: MonitoringReviewGateView }) {
  return (
    <section aria-labelledby="monitoring-gate-coverage-title" className="monitoring-gate-coverage">
      <div className="monitoring-gate-subheading">
        <div><span className="eyebrow">Trazabilidad contractual</span><h4 id="monitoring-gate-coverage-title">Coberturas exactas</h4></div>
      </div>
      <div className="monitoring-gate-coverage-grid">
        {gate.coverage.map((item) => {
          const ratio = item.expected_count === 0 ? 0 : item.passed_count / item.expected_count;
          return (
            <article key={item.kind}>
              <span>{gateCoverageLabel(item.kind)}</span>
              <div><i style={{ width: `${ratio * 100}%` }} /></div>
              <strong>{item.passed_count}/{item.expected_count}</strong>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function MonitoringSessionBar({
  session,
  executionTick,
  inspectedTick,
  inspectionCursor,
  followsExecution,
}: {
  session: MonitoringSessionView;
  executionTick: ReplayTick | null;
  inspectedTick: ReplayTick | null;
  inspectionCursor: number | null;
  followsExecution: boolean;
}) {
  return (
    <section className="monitoring-session-bar" aria-label="Contexto de sesión histórica">
      <div>
        <span>Sesión</span>
        <strong>{session.config.session_id}</strong>
      </div>
      <div>
        <span>Fuente NASA</span>
        <strong>{session.source.trajectory_id}</strong>
      </div>
      <div>
        <span>Cursor ejecutado</span>
        <strong>{executionTick ? `${executionTick.cursor + 1} · ${executionTick.snapshot_id}` : "Sin iniciar"}</strong>
      </div>
      <div className={followsExecution ? "in-sync" : "inspecting"}>
        <span>Cursor inspeccionado</span>
        <strong>{inspectedTick ? `${(inspectionCursor ?? inspectedTick.cursor) + 1} · ${sourceTimeLabel(inspectedTick.source_time)}` : "Sin iniciar"}</strong>
      </div>
      <div>
        <span>Política</span>
        <strong>{session.config.activation_policy_kind} · {session.state.active_policy_refs.activation_version}</strong>
      </div>
      <div>
        <span>Estado de sesión</span>
        <strong>{sessionStatusLabel(session.state.status)}</strong>
      </div>
    </section>
  );
}

function AssetCards({
  assets,
  tick,
  triggers,
  selectedAssetKey,
  onSelect,
}: {
  assets: ReplayAssetSpec[];
  tick: ReplayTick | null;
  triggers: MonitoringTriggerEvent[];
  selectedAssetKey: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <section className="monitoring-assets" aria-labelledby="monitoring-assets-title">
      <div className="monitoring-assets-heading">
        <div>
          <p className="eyebrow">Snapshot sincronizado</p>
          <h3 id="monitoring-assets-title">Canales del activo</h3>
        </div>
        <span>{tick ? sourceTimeLabel(tick.source_time) : "Esperando primer snapshot"}</span>
      </div>
      <div className="monitoring-asset-grid" role="group" aria-label="Seleccionar canal para inspección">
        {assets.map((asset) => {
          const frame = frameForAsset(tick, asset);
          const selected = assetKey(asset) === selectedAssetKey;
          const assetTriggers = triggers.filter((event) => event.asset_id === asset.asset_id);
          const assetTrigger = preferredTrigger(assetTriggers, asset.asset_id);
          return (
            <button
              aria-label={assetAccessibleLabel(asset, frame, assetTriggers)}
              aria-pressed={selected}
              className={`monitoring-asset-card analysis-${asset.analysis_status}${selected ? " selected" : ""}`}
              key={assetKey(asset)}
              onClick={() => onSelect(assetKey(asset))}
              type="button"
            >
              <span className="monitoring-asset-icon" aria-hidden="true">
                {asset.analysis_status === "modeled" ? <Gauge size={19} /> : <Waves size={19} />}
              </span>
              {assetTrigger ? (
                <span
                  aria-hidden="true"
                  className={`monitoring-asset-trigger-badge lifecycle-${assetTrigger.lifecycle_status}`}
                  data-lifecycle={assetTrigger.lifecycle_status}
                  title={`${triggerLifecycleLabel(assetTrigger.lifecycle_status)} · ${assetTriggers.length} trigger${assetTriggers.length === 1 ? "" : "s"}`}
                >
                  {triggerLifecycleGlyph(assetTrigger.lifecycle_status)}
                  {assetTriggers.length > 1 ? <b>{assetTriggers.length}</b> : null}
                </span>
              ) : null}
              <span className="monitoring-asset-name">
                <strong>{humanizeIdentifier(asset.asset_id)}</strong>
                <small>{humanizeIdentifier(asset.channel_id)}</small>
              </span>
              <span className="monitoring-analysis-label">{analysisStatusLabel(asset.analysis_status)}</span>
              <strong className="monitoring-asset-value">{frameHeadline(frame)}</strong>
              <small className="monitoring-asset-caption">{frameCaption(frame)}</small>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function StatusPanel({
  canDispatchReview,
  dispatching,
  frame,
  tick,
  trigger,
  linkedRunId,
  selectedAsset,
  policyVersion,
  onOpenEvents,
  onOpenAgentRun,
  onDispatchReview,
}: {
  canDispatchReview: boolean;
  dispatching: boolean;
  frame: MonitoringFrame | null;
  tick: ReplayTick | null;
  trigger: MonitoringTriggerEvent | null;
  linkedRunId: string | null;
  selectedAsset: ReplayAssetSpec | null;
  policyVersion: string;
  onOpenEvents: () => void;
  onOpenAgentRun: (
    trigger: MonitoringTriggerEvent,
    linkedRunId: string,
  ) => void;
  onDispatchReview: (trigger: MonitoringTriggerEvent) => void;
}) {
  const canOpenAgentRun = trigger !== null &&
    linkedRunId !== null &&
    isAgentRunLifecycle(trigger.lifecycle_status);
  return (
    <section className="monitoring-status-grid">
      <article className={`monitoring-status-card ${frameTone(frame)}`}>
        <div className="monitoring-card-heading">
          <div>
            <p className="eyebrow">Lectura inspeccionada</p>
            <h3>{selectedAsset ? humanizeIdentifier(selectedAsset.asset_id) : "Activo"}</h3>
          </div>
          <span className="monitoring-status-symbol" aria-hidden="true">
            {frame?.analysis_status === "modeled" && frame.health_state === "nominal"
              ? <CheckCircle2 size={24} />
              : <Gauge size={24} />}
          </span>
        </div>
        <strong className="monitoring-state-headline">{frameHeadline(frame)}</strong>
        <p>{statusExplanation(frame)}</p>
        <div className="monitoring-kpi-grid">
          {frame?.analysis_status === "modeled" ? (
            <>
              <Metric label="Índice de salud" value={`${formatNumber(frame.health_index, 1)} / 100`} />
              <Metric label="Riesgo" value={`${formatNumber(frame.risk_index, 1)} / 100`} />
              <Metric label="Score" value={formatNumber(frame.score, 3)} />
              <Metric label="Umbral" value={formatNumber(frame.threshold, 3)} />
            </>
          ) : frame?.analysis_status === "telemetry_only" ? (
            <>
              <Metric label="RMS" value={formatNumber(frame.telemetry.signal_rms, 4)} />
              <Metric label="Pico absoluto" value={formatNumber(frame.telemetry.signal_peak_abs, 4)} />
              <Metric label="Muestras" value={formatInteger(frame.telemetry.n_samples)} />
              <Metric label="Diagnóstico" value="No disponible" />
            </>
          ) : (
            <Metric label="Estado" value={frame?.analysis_status === "unavailable" ? "No disponible" : "Sin snapshot"} />
          )}
        </div>
        <details className="monitoring-disclosure">
          <summary>Contexto técnico</summary>
          <dl>
            <div><dt>Snapshot</dt><dd>{tick?.snapshot_id ?? "—"}</dd></div>
            <div><dt>Tiempo fuente</dt><dd>{tick ? sourceTimeLabel(tick.source_time) : "—"}</dd></div>
            <div><dt>Política activa</dt><dd>{policyVersion}</dd></div>
            <div><dt>Versión de scoring</dt><dd>{frame?.analysis_status === "modeled" ? frame.scoring_version : "No aplicable"}</dd></div>
          </dl>
        </details>
      </article>

      <article
        aria-label={trigger
          ? `Trigger seleccionado: ${triggerTypeLabel(trigger.trigger_type)}`
          : "Trigger seleccionado: ninguno"}
        className="monitoring-trigger-card"
        data-trigger-id={trigger?.trigger_id}
        role="region"
        tabIndex={-1}
      >
        <div className="monitoring-card-heading">
          <div>
            <p className="eyebrow">Revisión causal</p>
            <h3>Trigger seleccionado</h3>
          </div>
          <Zap size={22} aria-hidden="true" />
        </div>
        {trigger ? (
          <>
            <div className="monitoring-trigger-title">
              <strong>{triggerTypeLabel(trigger.trigger_type)}</strong>
              <span className={`monitoring-lifecycle lifecycle-${trigger.lifecycle_status}`}>
                <span aria-hidden="true">{triggerLifecycleGlyph(trigger.lifecycle_status)}</span>
                {triggerExecutionLabel(trigger, linkedRunId)}
              </span>
            </div>
            <dl className="monitoring-trigger-meta">
              <div><dt>Prioridad</dt><dd>{trigger.priority}</dd></div>
              <div><dt>Snapshot</dt><dd>{trigger.snapshot_end_id ?? "Preflight"}</dd></div>
              <div><dt>Activo</dt><dd>{trigger.asset_id ? humanizeIdentifier(trigger.asset_id) : "Sesión"}</dd></div>
              <div><dt>Run agente</dt><dd>{triggerRunLabel(linkedRunId)}</dd></div>
            </dl>
            <details className="monitoring-disclosure monitoring-trigger-reason">
              <summary>Motivo y política</summary>
              <p>{trigger.reason}</p>
              <dl>
                <div><dt>Regla</dt><dd>{humanizeIdentifier(trigger.reason_code)}</dd></div>
                <div><dt>Política</dt><dd>{trigger.activation_version}</dd></div>
              </dl>
            </details>
            <div className="monitoring-trigger-actions">
              <button className="secondary-button monitoring-open-events" onClick={onOpenEvents} type="button">
                <Zap size={15} />Abrir en Eventos
              </button>
              {canDispatchReview ? (
                <button
                  aria-busy={dispatching}
                  aria-label={`${dispatching ? "Lanzando" : "Lanzar"} revisión para el trigger ${triggerTypeLabel(trigger.trigger_type)}`}
                  className="primary-button monitoring-dispatch-review"
                  disabled={dispatching}
                  onClick={() => onDispatchReview(trigger)}
                  type="button"
                >
                  <RefreshCw className={dispatching ? "spin" : undefined} size={15} />
                  {dispatching ? "Lanzando…" : "Lanzar revisión"}
                </button>
              ) : null}
              {canOpenAgentRun && trigger && linkedRunId ? (
                <button
                  aria-label={agentRunCtaAccessibleLabel(trigger, linkedRunId)}
                  className="primary-button monitoring-open-agents"
                  onClick={() => onOpenAgentRun(trigger, linkedRunId)}
                  type="button"
                >
                  <Activity size={15} />{agentRunCtaLabel(trigger.lifecycle_status)}
                </button>
              ) : null}
            </div>
          </>
        ) : (
          <div className="monitoring-quiet-state">
            <CheckCircle2 size={22} />
            <div><strong>Sin trigger seleccionado</strong><p>Selecciona un marcador o inspecciona un snapshot con eventos.</p></div>
          </div>
        )}
      </article>
    </section>
  );
}

function EventsPanel({
  childRuns,
  dispatchingTriggerId,
  events,
  selectedTriggerId,
  onInspect,
  onOpenAgentRun,
  onDispatchReview,
  session,
}: {
  childRuns: MonitoringChildRunAttempt[];
  dispatchingTriggerId: string | null;
  events: MonitoringTriggerEvent[];
  selectedTriggerId: string | null;
  onInspect: (event: MonitoringTriggerEvent) => void;
  onOpenAgentRun: (
    trigger: MonitoringTriggerEvent,
    linkedRunId: string,
  ) => void;
  onDispatchReview: (trigger: MonitoringTriggerEvent) => void;
  session: MonitoringSessionView;
}) {
  const histories = groupTriggerHistories(events);
  const latest = histories.map((history) => history.latest);
  const attention = latest.filter((event) => event.lifecycle_status === "emitted").length;
  const inAnalysis = latest.filter((event) => ["dispatched", "running"].includes(event.lifecycle_status)).length;
  const notExecuted = latest.filter((event) => ["suppressed", "coalesced"].includes(event.lifecycle_status)).length;
  const closed = latest.filter((event) => ["resolved", "failed"].includes(event.lifecycle_status)).length;
  return (
    <section className="monitoring-events-panel" aria-labelledby="monitoring-events-title">
      <div className="monitoring-events-heading">
        <div>
          <p className="eyebrow">Ledger de activación</p>
          <h3 id="monitoring-events-title">Eventos y política</h3>
        </div>
        <div className="monitoring-event-counts" aria-label="Resumen de triggers" role="group">
          <span><strong>{attention}</strong> atención</span>
          <span><strong>{inAnalysis}</strong> en análisis</span>
          <span><strong>{notExecuted}</strong> no ejecutados</span>
          <span><strong>{closed}</strong> cerrados</span>
        </div>
      </div>
      {histories.length ? (
        <div className="monitoring-event-list" aria-label="Triggers de la sesión" role="list">
          {[...histories].reverse().map((history) => {
            const event = history.latest;
            const linkedRunId = linkedChildRunId(history.events, childRuns);
            const selected = event.trigger_id === selectedTriggerId;
            const canOpenAgentRun = linkedRunId !== null &&
              isAgentRunLifecycle(event.lifecycle_status);
            const dispatching = dispatchingTriggerId === event.trigger_id;
            const canDispatchReview =
              (dispatchingTriggerId === null || dispatching) &&
              isDispatchableTrigger(event, linkedRunId, session);
            return (
              <article
                className={`monitoring-event-row${selected ? " selected" : ""}`}
                data-lifecycle={event.lifecycle_status}
                data-trigger-id={event.trigger_id}
                key={event.trigger_id}
                role="listitem"
              >
                <details>
                  <summary>
                    <span className={`monitoring-event-marker lifecycle-${event.lifecycle_status}`} aria-hidden="true">
                      {triggerLifecycleGlyph(event.lifecycle_status)}
                    </span>
                    <span className="monitoring-event-main">
                      <strong>{triggerTypeLabel(event.trigger_type)}</strong>
                      <small>{event.snapshot_end_id ?? "Antes del primer snapshot"}</small>
                    </span>
                    <span className={`monitoring-lifecycle lifecycle-${event.lifecycle_status}`}>
                      {triggerLifecycleLabel(event.lifecycle_status)}
                    </span>
                    <span className={`monitoring-run-state${linkedRunId ? " linked" : ""}`}>
                      {linkedRunId ? "Run enlazada" : "Sin run"}
                    </span>
                  </summary>
                  <div className="monitoring-event-detail" aria-label={`Detalle del trigger ${event.trigger_id}`} role="region">
                    <p>{event.reason}</p>
                    <ol className="monitoring-event-history" aria-label="Historial del trigger">
                      {history.events.map((transition) => (
                        <li data-lifecycle={transition.lifecycle_status} key={transition.event_id}>
                          <span aria-hidden="true">{triggerLifecycleGlyph(transition.lifecycle_status)}</span>
                          <strong>{triggerLifecycleLabel(transition.lifecycle_status)}</strong>
                          <small>revisión {transition.lifecycle_revision}</small>
                        </li>
                      ))}
                    </ol>
                    <dl>
                      <div><dt>Trigger</dt><dd>{event.trigger_id}</dd></div>
                      <div><dt>Evento actual</dt><dd>{event.event_id}</dd></div>
                      <div><dt>Cursor causal</dt><dd>{event.cutoff_cursor === null ? "Preflight" : event.cutoff_cursor + 1}</dd></div>
                      <div><dt>Tiempo fuente</dt><dd>{event.cutoff_source_time ? sourceTimeLabel(event.cutoff_source_time) : "No aplica"}</dd></div>
                      <div><dt>Regla</dt><dd>{humanizeIdentifier(event.reason_code)}</dd></div>
                      <div><dt>Prioridad</dt><dd>{event.priority}</dd></div>
                      <div><dt>Política</dt><dd>{event.activation_version}</dd></div>
                      <div><dt>Cooldown</dt><dd>{formatIntervalSeconds(event.cooldown_source_seconds)}</dd></div>
                      <div><dt>Run agente</dt><dd>{linkedRunId ?? "No se ha ejecutado"}</dd></div>
                      {event.requested_roles.length ? (
                        <div><dt>Roles solicitados</dt><dd>{event.requested_roles.map(humanizeIdentifier).join(", ")}</dd></div>
                      ) : null}
                      {event.suppressed_by_trigger_id ? (
                        <div><dt>Suprimido por</dt><dd>{event.suppressed_by_trigger_id}</dd></div>
                      ) : null}
                      {event.coalesced_into_trigger_id ? (
                        <div><dt>Agrupado en</dt><dd>{event.coalesced_into_trigger_id}</dd></div>
                      ) : null}
                    </dl>
                    <div className="monitoring-event-actions">
                      {event.cutoff_cursor !== null ? (
                        <button className="secondary-button" onClick={() => onInspect(event)} type="button">
                          <Radar size={15} />Examinar snapshot causal
                        </button>
                      ) : null}
                      {canDispatchReview ? (
                        <button
                          aria-busy={dispatching}
                          aria-label={`${dispatching ? "Lanzando" : "Lanzar"} revisión para el trigger ${triggerTypeLabel(event.trigger_type)}`}
                          className="primary-button monitoring-dispatch-review"
                          disabled={dispatching}
                          onClick={() => onDispatchReview(event)}
                          type="button"
                        >
                          <RefreshCw className={dispatching ? "spin" : undefined} size={15} />
                          {dispatching ? "Lanzando…" : "Lanzar revisión"}
                        </button>
                      ) : null}
                      {canOpenAgentRun && linkedRunId ? (
                        <button
                          aria-label={agentRunCtaAccessibleLabel(event, linkedRunId)}
                          className="primary-button"
                          onClick={() => onOpenAgentRun(event, linkedRunId)}
                          type="button"
                        >
                          <Activity size={15} />{agentRunCtaLabel(event.lifecycle_status)}
                        </button>
                      ) : null}
                    </div>
                  </div>
                </details>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="monitoring-quiet-state">
          <CheckCircle2 size={22} />
          <div><strong>Sin eventos emitidos</strong><p>Los triggers aparecerán aquí al cumplirse una regla determinista.</p></div>
        </div>
      )}
    </section>
  );
}

function MonitoringTabButton({
  activeTab,
  id,
  children,
  onSelect,
}: {
  activeTab: MonitoringTab;
  id: MonitoringTab;
  children: string;
  onSelect: (tab: MonitoringTab) => void;
}) {
  const selected = activeTab === id;
  const tabOrder: MonitoringTab[] = ["status", "replay", "events"];
  function moveFocus(event: React.KeyboardEvent<HTMLButtonElement>) {
    const currentIndex = tabOrder.indexOf(id);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % tabOrder.length;
    } else if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + tabOrder.length) % tabOrder.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = tabOrder.length - 1;
    }
    if (nextIndex === null) {
      return;
    }
    event.preventDefault();
    const nextTab = tabOrder[nextIndex];
    onSelect(nextTab);
    window.requestAnimationFrame(() => document.getElementById(`monitoring-tab-${nextTab}`)?.focus());
  }
  return (
    <button
      aria-controls={`monitoring-panel-${id}`}
      aria-selected={selected}
      className={selected ? "active" : ""}
      id={`monitoring-tab-${id}`}
      onKeyDown={moveFocus}
      onClick={() => onSelect(id)}
      role="tab"
      tabIndex={selected ? 0 : -1}
      type="button"
    >{children}</button>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="monitoring-metric"><span>{label}</span><strong>{value}</strong></div>;
}

function mergeTicks(ticks: ReplayTick[], tick: ReplayTick | null): ReplayTick[] {
  if (!tick) {
    return ticks;
  }
  return [...ticks.filter((candidate) => candidate.tick_id !== tick.tick_id), tick].sort(
    (left, right) => left.cursor - right.cursor,
  );
}

function mergeTriggers(
  current: MonitoringTriggerEvent[],
  incoming: MonitoringTriggerEvent[],
): MonitoringTriggerEvent[] {
  const merged = new Map(current.map((event) => [event.event_id, event]));
  for (const event of incoming) {
    merged.set(event.event_id, event);
  }
  return [...merged.values()].sort((left, right) => left.sequence - right.sequence);
}

function latestTriggerTransitions(events: MonitoringTriggerEvent[]): MonitoringTriggerEvent[] {
  return groupTriggerHistories(events).map((history) => history.latest);
}

interface TriggerHistory {
  triggerId: string;
  events: MonitoringTriggerEvent[];
  latest: MonitoringTriggerEvent;
}

function groupTriggerHistories(events: MonitoringTriggerEvent[]): TriggerHistory[] {
  const grouped = new Map<string, MonitoringTriggerEvent[]>();
  for (const event of events) {
    grouped.set(event.trigger_id, [...(grouped.get(event.trigger_id) ?? []), event]);
  }
  return [...grouped.entries()]
    .map(([triggerId, triggerEvents]) => {
      const ordered = [...triggerEvents].sort(
        (left, right) => left.lifecycle_revision - right.lifecycle_revision || left.sequence - right.sequence,
      );
      return {
        triggerId,
        events: ordered,
        latest: ordered[ordered.length - 1],
      };
    })
    .filter((history): history is TriggerHistory => history.latest !== undefined)
    .sort((left, right) => left.latest.sequence - right.latest.sequence);
}

function preferredTrigger(
  events: MonitoringTriggerEvent[],
  preferredAssetId: string | null,
): MonitoringTriggerEvent | null {
  const matchingAsset = preferredAssetId
    ? events.filter((event) => event.asset_id === preferredAssetId)
    : [];
  const candidates = matchingAsset.length ? matchingAsset : events;
  return [...candidates].sort(
    (left, right) => right.priority - left.priority || right.sequence - left.sequence,
  )[0] ?? null;
}

function tickAtCursor(ticks: ReplayTick[], cursor: number | null): ReplayTick | null {
  if (cursor === null) {
    return null;
  }
  return ticks.find((tick) => tick.cursor === cursor) ?? null;
}

function frameForAsset(tick: ReplayTick | null, asset: ReplayAssetSpec): MonitoringFrame | null {
  return tick?.frames.find(
    (frame) => frame.asset_id === asset.asset_id && frame.channel_id === asset.channel_id,
  ) ?? null;
}

function assetKey(asset: ReplayAssetSpec): string {
  return `${asset.asset_id}::${asset.channel_id}`;
}

function frameHeadline(frame: MonitoringFrame | null): string {
  if (!frame) {
    return "Esperando datos";
  }
  if (frame.analysis_status === "modeled") {
    return healthStateLabel(frame.health_state);
  }
  if (frame.analysis_status === "telemetry_only") {
    return `RMS ${formatNumber(frame.telemetry.signal_rms, 4)}`;
  }
  return "No disponible";
}

function frameCaption(frame: MonitoringFrame | null): string {
  if (!frame) {
    return "Sin snapshot ejecutado";
  }
  if (frame.analysis_status === "modeled") {
    return `HI ${formatNumber(frame.health_index, 1)} · riesgo ${formatNumber(frame.risk_index, 1)}`;
  }
  if (frame.analysis_status === "telemetry_only") {
    return "Telemetría descriptiva · sin diagnóstico";
  }
  return frame.unavailable_reason;
}

function statusExplanation(frame: MonitoringFrame | null): string {
  if (!frame) {
    return "Ejecuta el primer paso para obtener un frame causal sincronizado.";
  }
  if (frame.analysis_status === "modeled") {
    const relation = frame.score > frame.threshold ? "supera" : "no supera";
    return `El score ${relation} el umbral congelado. La etiqueta de salud combina score, riesgo y política temporal usando únicamente el prefijo ya ejecutado.`;
  }
  if (frame.analysis_status === "telemetry_only") {
    return "Este canal aporta contexto de vibración, pero no dispone de modelo PHM. No se infiere estado de salud.";
  }
  return frame.unavailable_reason;
}

function assetAccessibleLabel(
  asset: ReplayAssetSpec,
  frame: MonitoringFrame | null,
  triggers: MonitoringTriggerEvent[],
): string {
  const triggerSummary = triggers.length
    ? `. ${triggers.length} trigger${triggers.length === 1 ? "" : "s"} en este snapshot: ${triggers.map((event) => triggerLifecycleLabel(event.lifecycle_status)).join(", ")}`
    : ". Sin triggers en este snapshot";
  return `${humanizeIdentifier(asset.asset_id)}, ${humanizeIdentifier(asset.channel_id)}, ${analysisStatusLabel(asset.analysis_status)}. ${frameHeadline(frame)}. ${frameCaption(frame)}${triggerSummary}`;
}

function frameTone(frame: MonitoringFrame | null): string {
  if (frame?.analysis_status === "modeled") {
    return `state-${frame.health_state}`;
  }
  return frame?.analysis_status === "telemetry_only" ? "state-telemetry" : "state-unavailable";
}

function triggerExecutionLabel(
  event: MonitoringTriggerEvent,
  linkedRunId: string | null,
): string {
  return `${triggerLifecycleLabel(event.lifecycle_status)} · ${linkedRunId ? "con run" : "sin run"}`;
}

function triggerRunLabel(linkedRunId: string | null): string {
  return linkedRunId ? "Run enlazada" : "Sin run enlazada";
}

function linkedChildRunId(
  events: MonitoringTriggerEvent[],
  childRuns: MonitoringChildRunAttempt[] = [],
): string | null {
  const eventRunId = [...events]
    .sort(
      (left, right) =>
        right.lifecycle_revision - left.lifecycle_revision ||
        right.sequence - left.sequence,
    )
    .find((event) => event.child_run_id !== null)?.child_run_id ?? null;
  if (eventRunId) {
    return eventRunId;
  }
  const triggerId = events[0]?.trigger_id;
  if (!triggerId) {
    return null;
  }
  return [...childRuns]
    .filter((attempt) => attempt.trigger_id === triggerId)
    .sort((left, right) => right.child_revision - left.child_revision)[0]?.child_run_id ?? null;
}

function isDispatchableTrigger(
  event: MonitoringTriggerEvent,
  linkedRunId: string | null,
  session: MonitoringSessionView,
): boolean {
  if (event.lifecycle_status !== "emitted" || linkedRunId !== null) {
    return false;
  }
  if (session.active_child_run_id !== null || session.state.active_child_run_id !== null) {
    return false;
  }
  return !session.child_runs.some((attempt) => attempt.trigger_id === event.trigger_id);
}

function latestTriggerForId(
  events: MonitoringTriggerEvent[],
  triggerId: string,
): MonitoringTriggerEvent | null {
  return [...events]
    .filter((event) => event.trigger_id === triggerId)
    .sort(
      (left, right) =>
        right.lifecycle_revision - left.lifecycle_revision ||
        right.sequence - left.sequence,
    )[0] ?? null;
}

function dispatchReceiptLabel(
  outcome: MonitoringReviewDispatchOutcome,
  error: string | null,
): string {
  if (outcome === "dispatched") {
    return "Revisión lanzada. La run agente ya está enlazada al trigger.";
  }
  if (outcome === "idempotent_replay") {
    return "Revisión ya lanzada; se ha recuperado el mismo despacho.";
  }
  return error ?? (outcome === "revision_conflict"
    ? "El ledger cambió antes del despacho."
    : "La revisión no pudo lanzarse.");
}

function isAgentRunLifecycle(
  lifecycle: MonitoringTriggerEvent["lifecycle_status"],
): lifecycle is "dispatched" | "running" | "resolved" | "failed" {
  return ["dispatched", "running", "resolved", "failed"].includes(lifecycle);
}

function agentRunCtaLabel(
  lifecycle: MonitoringTriggerEvent["lifecycle_status"],
): string {
  return {
    dispatched: "Abrir run despachada",
    running: "Ver agentes en curso",
    resolved: "Ver resultado en Agentes",
    failed: "Auditar fallo en Agentes",
    emitted: "Abrir run en Agentes",
    suppressed: "Abrir run en Agentes",
    coalesced: "Abrir run en Agentes",
  }[lifecycle];
}

function agentRunCtaAccessibleLabel(
  event: MonitoringTriggerEvent,
  linkedRunId: string,
): string {
  return `${agentRunCtaLabel(event.lifecycle_status)} para el trigger ${triggerTypeLabel(event.trigger_type)}, run ${linkedRunId}`;
}

function activationPolicyOptionLabel(kind: AgentActivationPolicyKind): string {
  return {
    P0: "P0 · observación sin triggers",
    P1: "P1 · demanda potencial",
    P2: "P2 · revisiones periódicas",
    P3: "P3 · eventos con persistencia (recomendada)",
  }[kind];
}

function formatIntervalSeconds(seconds: number): string {
  if (seconds === 0) {
    return "Sin cooldown";
  }
  if (seconds >= 60 && seconds % 60 === 0) {
    return `${formatInteger(seconds / 60)} min`;
  }
  return `${formatNumber(seconds, 0)} s`;
}

function monitoringAnnouncement(
  previousSession: MonitoringSessionView,
  tick: ReplayTick | null,
  triggers: MonitoringTriggerEvent[],
  status: MonitoringSessionView["state"]["status"],
): string | null {
  if (triggers.length === 1) {
    const event = triggers[0];
    const prefix = event.lifecycle_status === "emitted"
      ? "Nuevo trigger emitido"
      : event.lifecycle_status === "suppressed" || event.lifecycle_status === "coalesced"
        ? "Trigger registrado"
        : "Trigger actualizado";
    return `${prefix}: ${triggerTypeLabel(event.trigger_type)}, ${triggerLifecycleLabel(event.lifecycle_status)}, ${event.snapshot_end_id ?? "preflight"}.`;
  }
  if (triggers.length > 1) {
    return `${triggers.length} triggers actualizados en el snapshot ${tick?.snapshot_id ?? "actual"}.`;
  }
  const previousTick = tickAtCursor(
    previousSession.ticks,
    previousSession.state.execution_cursor,
  );
  const previousModeled = previousTick?.frames.find(
    (frame) => frame.analysis_status === "modeled",
  );
  const currentModeled = tick?.frames.find(
    (frame) => frame.analysis_status === "modeled",
  );
  if (
    previousModeled?.analysis_status === "modeled" &&
    currentModeled?.analysis_status === "modeled" &&
    previousModeled.health_state !== currentModeled.health_state
  ) {
    return `Cambio de estado: ${healthStateLabel(previousModeled.health_state)} a ${healthStateLabel(currentModeled.health_state)}.`;
  }
  if (status === "completed" && previousSession.state.status !== "completed") {
    return "Replay histórico completado.";
  }
  return null;
}

function analysisStatusLabel(status: ReplayAssetSpec["analysis_status"]): string {
  return {
    modeled: "Canal modelado",
    telemetry_only: "Solo telemetría",
    unavailable: "No disponible",
  }[status];
}

function sessionStatusLabel(status: MonitoringSessionView["state"]["status"]): string {
  return {
    ready: "Preparada",
    running: "En ejecución",
    paused: "Pausada",
    completed: "Completada",
    failed: "Fallida",
  }[status];
}

function receiptLabel(outcome: ReplayStepOutcome): string {
  return {
    applied: "Tick causal confirmado.",
    idempotent_replay: "Comando ya aplicado; se conserva el mismo tick.",
    revision_conflict: "La revisión esperaba otro estado.",
    rejected: "El paso fue rechazado.",
  }[outcome];
}

function cursorAccessibleText(tick: ReplayTick | null, totalTicks: number): string {
  if (!tick) {
    return "Replay sin iniciar";
  }
  return `Snapshot ${tick.cursor + 1} de ${totalTicks}, ${tick.snapshot_id}, tiempo fuente ${sourceTimeLabel(tick.source_time)}`;
}

function humanizeIdentifier(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function sourceTimeLabel(value: string): string {
  return value.replace("T", " ").replace(/\.\d+(?=Z|[+-]\d{2}:?\d{2}$)/, "");
}

function formatNumber(value: number, digits: number): string {
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(value);
}

function monitoringRoleLabel(role: string): string {
  return {
    supervisor: "Supervisor",
    cleaner: "Limpiador",
    structurer: "Estructurador",
    modeler: "Modelador",
    evaluator: "Evaluador",
    report_writer: "Redactor",
    report_verifier: "Verificador",
  }[role] ?? humanizeIdentifier(role);
}

function gateOutcomeLabel(outcome: string): string {
  return {
    first_pass: "primer intento",
    llm_repaired: "reparación LLM",
    fallback: "fallback",
    non_agentic: "no agéntica",
    error: "error",
    missing: "ausente",
  }[outcome] ?? humanizeIdentifier(outcome);
}

function gateActionLabel(action: string | null): string {
  if (action === null) return "sin acción";
  return {
    maintain_policy: "mantener política",
    intensify_observation: "intensificar observación",
    request_human_review: "revisión humana",
    pause_replay: "pausar replay",
    insufficient_evidence: "evidencia insuficiente",
  }[action] ?? humanizeIdentifier(action);
}

function gateCoverageLabel(kind: string): string {
  return {
    hypothesis_structure: "Hipótesis completas",
    causal_grounding: "Evidencia dentro del cutoff",
    trigger_decision_result_binding: "Trigger → decisión → resultado",
  }[kind] ?? humanizeIdentifier(kind);
}

function errorText(caught: unknown): string {
  if (caught instanceof ApiClientError) {
    if (caught.status === 404) {
      return "La API de monitorización todavía no está disponible en este backend.";
    }
    return caught.message;
  }
  return caught instanceof Error ? caught.message : "No se pudo cargar la monitorización.";
}
