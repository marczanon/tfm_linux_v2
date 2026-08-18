import {
  Activity,
  AlertTriangle,
  Box,
  Brain,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleX,
  Clock3,
  Database,
  Eye,
  FileJson,
  FileText,
  GitBranch,
  Lightbulb,
  ListChecks,
  MessageSquare,
  Network,
  Quote,
  Route,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { StatusPill } from "../common/StatusPill";
import { AgentMemoryShowcase } from "./AgentMemoryShowcase";
import { AgentMemoryPanel } from "../memory/AgentMemoryPanel";
import {
  AGENT_PROFILES,
  agentDecisionPayload,
  agentConversationMessages,
  agentEventPlainText,
  agentInitials,
  agentLabel,
  eventsForAgent,
  eventEmittingAgentId,
  eventOwnerId,
  eventRelatedAgentId,
  hasCompleteCommonHypothesisForPayload,
  kindLabel,
  hypothesisViewModelsForPayload,
  monitoringEvidenceCatalogModel,
  monitoringPolicyProposalModel,
  sourceLabel,
} from "../../lib/agentRuntime";
import { confidenceText, formatEventTime } from "../../lib/formatters";
import {
  buildAgentStoryModel,
  type AgentStoryAgent,
  type AgentStoryModel,
  type AgentStoryStep,
  type StoryAgenticState,
  type StoryMemoryState,
  type StoryMemorySummary,
  type StoryOutcomeState,
} from "../../lib/agentStory";
import type {
  AgentRuntimeEvent,
  ApiRunJobStatus,
  MemoryCollectionSummary,
  MemoryRecordSummary,
  MemoryStatusResponse,
  ReasoningMemoryRecord,
  RunSnapshot,
} from "../../types";
import type {
  AgentConversationMessage,
  AgentHypothesisViewModel,
  MonitoringEvidenceCatalogViewModel,
  MonitoringEvidenceRecordViewModel,
  MonitoringPolicyProposalContributionViewModel,
  MonitoringPolicyProposalViewModel,
} from "../../lib/agentRuntime";
import type { MonitoringAgentBridgeContext } from "../../types/ui";
import {
  triggerLifecycleGlyph,
  triggerLifecycleLabel,
  triggerTypeLabel,
} from "../monitoring/MonitoringReplayChart";

type AgentOfficeMode = "twoD" | "threeD";
type AgentWorkspaceMode = "runtime" | "memory";
type AgentNarrativeMode = "story" | "audit";

const AgentOffice3D = lazy(() =>
  import("./AgentOffice3D").then((module) => ({
    default: module.AgentOffice3D,
  })),
);

export function AgentObservabilityView({
  job,
  events,
  selectedSnapshot,
  selectedAgentId,
  onSelectAgent,
  onOpenEvidence,
  monitoringContext,
  onReturnToMonitoring,
  memoryCollections,
  memoryStatus,
  memoryRecords,
  selectedMemoryRecord,
  memorySearchText,
  loadingMemory,
  curatingMemory,
  onMemorySearchChange,
  onSelectMemoryRecord,
  onCurateMemoryRecord,
  onDeleteMemoryRecord,
}: {
  job: ApiRunJobStatus | null;
  events: AgentRuntimeEvent[];
  selectedSnapshot: RunSnapshot | null;
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
  onOpenEvidence?: () => void;
  monitoringContext?: MonitoringAgentBridgeContext | null;
  onReturnToMonitoring?: () => void;
  memoryCollections: MemoryCollectionSummary[];
  memoryStatus: MemoryStatusResponse | null;
  memoryRecords: MemoryRecordSummary[];
  selectedMemoryRecord: ReasoningMemoryRecord | null;
  memorySearchText: string;
  loadingMemory: boolean;
  curatingMemory: boolean;
  onMemorySearchChange: (value: string) => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
  onCurateMemoryRecord: (
    memoryRecordId: string,
    action: "exclude" | "restore",
  ) => void;
  onDeleteMemoryRecord: (memoryRecordId: string) => void;
}) {
  const story = useMemo(
    () => buildAgentStoryModel(events, job, selectedSnapshot),
    [events, job, selectedSnapshot],
  );
  const selectedEvents = eventsForAgent(events, selectedAgentId);
  const selectedDecisionEvents = selectedEvents.filter(isDecisionEvent);
  const [selectedDecisionEventId, setSelectedDecisionEventId] = useState<string | null>(null);
  const [selectedStoryStepId, setSelectedStoryStepId] = useState<string | null>(null);
  const selectedEvent =
    selectedDecisionEventId === UNLINKED_TIMELINE_EVENT_ID
      ? null
      : selectedDecisionEvents.find((event) => event.event_id === selectedDecisionEventId) ??
        (selectedDecisionEvents.length > 0
          ? selectedDecisionEvents[selectedDecisionEvents.length - 1]
          : null);
  const conversationMessages = agentConversationMessages(events);
  const [officeMode, setOfficeMode] = useState<AgentOfficeMode>("twoD");
  const [workspaceMode, setWorkspaceMode] = useState<AgentWorkspaceMode>("runtime");
  const [narrativeMode, setNarrativeMode] = useState<AgentNarrativeMode>("story");
  const [shouldFocusAudit, setShouldFocusAudit] = useState(false);
  const auditPanelRef = useRef<HTMLElement | null>(null);
  const monitoringContextRef = useRef<HTMLElement | null>(null);
  const showingOffice3D = officeMode === "threeD";
  const requestedStoryStepIndex = selectedStoryStepId === null
    ? -1
    : story.steps.findIndex((step) => step.id === selectedStoryStepId);
  const selectedStoryStepIndex = requestedStoryStepIndex >= 0
    ? requestedStoryStepIndex
    : Math.max(0, story.steps.length - 1);
  const selectedStoryStep = story.steps[selectedStoryStepIndex] ?? null;
  const visibleStoryEvents = useMemo(
    () => selectedStoryStepId === null || selectedStoryStep === null
      ? events
      : events.filter((event) => event.sequence <= selectedStoryStep.sequence),
    [events, selectedStoryStep?.sequence, selectedStoryStepId],
  );
  const visibleStory = useMemo(
    () => visibleStoryEvents === events
      ? story
      : buildAgentStoryModel(visibleStoryEvents, job, selectedSnapshot),
    [events, job, selectedSnapshot, story, visibleStoryEvents],
  );
  const policyProposal = useMemo(
    () => monitoringPolicyProposalModel(events),
    [events],
  );
  const visiblePolicyProposal = useMemo(
    () => monitoringPolicyProposalModel(visibleStoryEvents),
    [visibleStoryEvents],
  );
  const selectedStoryAgent = visibleStory.agents.find((agent) => agent.id === selectedAgentId)
    ?? visibleStory.agents[0];
  const selectAgent = (agentId: string) => {
    setSelectedDecisionEventId(null);
    setSelectedStoryStepId(null);
    onSelectAgent(agentId);
  };
  const selectTimelineEvent = (event: AgentRuntimeEvent) => {
    const linkedDecision = linkedDecisionEvent(events, event);
    const relatedAgentId = linkedDecision
      ? eventEmittingAgentId(linkedDecision)
      : eventRelatedAgentId(event);
    if (relatedAgentId) onSelectAgent(relatedAgentId);
    setSelectedDecisionEventId(
      linkedDecision?.event_id ?? UNLINKED_TIMELINE_EVENT_ID,
    );
    setSelectedStoryStepId(event.event_id);
  };
  const selectStoryStep = (index: number) => {
    const step = story.steps[index];
    if (step) selectTimelineEvent(step.event);
  };
  const openMemoryRecord = (memoryRecordId: string) => {
    onSelectMemoryRecord(memoryRecordId);
    setWorkspaceMode("memory");
  };
  const openAuditFromStory = () => {
    setShouldFocusAudit(true);
    setNarrativeMode("audit");
  };

  useEffect(() => {
    if (narrativeMode !== "audit" || !shouldFocusAudit) return;
    auditPanelRef.current?.focus();
    setShouldFocusAudit(false);
  }, [narrativeMode, shouldFocusAudit]);

  useEffect(() => {
    if (monitoringContext === null || monitoringContext === undefined) {
      return;
    }
    setSelectedDecisionEventId(null);
    setSelectedStoryStepId(null);
    setWorkspaceMode("runtime");
    setNarrativeMode("story");
    const frameId = window.requestAnimationFrame(() => {
      monitoringContextRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [monitoringContext?.childRunId, monitoringContext?.triggerId]);

  return (
    <section className="agent-workspace">
      {monitoringContext && onReturnToMonitoring ? (
        <section
          aria-label="Contexto de revisión desde Monitorización"
          className={`monitoring-agent-context lifecycle-${monitoringContext.triggerLifecycleAtOpen}`}
          ref={monitoringContextRef}
          tabIndex={-1}
        >
          <button
            aria-label={`Volver al trigger ${triggerTypeLabel(monitoringContext.triggerType)} en Monitorización`}
            className="secondary-button monitoring-agent-back"
            onClick={onReturnToMonitoring}
            type="button"
          >
            <ChevronLeft size={16} />Volver al trigger
          </button>
          <div className="monitoring-agent-context-main">
            <span className="eyebrow">Revisión activada por monitorización</span>
            <strong>{triggerTypeLabel(monitoringContext.triggerType)}</strong>
            <small>
              {monitoringContext.snapshotId ?? "Preflight"} · inspección {bridgeCursorLabel(monitoringContext.inspectionCursor)} · ejecución {bridgeCursorLabel(monitoringContext.executionCursorAtOpen)}
            </small>
            <small>Sesión {monitoringContext.sessionId}</small>
          </div>
          <span
            className={`monitoring-lifecycle lifecycle-${monitoringContext.triggerLifecycleAtOpen}`}
          >
            <span aria-hidden="true">
              {triggerLifecycleGlyph(monitoringContext.triggerLifecycleAtOpen)}
            </span>
            {triggerLifecycleLabel(monitoringContext.triggerLifecycleAtOpen)}
          </span>
          <div className="monitoring-agent-context-run">
            <span>Run hija</span>
            <strong>{monitoringContext.childRunId}</strong>
            <small>Enlace a nivel de run · sin decisión exacta seleccionada</small>
          </div>
        </section>
      ) : null}
      <section className="panel agent-overview-panel">
        <div className="panel-heading agent-control-heading">
          <div>
            <p className="eyebrow">Sala de control agentica</p>
            <h2>Una historia de decisiones y memoria</h2>
          </div>
          <div className="agent-overview-actions">
            {selectedSnapshot && onOpenEvidence ? (
              <button
                className="secondary-button agent-evidence-link"
                type="button"
                onClick={onOpenEvidence}
              >
                <FileText size={16} />
                Evidencia
              </button>
            ) : null}
            {workspaceMode === "runtime" ? (
              <AgentNarrativeModeToggle
                mode={narrativeMode}
                onChange={setNarrativeMode}
              />
            ) : null}
            <AgentWorkspaceModeToggle
              mode={workspaceMode}
              onChange={setWorkspaceMode}
            />
          </div>
        </div>
        <div className="agent-research-grid">
          <ResearchSignal
            icon={<Activity size={18} />}
            label="Run"
            value={`${runStoryStatusLabel(story.run.jobStatus, story.run.stage)} · ${storyTraceOriginLabel(story.run.traceOrigin)}`}
            tone={story.run.jobStatus === "failed" ? "danger" : "ok"}
          />
          <ResearchSignal
            icon={<Network size={18} />}
            label="Agentes"
            value={`${story.run.participatingAgentCount}/${AGENT_PROFILES.length}`}
            tone={story.run.participatingAgentCount === AGENT_PROFILES.length ? "ok" : "muted"}
          />
          <ResearchSignal
            icon={<Brain size={18} />}
            label="LLM primer intento"
            value={`${story.run.firstPassCount}/${story.run.decisionCount}`}
            tone={story.run.firstPassCount > 0 ? "ok" : "muted"}
          />
          <ResearchSignal
            icon={<AlertTriangle size={18} />}
            label="Excepciones"
            value={`${story.run.fallbackCount} fallback · ${story.run.errorCount} error`}
            tone={story.run.fallbackCount > 0 || story.run.errorCount > 0 ? "danger" : "ok"}
          />
          <ResearchSignal
            icon={<Database size={18} />}
            label="Memoria RAG"
            value={`${story.run.memory.retrievedCount} rec. · ${story.run.memory.usedCount} usada`}
            tone={story.run.memory.usedCount > 0 ? "ok" : story.run.memory.retrievedCount > 0 ? "neutral" : "muted"}
          />
          <ResearchSignal
            icon={story.run.approved === false ? <CircleX size={18} /> : <CircleCheck size={18} />}
            label="Resultado"
            value={runApprovalLabel(story.run.approved)}
            tone={story.run.approved === false ? "danger" : story.run.approved === true ? "ok" : "muted"}
          />
        </div>
        <p className="agent-story-method-note">
          Vista narrativa de eventos registrados. Recuperar no significa usar y ejecutar
          correctamente no confirma por si solo una hipotesis.
        </p>
      </section>

      {workspaceMode === "memory" ? (
        <AgentMemoryShowcase
          events={events}
          selectedAgentId={selectedAgentId}
          memoryCollections={memoryCollections}
          memoryStatus={memoryStatus}
          memoryRecords={memoryRecords}
          selectedMemoryRecord={selectedMemoryRecord}
          memorySearchText={memorySearchText}
          loadingMemory={loadingMemory}
          curatingMemory={curatingMemory}
          onSelectAgent={selectAgent}
          onMemorySearchChange={onMemorySearchChange}
          onSelectMemoryRecord={onSelectMemoryRecord}
          onCurateMemoryRecord={onCurateMemoryRecord}
          onDeleteMemoryRecord={onDeleteMemoryRecord}
        />
      ) : narrativeMode === "story" ? (
        <div className="agent-story-workspace">
          <section className={`panel agent-story-map-panel ${showingOffice3D ? "showing-3d" : ""}`}>
            <div className="panel-heading agent-story-panel-heading">
              <div>
                <p className="eyebrow">Historia de la run</p>
                <h2>{showingOffice3D ? "Replay visual 3D" : "Los siete agentes"}</h2>
              </div>
              <AgentOfficeModeToggle mode={officeMode} onChange={setOfficeMode} />
            </div>
            {showingOffice3D ? (
              <Suspense fallback={<p className="empty-state compact-empty">Preparando oficina 3D</p>}>
                <AgentOffice3D
                  events={visibleStoryEvents}
                  selectedAgentId={selectedAgentId}
                  onSelectAgent={selectAgent}
                />
              </Suspense>
            ) : (
              <AgentStoryMap
                agents={visibleStory.agents}
                selectedAgentId={selectedAgentId}
                onSelectAgent={selectAgent}
              />
            )}
            <div className="agent-story-legend" aria-label="Leyenda de relaciones">
              <span><i className="route" /> secuencia observada</span>
              <span><i className="memory" /> contexto RAG</span>
              <span><i className="result" /> resultado enlazado</span>
            </div>
          </section>

          <section className="panel agent-story-inspector-panel">
            <AgentStoryInspector
              agent={selectedStoryAgent}
              policyProposal={visiblePolicyProposal}
              onOpenAudit={openAuditFromStory}
              onOpenEvidence={selectedSnapshot && onOpenEvidence ? onOpenEvidence : undefined}
              onSelectMemoryRecord={openMemoryRecord}
            />
          </section>

          <section className="panel agent-story-playback-panel">
            <AgentStoryPlayback
              currentIndex={selectedStoryStepIndex}
              onSelectIndex={selectStoryStep}
              steps={story.steps}
            />
          </section>
        </div>
      ) : (
        <div className="agent-audit-workspace">
          <section
            aria-label="Auditoria exacta"
            className="panel agent-audit-mode-panel"
            ref={auditPanelRef}
            tabIndex={-1}
          >
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Auditoria exacta</p>
                <h2>Cobertura y procedencia</h2>
              </div>
              <ShieldCheck size={20} />
            </div>
            <AgentAuditEvidenceDashboard events={events} />
          </section>

          <section className="panel agent-detail-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Decision completa</p>
                <h2>{agentLabel(selectedAgentId)}</h2>
              </div>
              <Brain size={20} />
            </div>
            <AgentRuntimeDetail
              event={selectedEvent}
              eventCount={selectedDecisionEvents.length}
              policyProposal={policyProposal}
              onSelectMemoryRecord={onSelectMemoryRecord}
            />
            <AgentMemoryPanel
              agentId={selectedAgentId}
              events={selectedEvents}
              collections={memoryCollections}
              records={memoryRecords}
              selectedRecord={selectedMemoryRecord}
              searchText={memorySearchText}
              loading={loadingMemory}
              curating={curatingMemory}
              onSearchChange={onMemorySearchChange}
              onSelectRecord={onSelectMemoryRecord}
              onCurateRecord={onCurateMemoryRecord}
              onDeleteRecord={onDeleteMemoryRecord}
            />
          </section>

          <section className="panel timeline-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Timeline</p>
                <h2>Eventos reales</h2>
              </div>
              <Clock3 size={20} />
            </div>
            <AgentRuntimeTimeline
              events={events}
              selectedDecisionEventId={selectedEvent?.event_id ?? null}
              onSelectEvent={selectTimelineEvent}
            />
          </section>

          <section className="panel conversation-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Comunicacion</p>
                <h2>Conversacion</h2>
              </div>
              <MessageSquare size={20} />
            </div>
            <AgentConversation messages={conversationMessages} onSelectAgent={selectAgent} />
          </section>
        </div>
      )}
    </section>
  );
}

function AgentNarrativeModeToggle({
  mode,
  onChange,
}: {
  mode: AgentNarrativeMode;
  onChange: (mode: AgentNarrativeMode) => void;
}) {
  return (
    <div className="visual-mode-toggle agent-narrative-mode-toggle" aria-label="Profundidad de lectura" role="group">
      <button
        aria-pressed={mode === "story"}
        className={mode === "story" ? "active" : ""}
        onClick={() => onChange("story")}
        title="Vista resumida de la historia"
        type="button"
      >
        <Eye size={15} />
        <span>Historia</span>
      </button>
      <button
        aria-pressed={mode === "audit"}
        className={mode === "audit" ? "active" : ""}
        onClick={() => onChange("audit")}
        title="Abrir la traza tecnica exacta"
        type="button"
      >
        <ShieldCheck size={15} />
        <span>Auditoria</span>
      </button>
    </div>
  );
}

function AgentStoryMap({
  agents,
  selectedAgentId,
  onSelectAgent,
}: {
  agents: AgentStoryAgent[];
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
}) {
  const supervisor = agents.find((agent) => agent.id === "supervisor");
  const specialists = agents.filter((agent) => agent.id !== "supervisor");
  return (
    <div className="agent-story-map" aria-label="Mapa resumido de agentes" role="group">
      {supervisor ? (
        <div className="agent-story-supervisor">
          <AgentStoryCard
            agent={supervisor}
            selected={selectedAgentId === supervisor.id}
            onSelect={() => onSelectAgent(supervisor.id)}
          />
          <span className="agent-story-delegation" aria-hidden="true">
            <i />
            delega y cierra
            <i />
          </span>
        </div>
      ) : null}
      <div className="agent-story-specialists">
        {specialists.map((agent, index) => (
          <div className="agent-story-specialist" key={agent.id}>
            <AgentStoryCard
              agent={agent}
              selected={selectedAgentId === agent.id}
              onSelect={() => onSelectAgent(agent.id)}
            />
            {index < specialists.length - 1
              && agent.decisionCount > 0
              && specialists[index + 1].decisionCount > 0 ? (
              <span className="agent-story-flow-arrow" aria-hidden="true">→</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentStoryCard({
  agent,
  selected,
  onSelect,
}: {
  agent: AgentStoryAgent;
  selected: boolean;
  onSelect: () => void;
}) {
  const hypothesis = agent.primaryHypothesis;
  const stateTone = storyAgenticTone(agent.agenticState);
  const hasAttention = stateTone === "danger" || stateTone === "warning";
  return (
    <button
      aria-label={agentStoryCardAccessibleLabel(agent)}
      aria-pressed={selected}
      className={`agent-story-card agent-tone-${agent.id} ${selected ? "selected" : ""} ${hasAttention ? "attention" : ""}`}
      onClick={onSelect}
      type="button"
    >
      <span className="agent-story-card-head">
        <span className="agent-story-avatar">
          {agent.id === "supervisor" ? <Network size={17} /> : <Brain size={17} />}
        </span>
        <span className="agent-story-identity">
          <strong>{agent.label}</strong>
          <small>{agent.role}</small>
        </span>
        <em className={`agent-story-state tone-${stateTone}`}>
          {storyAgenticLabel(agent.agenticState, agent.decisionCount)}
        </em>
      </span>
      <span className="agent-story-hypothesis">
        <Lightbulb size={14} />
        <span>
          <small>
            {hypothesis
              ? hypothesisAssessmentLabel(hypothesis.assessmentStatus)
              : agent.decisionCount > 0 ? "Cobertura incompleta" : "Sin participacion"}
          </small>
          <strong>
            {hypothesis?.statement
              ?? (agent.decisionCount > 0
                ? "La decision historica no conserva una hipotesis estructurada."
                : "No participo en el tramo observado.")}
          </strong>
        </span>
      </span>
      <span className="agent-story-decision" title={agent.decisionLabel}>
        {agent.decisionLabel}
      </span>
      <span className="agent-story-card-signals">
        <span className={`memory-${agent.memory.state}`} title={storyMemoryLabel(agent.memory)}>
          <Database size={13} /> {storyMemoryShortLabel(agent.memory)}
        </span>
        <span className={`outcome-${agent.outcome.state}`} title={agent.outcome.label}>
          {agent.outcome.state === "failed" || agent.outcome.state === "blocked"
            ? <CircleX size={13} />
            : <CircleCheck size={13} />}
          {storyOutcomeShortLabel(agent.outcome.state)}
        </span>
      </span>
    </button>
  );
}

function AgentStoryInspector({
  agent,
  policyProposal,
  onOpenAudit,
  onOpenEvidence,
  onSelectMemoryRecord,
}: {
  agent: AgentStoryAgent;
  policyProposal: MonitoringPolicyProposalViewModel | null;
  onOpenAudit: () => void;
  onOpenEvidence?: () => void;
  onSelectMemoryRecord: (memoryRecordId: string) => void;
}) {
  const hypothesis = agent.primaryHypothesis;
  const policyContribution = policyProposal?.contributions.find(
    (item) => item.agentId === agent.id,
  ) ?? null;
  const memoryIds = agent.memory.usedIds.length > 0
    ? agent.memory.usedIds
    : agent.memory.retrievedIds;
  const inspectorHeadingId = `agent-story-inspector-${agent.id}`;
  return (
    <div
      aria-atomic="false"
      aria-labelledby={inspectorHeadingId}
      aria-live="polite"
      className={`agent-story-inspector agent-tone-${agent.id}`}
      role="region"
    >
      <header className="agent-story-inspector-head">
        <span className="agent-story-inspector-avatar">
          {agent.id === "supervisor" ? <Network size={21} /> : <Brain size={21} />}
        </span>
        <span>
          <small>{agent.role}</small>
          <strong aria-level={3} id={inspectorHeadingId} role="heading">
            {agent.label}
          </strong>
        </span>
        <em className={`agent-story-state tone-${storyAgenticTone(agent.agenticState)}`}>
          {storyAgenticLabel(agent.agenticState, agent.decisionCount)}
        </em>
      </header>

      <div className="agent-story-inspector-block hypothesis">
        <span><Lightbulb size={15} /> Cree</span>
        <strong>
          {hypothesis?.statement
            ?? (agent.decisionCount > 0
              ? "No consta una hipotesis estructurada para esta decision."
              : "Este rol aun no ha participado en el tramo observado.")}
        </strong>
        {hypothesis ? <em>{hypothesisAssessmentLabel(hypothesis.assessmentStatus)}</em> : null}
      </div>

      <div className="agent-story-inspector-block decision">
        <span><GitBranch size={15} /> Elige</span>
        <strong>{agent.decisionLabel}</strong>
      </div>

      {policyContribution && policyProposal ? (
        <MonitoringPolicyContributionCard
          contribution={policyContribution}
          proposal={policyProposal}
        />
      ) : null}

      <div className="agent-story-inspector-block memory">
        <span><Database size={15} /> Recuerda</span>
        <strong>{storyMemoryLabel(agent.memory)}</strong>
        <AgentStoryMemoryFlow memory={agent.memory} />
        {memoryIds.length > 0 ? (
          <div className="agent-story-memory-capsules">
            {memoryIds.slice(0, 3).map((memoryId) => (
              <button
                key={memoryId}
                onClick={() => onSelectMemoryRecord(memoryId)}
                title={memoryId}
                type="button"
              >
                <Quote size={12} /> {compactAuditText(memoryId, 32)}
              </button>
            ))}
            {memoryIds.length > 3 ? <span>+{memoryIds.length - 3}</span> : null}
          </div>
        ) : null}
      </div>

      <div className={`agent-story-inspector-block outcome outcome-${agent.outcome.state}`}>
        <span><Wrench size={15} /> Ocurre</span>
        <strong>{agent.outcome.label}</strong>
        <em>{agent.outcome.linked ? "Enlace exacto registrado" : "Sin enlace verificable"}</em>
      </div>

      {hypothesis?.expectedObservation || hypothesis?.falsificationCriterion ? (
        <details className="compact-disclosure agent-story-contrast">
          <summary>Como se contrasta la hipotesis</summary>
          {hypothesis.expectedObservation ? (
            <div>
              <span>Esperaria observar</span>
              <p>{hypothesis.expectedObservation}</p>
            </div>
          ) : null}
          {hypothesis.falsificationCriterion ? (
            <div>
              <span>Se refutaria si</span>
              <p>{hypothesis.falsificationCriterion}</p>
            </div>
          ) : null}
        </details>
      ) : null}

      <div className="agent-story-inspector-actions">
        <button className="secondary-button" onClick={onOpenAudit} type="button">
          <ShieldCheck size={15} /> Auditar traza
        </button>
        {onOpenEvidence ? (
          <button className="secondary-button" onClick={onOpenEvidence} type="button">
            <FileText size={15} /> Abrir informe
          </button>
        ) : null}
      </div>
    </div>
  );
}

function AgentStoryMemoryFlow({ memory }: { memory: StoryMemorySummary }) {
  const steps = [
    { label: "Consulta", value: memory.contextCount, active: memory.contextCount > 0 },
    { label: "Recupera", value: memory.retrievedCount, active: memory.retrievedCount > 0 },
    { label: "Usa", value: memory.usedCount, active: memory.usedCount > 0 },
    { label: "No usa", value: memory.ignoredCount, active: memory.ignoredCount > 0 || memory.state === "rejected_by_agent" },
  ];
  return (
    <div className="agent-story-memory-flow" aria-label="Flujo de memoria de la decision">
      {steps.map((step, index) => (
        <span className={step.active ? "active" : "idle"} key={step.label}>
          <small>{step.label}</small>
          <strong>{step.value}</strong>
          {index < steps.length - 1 ? <i aria-hidden="true">→</i> : null}
        </span>
      ))}
      {memory.filteredCount > 0 ? (
        <em>{memory.filteredCount} filtrada(s) antes del agente</em>
      ) : null}
    </div>
  );
}

function AgentStoryPlayback({
  currentIndex,
  onSelectIndex,
  steps,
}: {
  currentIndex: number;
  onSelectIndex: (index: number) => void;
  steps: AgentStoryStep[];
}) {
  if (steps.length === 0) {
    return <p className="empty-state compact-empty">Sin eventos para reconstruir la historia</p>;
  }
  const safeIndex = Math.min(Math.max(currentIndex, 0), steps.length - 1);
  const current = steps[safeIndex];
  const counts = {
    decisions: steps.filter((step) => step.kind === "agent_decision" || step.kind === "supervisor_decision").length,
    memory: steps.filter((step) => step.kind === "memory_retrieval").length,
    results: steps.filter((step) => step.kind === "executor_result").length,
  };
  return (
    <div className="agent-story-playback">
      <div className="agent-story-playback-heading">
        <div>
          <p className="eyebrow">Recorrido interactivo</p>
          <strong>Evento {safeIndex + 1} de {steps.length}</strong>
        </div>
        <div className="agent-story-playback-counts">
          <span>{counts.decisions} decisiones</span>
          <span>{counts.memory} eventos RAG</span>
          <span>{counts.results} resultados</span>
        </div>
      </div>
      <div className="agent-story-scrubber">
        <button
          aria-label="Evento anterior"
          disabled={safeIndex === 0}
          onClick={() => onSelectIndex(safeIndex - 1)}
          type="button"
        >
          <ChevronLeft size={17} />
        </button>
        <input
          aria-label="Seleccionar evento de la historia"
          aria-valuetext={`Evento ${safeIndex + 1} de ${steps.length}: ${current.label}`}
          max={steps.length - 1}
          min={0}
          onChange={(event) => onSelectIndex(Number(event.target.value))}
          step={1}
          type="range"
          value={safeIndex}
        />
        <button
          aria-label="Evento siguiente"
          disabled={safeIndex === steps.length - 1}
          onClick={() => onSelectIndex(safeIndex + 1)}
          type="button"
        >
          <ChevronRight size={17} />
        </button>
      </div>
      <button
        className={`agent-story-current-event kind-${current.kind}`}
        onClick={() => onSelectIndex(safeIndex)}
        type="button"
      >
        <span>#{current.sequence}</span>
        <span>
          <strong>{current.label}</strong>
          <small>{current.event.summary}</small>
        </span>
        <em>{current.stage?.replace(/_/g, " ") ?? current.kind.replace(/_/g, " ")}</em>
      </button>
    </div>
  );
}

function agentStoryCardAccessibleLabel(agent: AgentStoryAgent): string {
  const hypothesis = agent.primaryHypothesis;
  const hypothesisLabel = hypothesis?.statement
    ?? (agent.decisionCount > 0
      ? "No consta una hipotesis estructurada."
      : "Sin participacion en el tramo observado.");
  return [
    `${agent.label}: ${agent.role}.`,
    `Estado agentico: ${storyAgenticLabel(agent.agenticState, agent.decisionCount)}.`,
    `Hipotesis: ${hypothesisLabel}`,
    `Decision: ${agent.decisionLabel}.`,
    `Memoria: ${storyMemoryLabel(agent.memory)}`,
    `Resultado: ${agent.outcome.label}.`,
  ].join(" ");
}

function runStoryStatusLabel(status: string, stage: string | null): string {
  if (status !== "unknown") return status.replace(/_/g, " ");
  return stage?.replace(/_/g, " ") ?? "sin ejecucion";
}

function storyTraceOriginLabel(origin: AgentStoryModel["run"]["traceOrigin"]): string {
  const labels: Record<AgentStoryModel["run"]["traceOrigin"], string> = {
    empty: "sin traza",
    live: "viva",
    persisted: "runtime exacto",
    reconstructed: "reconstruida",
  };
  return labels[origin];
}

function bridgeCursorLabel(cursor: number | null): string {
  return cursor === null ? "preflight" : String(cursor + 1);
}

function runApprovalLabel(approved: boolean | null): string {
  if (approved === true) return "Aprobada";
  if (approved === false) return "No aprobada";
  return "Sin veredicto";
}

function storyAgenticLabel(state: StoryAgenticState, decisionCount: number): string {
  if (decisionCount === 0) return "Sin decision";
  const labels: Record<StoryAgenticState, string> = {
    llm_first_pass: "LLM · 1er intento",
    llm_repaired: "LLM · reparada",
    llm_protocol_restricted: "LLM · protocolo",
    llm_with_overlay: "LLM + overlay",
    fallback: "Fallback",
    non_agentic: "No agentica",
    unknown: "Origen incompleto",
  };
  return labels[state];
}

function storyAgenticTone(state: StoryAgenticState): "ok" | "warning" | "danger" | "muted" {
  if (state === "fallback" || state === "non_agentic") return "danger";
  if (state === "llm_repaired" || state === "llm_protocol_restricted" || state === "llm_with_overlay") return "warning";
  if (state === "llm_first_pass") return "ok";
  return "muted";
}

function storyMemoryShortLabel(memory: StoryMemorySummary): string {
  if (memory.state === "used") return `${memory.usedCount} usada`;
  if (memory.state === "returned" || memory.state === "rejected_by_agent") {
    return `${memory.retrievedCount} recuperada`;
  }
  if (memory.state === "returned_empty") return "sin candidatos";
  if (memory.state === "unavailable") return "sin contexto";
  if (memory.state === "requested") return "consultando";
  if (memory.state === "inconsistent") return "inconsistente";
  return "sin contexto";
}

function storyMemoryLabel(memory: StoryMemorySummary): string {
  const labels: Record<StoryMemoryState, string> = {
    not_observed: "No recibio contexto RAG en la traza seleccionada.",
    unavailable: "No se dispuso de contexto RAG.",
    requested: "La consulta RAG quedo registrada, aun sin resultado final.",
    returned: `${memory.retrievedCount} recuerdo(s) recuperado(s); no consta uso.` ,
    returned_empty: "La consulta no devolvio recuerdos utilizables.",
    used: `${memory.retrievedCount} recuperado(s) y ${memory.usedCount} utilizado(s).`,
    rejected_by_agent: `${memory.retrievedCount} recuperado(s); el agente no los utilizo.`,
    inconsistent: "Se declaro uso, pero faltan identificadores de recuerdos citados.",
  };
  return labels[memory.state];
}

function storyOutcomeShortLabel(state: StoryOutcomeState): string {
  const labels: Record<StoryOutcomeState, string> = {
    success: "resultado OK",
    failed: "resultado fallido",
    approved: "aprobada",
    not_approved: "no aprobada",
    needs_revision: "revision",
    blocked: "bloqueada",
    routed: "enrutada",
    closed: "cerrada",
    pending: "pendiente",
    unknown: "sin estado",
  };
  return labels[state];
}

function AgentWorkspaceModeToggle({
  mode,
  onChange,
}: {
  mode: AgentWorkspaceMode;
  onChange: (mode: AgentWorkspaceMode) => void;
}) {
  return (
    <div className="visual-mode-toggle agent-workspace-mode-toggle" aria-label="Vista agentica" role="group">
      <button
        aria-pressed={mode === "runtime"}
        className={mode === "runtime" ? "active" : ""}
        onClick={() => onChange("runtime")}
        title="Mostrar runtime agentico"
        type="button"
      >
        <Activity size={15} />
        <span>Runtime</span>
      </button>
      <button
        aria-pressed={mode === "memory"}
        className={mode === "memory" ? "active" : ""}
        onClick={() => onChange("memory")}
        title="Mostrar memoria agentica"
        type="button"
      >
        <Brain size={15} />
        <span>Memoria</span>
      </button>
    </div>
  );
}

function AgentOfficeModeToggle({
  mode,
  onChange,
}: {
  mode: AgentOfficeMode;
  onChange: (mode: AgentOfficeMode) => void;
}) {
  return (
    <div className="visual-mode-toggle agent-office-mode-toggle" aria-label="Modo de oficina agentica" role="group">
      <button
        aria-pressed={mode === "twoD"}
        className={mode === "twoD" ? "active" : ""}
        onClick={() => onChange("twoD")}
        title="Mostrar oficina 2D"
        type="button"
      >
        <Network size={15} />
        <span>2D</span>
      </button>
      <button
        aria-pressed={mode === "threeD"}
        className={mode === "threeD" ? "active" : ""}
        onClick={() => onChange("threeD")}
        title="Mostrar oficina 3D"
        type="button"
      >
        <Box size={15} />
        <span>3D</span>
      </button>
    </div>
  );
}

function ResearchSignal({
  icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "danger" | "muted";
}) {
  return (
    <article className={`agent-research-signal tone-${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

type AuditCoverageSignal = {
  label: string;
  value: number;
  total: number;
  detail: string;
};

type AuditGenerationOrigin =
  | "llm"
  | "deterministic"
  | "guardrail_fallback"
  | "protocol_restricted"
  | "unknown";

type AgentRoleAudit = {
  agentId: string;
  label: string;
  role: string;
  decisionCount: number;
  latestDecisionId: string | null;
  focusLabel: string;
  focusText: string;
  chosenDecision: string;
  hypothesisCount: number;
  alternativeCount: number;
  evidenceCount: number;
  toolClaimCount: number;
  executorLinkExpected: boolean;
  executorLinked: boolean;
  traceLabel: string;
  traceTone: "ok" | "warning" | "danger" | "muted";
  exactTraceCount: number;
  firstPassCount: number;
  fallbackCount: number;
  inferredFallbackCount: number;
  repairedCount: number;
  nonAgenticCount: number;
  policyOverlayCount: number;
  protocolRestrictedCount: number;
  protocolRestricted: boolean;
  limitation: string | null;
};

type AgentAuditSummary = {
  decisionCount: number;
  completeHypothesisCount: number;
  participatingAgentCount: number;
  supervisorDecisionCount: number;
  roleDecisionCount: number;
  executorCount: number;
  executorLinkExpectedCount: number;
  executorLinkedDecisionCount: number;
  evaluationCount: number;
  exactTraceCount: number;
  firstPassCount: number;
  fallbackCount: number;
  inferredFallbackCount: number;
  repairedCount: number;
  nonAgenticCount: number;
  failedDecisionCount: number;
  policyOverlayCount: number;
  protocolRestrictedCount: number;
  unknownTraceCount: number;
  toolClaimCount: number;
  toolObservationCount: number;
  unobservedToolClaimCount: number;
  origin: "live" | "persisted" | "reconstructed" | "empty";
  originCounts: Record<AuditGenerationOrigin, number>;
  roleAudits: AgentRoleAudit[];
  coverage: AuditCoverageSignal[];
  gaps: string[];
};

const UNLINKED_TIMELINE_EVENT_ID = "__unlinked_timeline_event__";
const EXECUTOR_DECISION_AGENTS = new Set([
  "cleaner",
  "structurer",
  "modeler",
  "report_writer",
]);

type DecisionAgenticState = {
  primaryTrace: Record<string, unknown> | null;
  proposalTrace: Record<string, unknown> | null;
  firstPass: boolean;
  repaired: boolean;
  fallback: boolean;
  nonAgentic: boolean;
  protocolRestricted: boolean;
  policyOverlay: boolean;
};

function isDecisionEvent(event: AgentRuntimeEvent): boolean {
  return event.kind === "agent_decision" || event.kind === "supervisor_decision";
}

function linkedDecisionEvent(
  events: AgentRuntimeEvent[],
  event: AgentRuntimeEvent,
): AgentRuntimeEvent | null {
  if (isDecisionEvent(event)) return event;
  const linkedIds = eventDecisionLinkIds(event);
  if (linkedIds.length === 0) return null;
  return events.find(
    (candidate) =>
      isDecisionEvent(candidate) &&
      candidate.decision_id !== null &&
      linkedIds.includes(candidate.decision_id),
  ) ?? null;
}

function eventDecisionLinkIds(event: AgentRuntimeEvent): string[] {
  const toolObservation = auditRecord(event.payload.tool_observation);
  return [
    event.decision_id,
    event.payload.decision_id,
    event.payload.source_decision_id,
    event.payload.agent_decision_id,
    toolObservation?.decision_id,
    toolObservation?.source_decision_id,
  ].filter(
    (value): value is string => typeof value === "string" && value.trim().length > 0,
  );
}

function AgentAuditEvidenceDashboard({ events }: { events: AgentRuntimeEvent[] }) {
  const audit = buildAgentAuditSummary(events);
  const hasExactRuntimeTrace = audit.origin === "live" || audit.origin === "persisted";
  const originLabel =
    audit.origin === "reconstructed"
      ? "Traza reconstruida"
      : audit.origin === "persisted"
        ? "Runtime persistido"
        : audit.origin === "live"
          ? "Runtime en directo"
          : "Sin traza";
  const conclusion = auditConclusion(audit);
  const flow = [
    { label: "Rutas supervisor", value: String(audit.supervisorDecisionCount), observed: audit.supervisorDecisionCount > 0 },
    { label: "Decisiones de rol", value: String(audit.roleDecisionCount), observed: audit.roleDecisionCount > 0 },
    { label: "Intento logico 1", value: String(audit.firstPassCount), observed: audit.firstPassCount > 0 },
    { label: "Reparacion LLM", value: String(audit.repairedCount), observed: audit.repairedCount > 0 },
    {
      label: hasExactRuntimeTrace ? "Fallback" : "Fallback legado",
      value: hasExactRuntimeTrace ? String(audit.fallbackCount) : `~${audit.inferredFallbackCount}`,
      observed: hasExactRuntimeTrace
        ? audit.fallbackCount > 0
        : audit.inferredFallbackCount > 0,
    },
    { label: "No agenticas", value: String(audit.nonAgenticCount), observed: audit.nonAgenticCount > 0 },
    {
      label: "Protocolo / overlay",
      value: `${audit.protocolRestrictedCount}/${audit.policyOverlayCount}`,
      observed: audit.protocolRestrictedCount > 0 || audit.policyOverlayCount > 0,
    },
    { label: "Eventos ejecutor", value: String(audit.executorCount), observed: audit.executorCount > 0 },
  ];

  return (
    <section className={`agent-audit-dashboard origin-${audit.origin}`}>
      <div className="agent-audit-heading">
        <div>
          <span className="agent-audit-kicker">
            <ShieldCheck size={15} /> Auditabilidad de la run
          </span>
          <strong>{conclusion.title}</strong>
          <p>{conclusion.detail}</p>
        </div>
        <span className={`agent-trace-origin ${audit.origin}`}>{originLabel}</span>
      </div>

      <div className="agent-evidence-flow" aria-label="Flujo de evidencia agentica">
        {flow.map((item) => (
          <div className={`agent-evidence-step ${item.observed ? "observed" : "missing"}`} key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>

      <div className="agent-audit-visual-grid">
        <section className="agent-coverage-chart">
          <div className="agent-audit-subheading">
            <GitBranch size={15} />
            <span>Cobertura de decisiones observadas</span>
          </div>
          <div className="agent-coverage-axis" aria-hidden="true">
            <span>0%</span><span>50%</span><span>100%</span>
          </div>
          {audit.coverage.map((item) => {
            const ratio = item.total === 0 ? 0 : item.value / item.total;
            return (
              <div className="agent-coverage-row" key={item.label}>
                <span>{item.label}</span>
                <div className="agent-coverage-track" title={item.detail}>
                  <i style={{ width: `${Math.round(ratio * 100)}%` }} />
                </div>
                <strong>{item.value}/{item.total}</strong>
              </div>
            );
          })}
        </section>

        <section className="agent-origin-chart">
          <div className="agent-audit-subheading">
            <ShieldCheck size={15} />
            <span>Estado agentico observable</span>
          </div>
          <OriginBar label="Intento logico 1" value={audit.firstPassCount} max={audit.decisionCount} tone="llm" />
          <OriginBar label="Reparacion LLM" value={audit.repairedCount} max={audit.decisionCount} tone="repaired" />
          <OriginBar label="Fallback" value={audit.fallbackCount} max={audit.decisionCount} tone="fallback" />
          <OriginBar label="No agentica" value={audit.nonAgenticCount} max={audit.decisionCount} tone="nonagentic" />
          <OriginBar label="Protocolo fijo" value={audit.protocolRestrictedCount} max={audit.decisionCount} tone="protocol" />
          <OriginBar label="Overlay" value={audit.policyOverlayCount} max={audit.decisionCount} tone="overlay" />
          <p>
            Las categorias de protocolo y overlay pueden solaparse con una propuesta LLM.
            Una reparacion sigue siendo agentica; fallback, overlay o salida no agentica
            impiden superar la puerta de validacion.
          </p>
        </section>
      </div>

      <section className="agent-role-audit" aria-label="Auditoria por rol">
        <div className="agent-audit-subheading">
          <Brain size={15} />
          <span>Lectura por rol</span>
        </div>
        <div className="agent-role-audit-grid">
          {audit.roleAudits.map((roleAudit) => (
            <AgentRoleAuditCard audit={roleAudit} key={roleAudit.agentId} />
          ))}
        </div>
      </section>

      {audit.gaps.length > 0 ? (
        <div className="agent-audit-gaps">
          <strong>Limites visibles</strong>
          <div>
            {audit.gaps.slice(0, 4).map((gap) => <span key={gap}>{gap}</span>)}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function OriginBar({
  label,
  value,
  max,
  tone,
}: {
  label: string;
  value: number;
  max: number;
  tone: "llm" | "repaired" | "fallback" | "nonagentic" | "protocol" | "overlay";
}) {
  const width = max === 0 || value === 0 ? 0 : Math.max(8, Math.round((value / max) * 100));
  return (
    <div className={`agent-origin-row tone-${tone}`}>
      <span>{label}</span>
      <div><i style={{ width: `${width}%` }} /></div>
      <strong>{value}</strong>
    </div>
  );
}

function AgentRoleAuditCard({ audit }: { audit: AgentRoleAudit }) {
  return (
    <article className={`agent-role-audit-card tone-${audit.traceTone}`}>
      <header>
        <div>
          <span>{audit.role}</span>
          <strong>{audit.label}</strong>
        </div>
        <span className={`agent-role-origin tone-${audit.traceTone}`}>{audit.traceLabel}</span>
      </header>
      <div className="agent-role-decision-focus">
        <span>{audit.focusLabel}</span>
        <p>{audit.focusText}</p>
      </div>
      <div className="agent-role-choice">
        <span>Decision observable</span>
        <strong>{audit.chosenDecision}</strong>
      </div>
      <div className="agent-role-facts">
        <span>{audit.decisionCount} decisiones</span>
        <span>{audit.hypothesisCount} hipotesis completas</span>
        <span>{audit.alternativeCount} alternativas</span>
        <span>{audit.evidenceCount} refs. evidencia</span>
        <span>{audit.toolClaimCount} herr. declaradas</span>
      </div>
      <div className="agent-role-state-row">
        {audit.executorLinkExpected ? (
          <span className={audit.executorLinked ? "ok" : "danger"}>
            {audit.executorLinked ? "Accion enlazada a ejecutor" : "Accion sin ejecutor enlazado"}
          </span>
        ) : (
          <span className="muted">Sin ejecutor propio esperado</span>
        )}
        {audit.firstPassCount > 0 ? <span className="ok">LLM intento logico 1 · {audit.firstPassCount}</span> : null}
        {audit.protocolRestricted ? <span className="protocol">Configuracion fijada por protocolo</span> : null}
        {audit.repairedCount > 0 ? <span className="warning">Reparacion LLM observada</span> : null}
        {audit.policyOverlayCount > 0 ? <span className="warning">Salida LLM completada por guardarrail</span> : null}
        {audit.fallbackCount > 0 ? <span className="danger">Fallback trazado</span> : null}
        {audit.nonAgenticCount > 0 ? <span className="danger">Salida no agentica</span> : null}
        {audit.inferredFallbackCount > 0 ? <span className="warning">Fallback legacy inferido</span> : null}
      </div>
      {audit.limitation ? <p className="agent-role-limitation">{audit.limitation}</p> : null}
      {audit.latestDecisionId ? <small title={audit.latestDecisionId}>ID: {audit.latestDecisionId}</small> : null}
    </article>
  );
}

function buildAgentAuditSummary(events: AgentRuntimeEvent[]): AgentAuditSummary {
  const decisions = events.filter(
    (event) => event.kind === "agent_decision" || event.kind === "supervisor_decision",
  );
  const decisionPayloads = decisions.map(decisionPayload);
  const supervisorDecisions = decisions.filter((event) => event.kind === "supervisor_decision");
  const roleDecisions = decisions.filter((event) => event.kind === "agent_decision");
  const configurablePayloads = decisions
    .filter((event) => event.agent_name === "structurer" || event.agent_name === "modeler")
    .map(decisionPayload);
  const nonSupervisorPayloads = decisions
    .filter((event) => event.kind === "agent_decision")
    .map(decisionPayload);
  const generationTraces = decisionPayloads.map(primaryGenerationTrace);
  const agenticStates = decisionPayloads.map(decisionAgenticState);
  const exactTraceCount = generationTraces.filter((trace) => trace !== null).length;
  const originCounts: Record<AuditGenerationOrigin, number> = {
    llm: 0,
    deterministic: 0,
    guardrail_fallback: 0,
    protocol_restricted: 0,
    unknown: 0,
  };
  for (const trace of generationTraces) {
    const origin = generationOrigin(trace);
    originCounts[origin] += 1;
  }
  const inferredFallbackCount = decisions.filter(
    (event, index) => !agenticStates[index].fallback && hasLegacyFallbackSignal(event),
  ).length;
  const firstPassCount = agenticStates.filter((state) => state.firstPass).length;
  const repairedCount = agenticStates.filter((state) => state.repaired).length;
  const fallbackCount = agenticStates.filter((state) => state.fallback).length;
  const nonAgenticCount = agenticStates.filter((state) => state.nonAgentic).length;
  const policyOverlayCount = agenticStates.filter((state) => state.policyOverlay).length;
  const protocolRestrictedCount = agenticStates.filter(
    (state) => state.protocolRestricted,
  ).length;
  const failedDecisionCount = agenticStates.filter(
    (state) => state.fallback || state.nonAgentic || state.policyOverlay,
  ).length;
  const counts = {
    rationale: decisions.filter((event) => Boolean(event.rationale?.trim())).length,
    hypothesis: decisionPayloads.filter(hasCompleteCommonHypothesisForPayload).length,
    alternatives: configurablePayloads.filter(hasAlternatives).length,
    evidence: nonSupervisorPayloads.filter(hasEvidenceReferences).length,
    exactTrace: exactTraceCount,
  };
  const origin = traceOrigin(events);
  const participatingAgentCount = AGENT_PROFILES.filter((profile) =>
    decisions.some((event) => eventEmittingAgentId(event) === profile.id),
  ).length;
  const executorEvents = events.filter((event) => event.kind === "executor_result");
  const executorCount = executorEvents.length;
  const executorLinkExpectedDecisions = decisions.filter(decisionExpectsExecutorLink);
  const executorLinkedDecisionCount = executorLinkExpectedDecisions.filter((decision) =>
    decisionHasExecutorLink(decision, executorEvents),
  ).length;
  const evaluationCount = decisions.filter(
    (event) => event.agent_name === "evaluator" || event.node === "evaluator",
  ).length;
  const toolClaimCount = decisionPayloads.reduce(
    (total, payload) => total + auditToolClaims(payload).length,
    0,
  );
  const toolObservationCount = events.filter(
    (event) => toolObservationRecord(event) !== null,
  ).length;
  const unobservedToolClaimCount = decisions.reduce(
    (total, decision) =>
      total + unobservedToolClaimsForDecision(decision, events).length,
    0,
  );
  const roleAudits = buildRoleAudits(decisions, events);
  const gaps: string[] = [];
  if (origin === "reconstructed") gaps.push("No conserva intentos rechazados ni tiempos runtime");
  if (executorCount === 0) gaps.push("Sin eventos de ejecutor enlazados en esta traza");
  if (executorLinkedDecisionCount < executorLinkExpectedDecisions.length) {
    gaps.push(`Enlace accion-ejecutor incompleto en ${executorLinkExpectedDecisions.length - executorLinkedDecisionCount} decisiones`);
  }
  if (exactTraceCount < decisions.length) gaps.push(`Origen exacto ausente en ${decisions.length - exactTraceCount} decisiones`);
  if (inferredFallbackCount > 0) gaps.push(`${inferredFallbackCount} fallbacks historicos son inferencias textuales, no trazas exactas`);
  if (policyOverlayCount > 0) gaps.push(`${policyOverlayCount} decisiones LLM fueron modificadas por un guardarrail determinista`);
  if (counts.hypothesis < decisions.length) gaps.push(`Contrato comun de hipotesis incompleto en ${decisions.length - counts.hypothesis} decisiones`);
  if (participatingAgentCount < AGENT_PROFILES.length) gaps.push(`Cobertura parcial: ${participatingAgentCount}/${AGENT_PROFILES.length} agentes emitieron decisiones`);
  if (counts.alternatives < configurablePayloads.length) gaps.push("Alternativas ausentes en alguna decision configurable");
  if (unobservedToolClaimCount > 0) {
    gaps.push(`${unobservedToolClaimCount} herramientas declaradas sin observacion exitosa enlazada a la misma decision`);
  }

  return {
    decisionCount: decisions.length,
    completeHypothesisCount: counts.hypothesis,
    participatingAgentCount,
    supervisorDecisionCount: supervisorDecisions.length,
    roleDecisionCount: roleDecisions.length,
    executorCount,
    executorLinkExpectedCount: executorLinkExpectedDecisions.length,
    executorLinkedDecisionCount,
    evaluationCount,
    exactTraceCount,
    firstPassCount,
    fallbackCount,
    inferredFallbackCount,
    repairedCount,
    nonAgenticCount,
    failedDecisionCount,
    policyOverlayCount,
    protocolRestrictedCount,
    unknownTraceCount: originCounts.unknown,
    toolClaimCount,
    toolObservationCount,
    unobservedToolClaimCount,
    origin,
    originCounts,
    roleAudits,
    coverage: [
      { label: "Agentes participantes", value: participatingAgentCount, total: AGENT_PROFILES.length, detail: "Roles que emitieron al menos una decision contractual" },
      { label: "Justificacion", value: counts.rationale, total: decisions.length, detail: "Decision con rationale persistido" },
      { label: "Origen exacto", value: counts.exactTrace, total: decisions.length, detail: "Procedencia persistida en generation_trace" },
      { label: "Hipotesis completa", value: counts.hypothesis, total: decisions.length, detail: "Tipo, afirmacion, alcance, corte de evidencia, observacion esperada, refutacion, evidencias y riesgos" },
      { label: "Alternativas", value: counts.alternatives, total: configurablePayloads.length, detail: "Opciones en estructuracion y modelado" },
      { label: "Evidencia", value: counts.evidence, total: nonSupervisorPayloads.length, detail: "Decisiones con referencias de evidencia declaradas" },
      { label: "Accion enlazada", value: executorLinkedDecisionCount, total: executorLinkExpectedDecisions.length, detail: "Decisiones que materializan una accion y conservan el decision_id en su resultado de ejecutor" },
    ],
    gaps,
  };
}

function buildRoleAudits(
  decisions: AgentRuntimeEvent[],
  events: AgentRuntimeEvent[],
): AgentRoleAudit[] {
  const executorEvents = events.filter((event) => event.kind === "executor_result");
  return AGENT_PROFILES.map((profile) => {
    const roleEvents = decisions.filter(
      (event) => eventEmittingAgentId(event) === profile.id,
    );
    const latestEvent = roleEvents.length > 0 ? roleEvents[roleEvents.length - 1] : null;
    const latestPayload = latestEvent ? decisionPayload(latestEvent) : {};
    const primaryTraces = roleEvents.map((event) => primaryGenerationTrace(decisionPayload(event)));
    const states = roleEvents.map((event) => decisionAgenticState(decisionPayload(event)));
    const exactTraceCount = primaryTraces.filter((trace) => trace !== null).length;
    const firstPassCount = states.filter((state) => state.firstPass).length;
    const fallbackCount = states.filter((state) => state.fallback).length;
    const inferredFallbackCount = roleEvents.filter(
      (event, index) => !states[index].fallback && hasLegacyFallbackSignal(event),
    ).length;
    const repairedCount = states.filter((state) => state.repaired).length;
    const nonAgenticCount = states.filter((state) => state.nonAgentic).length;
    const policyOverlayCount = states.filter((state) => state.policyOverlay).length;
    const protocolRestrictedCount = states.filter(
      (state) => state.protocolRestricted,
    ).length;
    const protocolRestricted = protocolRestrictedCount > 0;
    const tracePresentation = roleTracePresentation({
      decisionCount: roleEvents.length,
      exactTraceCount,
      firstPassCount,
      fallbackCount,
      inferredFallbackCount,
      repairedCount,
      nonAgenticCount,
      policyOverlayCount,
      protocolRestricted,
    });
    const rolePayloads = roleEvents.map(decisionPayload);
    const hypothesisCount = rolePayloads.filter(
      hasCompleteCommonHypothesisForPayload,
    ).length;
    const evidenceCount = new Set(rolePayloads.flatMap(auditEvidenceReferences)).size;
    const toolClaimCount = rolePayloads.reduce(
      (total, payload) => total + auditToolClaims(payload).length,
      0,
    );
    const alternativeCount = rolePayloads.reduce(
      (total, payload) => total + auditAlternatives(payload).length,
      0,
    );
    const focus = roleFocus(profile.id, latestPayload, latestEvent);
    const expectedExecutorEvents = roleEvents.filter(decisionExpectsExecutorLink);
    const linkedExecutorEvents = expectedExecutorEvents.filter((event) =>
      decisionHasExecutorLink(event, executorEvents),
    );

    return {
      agentId: profile.id,
      label: profile.label,
      role: profile.role,
      decisionCount: roleEvents.length,
      latestDecisionId: latestEvent?.decision_id ?? null,
      focusLabel: focus.label,
      focusText: focus.text,
      chosenDecision: roleChosenDecision(profile.id, latestPayload),
      hypothesisCount,
      alternativeCount,
      evidenceCount,
      toolClaimCount,
      executorLinkExpected: expectedExecutorEvents.length > 0,
      executorLinked:
        expectedExecutorEvents.length > 0 &&
        linkedExecutorEvents.length === expectedExecutorEvents.length,
      traceLabel: tracePresentation.label,
      traceTone: tracePresentation.tone,
      exactTraceCount,
      firstPassCount,
      fallbackCount,
      inferredFallbackCount,
      repairedCount,
      nonAgenticCount,
      policyOverlayCount,
      protocolRestrictedCount,
      protocolRestricted,
      limitation: roleAuditLimitation(
        profile.id,
        roleEvents.length,
        hypothesisCount,
        exactTraceCount,
        protocolRestricted,
        evidenceCount,
      ),
    };
  });
}

function roleTracePresentation({
  decisionCount,
  exactTraceCount,
  firstPassCount,
  fallbackCount,
  inferredFallbackCount,
  repairedCount,
  nonAgenticCount,
  policyOverlayCount,
  protocolRestricted,
}: {
  decisionCount: number;
  exactTraceCount: number;
  firstPassCount: number;
  fallbackCount: number;
  inferredFallbackCount: number;
  repairedCount: number;
  nonAgenticCount: number;
  policyOverlayCount: number;
  protocolRestricted: boolean;
}): { label: string; tone: AgentRoleAudit["traceTone"] } {
  if (decisionCount === 0) return { label: "Sin decision", tone: "muted" };
  if (fallbackCount > 0) return { label: `Fallback trazado (${fallbackCount})`, tone: "danger" };
  if (nonAgenticCount > 0) return { label: `No agentica (${nonAgenticCount})`, tone: "danger" };
  if (inferredFallbackCount > 0) return { label: `Fallback legacy (~${inferredFallbackCount})`, tone: "warning" };
  if (policyOverlayCount > 0) return { label: `LLM + guardarrail (${policyOverlayCount})`, tone: "warning" };
  if (repairedCount > 0) return { label: `LLM reparado (${repairedCount})`, tone: "warning" };
  if (protocolRestricted) return { label: "Protocolo fijo", tone: "warning" };
  if (firstPassCount > 0) return { label: `LLM intento logico 1 (${firstPassCount})`, tone: "ok" };
  if (exactTraceCount < decisionCount) return { label: "Origen no registrado", tone: "muted" };
  return { label: "Origen desconocido", tone: "muted" };
}

function roleFocus(
  agentId: string,
  payload: Record<string, unknown>,
  event: AgentRuntimeEvent | null,
): { label: string; text: string } {
  const commonHypotheses = hypothesisViewModelsForPayload(payload);
  const primaryHypothesis = commonHypotheses.length > 0
    ? commonHypotheses[commonHypotheses.length - 1]
    : null;
  if (primaryHypothesis) {
    return {
      label: primaryHypothesis.label,
      text: compactAuditText(primaryHypothesis.statement),
    };
  }
  const variants = decisionPayloadVariants(payload);
  if (agentId === "modeler") {
    for (const candidate of variants) {
      const strategy = auditRecord(candidate.decision_strategy);
      const hypothesis = auditText(strategy?.hypothesis);
      if (hypothesis) return { label: "Hipotesis", text: compactAuditText(hypothesis) };
    }
  }
  if (agentId === "evaluator") {
    const evaluation = auditRecord(payload.evaluation);
    const assessment = auditText(payload.operational_assessment)
      ?? auditText(evaluation?.summary);
    if (assessment) return { label: "Juicio", text: compactAuditText(assessment) };
  }
  if (agentId === "report_verifier") {
    const summary = auditText(payload.summary);
    if (summary) return { label: "Verificacion factual", text: compactAuditText(summary) };
  }
  const labels: Record<string, string> = {
    supervisor: "Criterio de enrutamiento",
    cleaner: "Politica de limpieza",
    structurer: "Criterio de estructuracion",
    report_writer: "Plan narrativo",
  };
  const rationale = auditText(payload.rationale) ?? event?.rationale ?? null;
  return {
    label: labels[agentId] ?? "Justificacion",
    text: compactAuditText(rationale ?? "No hay justificacion estructurada disponible."),
  };
}

function roleChosenDecision(agentId: string, payload: Record<string, unknown>): string {
  if (Object.keys(payload).length === 0) return "No participo en la traza cargada";
  if (agentId === "supervisor") {
    const next = auditText(payload.next_node) ?? auditText(payload.next_stage) ?? "fin";
    return `${auditText(payload.current_stage) ?? "fase"} → ${next}`;
  }
  if (agentId === "cleaner") {
    const config = auditRecord(payload.cleaning_config);
    const strategy = auditText(config?.strategy_id) ?? "politica sin identificador";
    const normalization = auditText(config?.normalization);
    return normalization ? `${strategy} · normalizacion ${normalization}` : strategy;
  }
  if (agentId === "structurer") {
    const config = auditRecord(payload.structuring_config);
    const windowSize = auditScalarText(config?.window_size);
    const overlap = auditScalarText(config?.overlap);
    return windowSize
      ? `Ventana ${windowSize}${overlap ? ` · solape ${overlap}` : ""}`
      : "Configuracion de estructuracion persistida";
  }
  if (agentId === "modeler") {
    const config = auditRecord(payload.modeling_config) ?? auditRecord(payload.retry_config);
    return auditText(config?.model_name) ?? (payload.should_retry === false ? "Detener reintentos" : "Modelo no identificado");
  }
  if (agentId === "evaluator") {
    const evaluation = auditRecord(payload.evaluation);
    if (evaluation?.approved === true) return "Aprobacion operativa";
    if (evaluation?.approved === false) return `No aprobado · ${auditText(evaluation.next_action) ?? "revisar"}`;
    return "Juicio sin veredicto persistido";
  }
  if (agentId === "report_writer") {
    const revisionRound = auditScalarText(payload.revision_round);
    if (revisionRound) return `Revision del informe · ronda ${revisionRound}`;
    return `Informe ${auditText(payload.output_format) ?? "estructurado"}`;
  }
  if (agentId === "report_verifier") {
    return auditText(payload.verification_status) ?? "Verificacion sin estado";
  }
  return "Decision contractual persistida";
}

function roleAuditLimitation(
  agentId: string,
  decisionCount: number,
  hypothesisCount: number,
  exactTraceCount: number,
  protocolRestricted: boolean,
  evidenceCount: number,
): string | null {
  if (decisionCount === 0) return "El rol no participo en esta ejecucion; no puede evaluarse.";
  if (hypothesisCount < decisionCount) return `${decisionCount - hypothesisCount} decisiones no conservan completo el contrato comun de hipotesis.`;
  if (exactTraceCount === 0) return "La run historica no permite distinguir LLM, reparacion y fallback con certeza.";
  if (protocolRestricted) return "La propuesta queda visible, pero no controlo la configuracion ejecutada.";
  if (agentId === "supervisor") return "La ruta esta acotada por transiciones permitidas; no mide autonomia abierta.";
  if (agentId === "cleaner") return "La hipotesis de calidad requiere metricas antes/despues para poder contrastarse.";
  if (agentId === "evaluator") return "El juicio narrativo se somete a umbrales y guardarrailes deterministas.";
  if (agentId === "report_writer" && evidenceCount === 0) return "No hay referencias de evidencia estructuradas en la decision mostrada.";
  if (agentId === "report_verifier") return "Debe comprobarse por separado si su veredicto final bloquea realmente el cierre.";
  return null;
}

function decisionHasExecutorLink(
  decision: AgentRuntimeEvent,
  executorEvents: AgentRuntimeEvent[],
): boolean {
  if (!decision.decision_id) return false;
  return executorEvents.some((event) => {
    const candidates = [
      event.decision_id,
      auditText(event.payload.decision_id),
      auditText(event.payload.source_decision_id),
      auditText(event.payload.agent_decision_id),
    ];
    return candidates.includes(decision.decision_id);
  });
}

function decisionExpectsExecutorLink(decision: AgentRuntimeEvent): boolean {
  const agentId = eventEmittingAgentId(decision);
  if (agentId === null || !EXECUTOR_DECISION_AGENTS.has(agentId)) return false;
  const payload = decisionPayload(decision);
  if (
    agentId === "modeler" &&
    auditText(payload.decision_kind) === "modeling_retry"
  ) {
    return payload.should_retry === true;
  }
  return true;
}

function toolObservationRecord(
  event: AgentRuntimeEvent,
): Record<string, unknown> | null {
  const nested = auditRecord(event.payload.tool_observation);
  if (nested) return nested;
  return auditText(event.payload.observation_id) ? event.payload : null;
}

function unobservedToolClaimsForDecision(
  decision: AgentRuntimeEvent,
  events: AgentRuntimeEvent[],
): string[] {
  const claims = [...new Set(auditToolClaims(decisionPayload(decision)).map(
    (claim) => claim.trim().toLowerCase(),
  ))];
  if (claims.length === 0 || !decision.decision_id) return claims;
  const decisionAgentId = eventEmittingAgentId(decision);
  const observedTools = new Set(
    events.flatMap((event) => {
      if (event.sequence >= decision.sequence) return [];
      if (!eventDecisionLinkIds(event).includes(decision.decision_id!)) return [];
      const observation = toolObservationRecord(event);
      if (!observation || auditText(observation.status) !== "success") return [];
      const observationAgentId =
        auditText(observation.agent_name) ?? eventRelatedAgentId(event);
      if (decisionAgentId === null || observationAgentId !== decisionAgentId) return [];
      const toolName = auditText(observation.tool_name);
      return toolName ? [toolName.toLowerCase()] : [];
    }),
  );
  return claims.filter((claim) => !observedTools.has(claim));
}

function primaryGenerationTrace(payload: Record<string, unknown>): Record<string, unknown> | null {
  return auditRecord(payload.generation_trace);
}

function proposalGenerationTrace(payload: Record<string, unknown>): Record<string, unknown> | null {
  const protocolTrace = auditRecord(payload.protocol_trace);
  const proposal = auditRecord(protocolTrace?.agent_proposal);
  return proposal ? primaryGenerationTrace(proposal) : null;
}

function decisionAgenticState(payload: Record<string, unknown>): DecisionAgenticState {
  const primaryTrace = primaryGenerationTrace(payload);
  const proposalTrace = proposalGenerationTrace(payload);
  const protocolRestricted = hasProtocolTrace(payload)
    || generationOrigin(primaryTrace) === "protocol_restricted";
  const agenticTrace = protocolRestricted && proposalTrace !== null
    ? proposalTrace
    : primaryTrace;
  const traces = [primaryTrace, proposalTrace].filter(
    (trace): trace is Record<string, unknown> => trace !== null,
  );
  const agenticOrigin = generationOrigin(agenticTrace);
  const validationStatus = auditText(agenticTrace?.validation_status);
  const attemptIndex = Number(agenticTrace?.attempt_index);
  const fallback = traces.some(
    (trace) => generationOrigin(trace) === "guardrail_fallback",
  );
  return {
    primaryTrace,
    proposalTrace,
    firstPass:
      agenticOrigin === "llm"
      && validationStatus === "validated"
      && attemptIndex === 1,
    repaired: traces.some((trace) => trace.validation_status === "repaired"),
    fallback,
    nonAgentic:
      !fallback
      && agenticTrace !== null
      && agenticOrigin !== "llm",
    protocolRestricted,
    policyOverlay: hasPolicyOverlay(payload),
  };
}

function allGenerationTraces(payload: Record<string, unknown>): Record<string, unknown>[] {
  return decisionPayloadVariants(payload)
    .map(primaryGenerationTrace)
    .filter((trace): trace is Record<string, unknown> => trace !== null);
}

function generationOrigin(trace: Record<string, unknown> | null): AuditGenerationOrigin {
  const origin = auditText(trace?.origin);
  if (["llm", "deterministic", "guardrail_fallback", "protocol_restricted"].includes(origin ?? "")) {
    return origin as AuditGenerationOrigin;
  }
  return "unknown";
}

function hasPolicyOverlay(payload: Record<string, unknown>): boolean {
  return payload.policy_overlay_applied === true;
}

function hasLegacyFallbackSignal(event: AgentRuntimeEvent): boolean {
  const text = `${event.rationale ?? ""} ${JSON.stringify(decisionPayload(event))}`.toLowerCase();
  return [
    "fallback after",
    "guardrail correction",
    "reparacion tras",
    "repair after",
    "fallback determinista tras",
  ].some((term) => text.includes(term));
}

function auditAlternatives(payload: Record<string, unknown>): Record<string, unknown>[] {
  const alternatives: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  for (const candidate of decisionPayloadVariants(payload)) {
    for (const key of ["comparison_candidates", "alternatives", "options_considered"]) {
      const values = candidate[key];
      if (!Array.isArray(values)) continue;
      for (const value of values) {
        const record = auditRecord(value);
        if (!record) continue;
        const identity = auditText(record.alternative_id) ?? JSON.stringify(record);
        if (!seen.has(identity)) {
          seen.add(identity);
          alternatives.push(record);
        }
      }
    }
  }
  return alternatives;
}

function auditEvidenceReferences(payload: Record<string, unknown>): string[] {
  const refs = new Set<string>();
  for (const candidate of decisionPayloadVariants(payload)) {
    const strategy = auditRecord(candidate.decision_strategy);
    const hypothesis = auditRecord(candidate.hypothesis);
    for (const value of [
      candidate.evidence_refs,
      candidate.evidence_used,
      strategy?.evidence_refs,
      hypothesis?.evidence_refs,
    ]) {
      for (const ref of auditStringArray(value)) refs.add(ref);
    }
    const sections = candidate.sections;
    if (Array.isArray(sections)) {
      for (const section of sections) {
        const sectionRecord = auditRecord(section);
        for (const ref of auditStringArray(sectionRecord?.evidence_refs)) refs.add(ref);
      }
    }
    for (const key of ["unsupported_claims", "misleading_claims", "missing_limitations"]) {
      const issues = candidate[key];
      if (!Array.isArray(issues)) continue;
      for (const issue of issues) {
        const issueRecord = auditRecord(issue);
        for (const ref of auditStringArray(issueRecord?.evidence_refs)) refs.add(ref);
      }
    }
  }
  return [...refs];
}

function compactAuditText(value: string, maxLength = 210): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length <= maxLength ? normalized : `${normalized.slice(0, maxLength - 1).trimEnd()}…`;
}

function auditScalarText(value: unknown): string | null {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : null;
}

function auditConclusion(audit: AgentAuditSummary): { title: string; detail: string } {
  if (audit.origin === "empty") {
    return { title: "Run no auditable desde esta vista", detail: "No se han cargado eventos ni decisiones persistidas." };
  }
  if (audit.origin === "reconstructed") {
    return {
      title: "Evidencia historica parcial",
      detail: `${audit.supervisorDecisionCount} rutas y ${audit.roleDecisionCount} decisiones de rol reconstruidas; las ausencias se muestran como limites, no como ceros de comportamiento.`,
    };
  }
  if (audit.failedDecisionCount > 0) {
    return {
      title: "NO APTA para validacion agentica",
      detail: `${audit.fallbackCount} decisiones con fallback, ${audit.nonAgenticCount} no agenticas y ${audit.policyOverlayCount} con overlay. La run puede ser operativa, pero no supera la puerta LLM.`,
    };
  }
  if (audit.exactTraceCount < audit.decisionCount) {
    return {
      title: "Procedencia agentica incompleta",
      detail: `Falta generation_trace en ${audit.decisionCount - audit.exactTraceCount} decisiones; no se puede certificar la run como agentica.`,
    };
  }
  if (audit.completeHypothesisCount < audit.decisionCount) {
    return {
      title: "Contrato de hipotesis incompleto",
      detail: `Solo ${audit.completeHypothesisCount}/${audit.decisionCount} decisiones conservan todos los campos auditables; la run no supera la puerta de trazabilidad.`,
    };
  }
  if (audit.participatingAgentCount < AGENT_PROFILES.length) {
    return {
      title: "Cobertura agentica parcial",
      detail: `${audit.participatingAgentCount}/${AGENT_PROFILES.length} agentes emitieron una decision. La traza sirve para inspeccion parcial, no para certificar el flujo completo.`,
    };
  }
  if (audit.executorLinkedDecisionCount < audit.executorLinkExpectedCount) {
    return {
      title: "Decisiones persistidas, enlace de ejecucion incompleto",
      detail: `Solo ${audit.executorLinkedDecisionCount}/${audit.executorLinkExpectedCount} decisiones que materializan acciones conservan un enlace exacto a su resultado de ejecutor.`,
    };
  }
  return {
    title: "APTA en trazabilidad agentica",
    detail: `${audit.firstPassCount} decisiones registradas en el intento logico 1, ${audit.repairedCount} con segunda llamada LLM y cero fallbacks o overlays. Falta valorar por separado la calidad tecnica de sus decisiones.`,
  };
}

function traceOrigin(events: AgentRuntimeEvent[]): AgentAuditSummary["origin"] {
  if (events.length === 0) return "empty";
  const origins = events.map((event) => event.payload.trace_origin);
  if (origins.includes("reconstructed_from_decisions")) return "reconstructed";
  if (origins.includes("persisted_runtime")) return "persisted";
  return "live";
}

function decisionPayload(event: AgentRuntimeEvent): Record<string, unknown> {
  return agentDecisionPayload(event);
}

function hasAlternatives(payload: Record<string, unknown>): boolean {
  return auditAlternatives(payload).length > 0;
}

function hasEvidenceReferences(payload: Record<string, unknown>): boolean {
  return auditEvidenceReferences(payload).length > 0;
}

function hasProtocolTrace(payload: Record<string, unknown>): boolean {
  return auditRecord(payload.protocol_trace) !== null;
}

function auditToolClaims(payload: Record<string, unknown>): string[] {
  const claims: string[] = [];
  for (const candidate of decisionPayloadVariants(payload)) {
    const strategy = auditRecord(candidate.decision_strategy);
    claims.push(
      ...auditStringArray(candidate.tool_names),
      ...auditStringArray(candidate.tools_used),
      ...auditStringArray(strategy?.tool_names),
    );
  }
  return claims;
}

function decisionPayloadVariants(payload: Record<string, unknown>): Record<string, unknown>[] {
  const variants = [payload];
  const protocolTrace = auditRecord(payload.protocol_trace);
  const proposal = protocolTrace ? auditRecord(protocolTrace.agent_proposal) : null;
  if (proposal) variants.push(proposal);
  return variants;
}

function auditRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function auditText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function auditStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function AgentRuntimeTimeline({
  events,
  selectedDecisionEventId,
  onSelectEvent,
}: {
  events: AgentRuntimeEvent[];
  selectedDecisionEventId: string | null;
  onSelectEvent: (event: AgentRuntimeEvent) => void;
}) {
  if (events.length === 0) {
    return <p className="empty-state compact-empty">Sin eventos runtime</p>;
  }

  return (
    <div className="runtime-timeline" aria-label="Timeline de eventos agenticos">
      {events.slice(-60).map((event) => (
        <button
          aria-pressed={event.event_id === selectedDecisionEventId}
          className={`timeline-event ${event.kind === "error" ? "error" : ""} ${
            isDecisionEvent(event) ? "decision" : ""
          } ${event.event_id === selectedDecisionEventId ? "selected" : ""}`}
          key={event.event_id}
          type="button"
          onClick={() => onSelectEvent(event)}
        >
          <span>{event.sequence}</span>
          <div>
            <strong>{event.title}</strong>
            <small>
              {formatEventTime(event.created_at)} | {sourceLabel(event)} |{" "}
              {event.stage ?? kindLabel(event.kind)}
            </small>
            {isDecisionEvent(event) ? <em>abrir decisión</em> : null}
          </div>
        </button>
      ))}
    </div>
  );
}

function AgentRuntimeDetail({
  event,
  eventCount,
  policyProposal,
  onSelectMemoryRecord,
}: {
  event: AgentRuntimeEvent | null;
  eventCount: number;
  policyProposal: MonitoringPolicyProposalViewModel | null;
  onSelectMemoryRecord?: (memoryRecordId: string) => void;
}) {
  if (event === null) {
    return (
      <p className="empty-state compact-empty">
        No hay una decisión de agente enlazada de forma exacta al evento seleccionado.
      </p>
    );
  }

  const runtimeSignals = runtimeSignalChips(event);
  const nextStep = event.next_node ?? event.next_stage ?? "-";

  return (
    <div className="agent-detail">
      <section className="agent-decision-card">
        <div className="event-head">
          <StatusPill ok={event.kind !== "error"} label={kindLabel(event.kind)} />
          <span>{eventCount} decisiones</span>
        </div>
        <h3>{event.title}</h3>
        <p className="agent-event-summary">{event.summary}</p>
        <AgentEventTranslation event={event} />
        <AgentDecisionInspector event={event} policyProposal={policyProposal} />

        <div className="agent-decision-grid">
          <DecisionFact icon={<FileJson size={16} />} label="Decision" value={event.decision_id ?? "-"} />
          <DecisionFact icon={<Brain size={16} />} label="Confianza" value={confidenceText(event.confidence)} />
          <DecisionFact icon={<ListChecks size={16} />} label="Fase" value={event.stage ?? "-"} />
          <DecisionFact icon={<Route size={16} />} label="Siguiente" value={nextStep} />
        </div>
      </section>

      {event.rationale ? (
        <details className="runtime-block compact-disclosure agent-rationale-block">
          <summary>Rationale</summary>
          <p>{event.rationale}</p>
        </details>
      ) : null}

      {runtimeSignals.length > 0 ? (
        <section className="runtime-block">
          <h4>Declaraciones y señales</h4>
          <div className="agent-signal-chip-row">
            {runtimeSignals.map((signal) => (
              <span className={`agent-signal-chip ${signal.tone}`} key={`${signal.label}-${signal.value}`}>
                {signal.label}: {signal.value}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {event.memory_record_ids.length > 0 ? (
        <section className="runtime-block">
          <h4>
            <Quote size={14} />
            Memoria citada
          </h4>
          <div className="memory-chip-row">
            {event.memory_record_ids.map((memoryId) => (
              onSelectMemoryRecord ? (
                <button
                  className="memory-chip memory-chip-button"
                  key={memoryId}
                  type="button"
                  onClick={() => onSelectMemoryRecord(memoryId)}
                >
                  {memoryId}
                </button>
              ) : (
                <span className="memory-chip" key={memoryId}>
                  {memoryId}
                </span>
              )
            ))}
          </div>
        </section>
      ) : null}

      <details className="runtime-block compact-disclosure runtime-payload-details">
        <summary>
          <FileJson size={15} />
          Payload tecnico
        </summary>
        <pre className="runtime-json">{JSON.stringify(event.payload, null, 2)}</pre>
      </details>
    </div>
  );
}

function AgentDecisionInspector({
  event,
  policyProposal,
}: {
  event: AgentRuntimeEvent;
  policyProposal: MonitoringPolicyProposalViewModel | null;
}) {
  const payload = decisionPayload(event);
  const evidenceCatalog = monitoringEvidenceCatalogModel(event);
  const agentId = eventEmittingAgentId(event) ?? eventOwnerId(event);
  const protocolTrace = auditRecord(payload.protocol_trace);
  const proposal = auditRecord(protocolTrace?.agent_proposal);
  const alternatives = auditAlternatives(payload);
  const evidenceRefs = auditEvidenceReferences(payload);
  const visibleEvidenceRefs = evidenceCatalog ? [] : evidenceRefs.slice(0, 12);
  const toolClaims = [...new Set(auditToolClaims(payload))];
  const hypotheses = decisionHypotheses(payload);
  const state = decisionAgenticState(payload);
  const overlayIds = auditStringArray(payload.policy_overlay_issue_ids);

  return (
    <section className="agent-decision-inspector" aria-label="Inspector visual de la decision">
      <div className="agent-inspector-heading">
        <div>
          <span>Inspector de decision</span>
          <strong>{roleChosenDecision(agentId, payload)}</strong>
        </div>
        <span className={`agent-inspector-gate ${decisionGateTone(state)}`}>
          {decisionGateLabel(state)}
        </span>
      </div>

      <GenerationTraceStrip state={state} />

      {evidenceCatalog ? (
        <MonitoringEvidenceSelection catalog={evidenceCatalog} />
      ) : null}

      {policyProposal ? (
        <MonitoringPolicyProposalAudit proposal={policyProposal} />
      ) : null}

      {hypotheses.length > 0 ? (
        <div className="agent-inspector-hypotheses">
          {hypotheses.map((item) => (
            <article key={`${item.label}-${item.statement}`}>
              <header>
                <span>{item.label}</span>
                <em>{hypothesisAssessmentLabel(item.assessmentStatus)}</em>
              </header>
              <p>{item.statement}</p>
              {item.expectedObservation ? (
                <div className="agent-hypothesis-test expected">
                  <span>Que esperamos observar</span>
                  <p>{item.expectedObservation}</p>
                </div>
              ) : null}
              {item.falsificationCriterion ? (
                <div className="agent-hypothesis-test falsifier">
                  <span>Que la refutaria</span>
                  <p>{item.falsificationCriterion}</p>
                </div>
              ) : null}
              {item.kind || item.scope || item.evidenceCutoff ? (
                <dl className="agent-hypothesis-context">
                  {item.kind ? <div><dt>Tipo</dt><dd>{item.kind.replace(/_/g, " ")}</dd></div> : null}
                  {item.scope ? <div><dt>Alcance</dt><dd>{item.scope}</dd></div> : null}
                  {item.evidenceCutoff ? <div><dt>Corte de evidencia</dt><dd>{item.evidenceCutoff}</dd></div> : null}
                </dl>
              ) : null}
              {item.assumptions.length > 0 ? (
                <div className="agent-hypothesis-assumptions">
                  <strong>Supuestos declarados</strong>
                  {item.assumptions.map((assumption) => <span key={assumption}>{assumption}</span>)}
                </div>
              ) : null}
              {item.evidenceRefs.length > 0 ? (
                <div className="agent-hypothesis-evidence">
                  <strong>
                    {evidenceCatalog
                      ? "Registros atribuidos a esta hipótesis"
                      : "Evidencia atribuida a esta hipotesis"}
                  </strong>
                  <div className="agent-inspector-chip-row evidence">
                    {(evidenceCatalog?.selectedHandles ?? item.evidenceRefs).map(
                      (ref) => <span key={ref}>{ref}</span>,
                    )}
                  </div>
                </div>
              ) : null}
              {item.riskNotes.length > 0 ? (
                <div className="agent-hypothesis-risks">
                  <strong>Riesgos</strong>
                  {item.riskNotes.map((risk) => <span key={risk}>{risk}</span>)}
                </div>
              ) : null}
              {item.source === "legacy_modeler" ? (
                <small>Traza legacy: no conserva prueba ni corte de evidencia completos.</small>
              ) : !item.contractComplete ? (
                <small>Contrato comun incompleto: esta hipotesis no cuenta para la cobertura auditable.</small>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {proposal && protocolTrace ? (
        <section className="agent-protocol-comparison">
          <DecisionComparisonCard
            agentId={agentId}
            label="Propuso el LLM"
            payload={proposal}
            tone="proposal"
          />
          <span className="agent-protocol-arrow" aria-hidden="true">→</span>
          <DecisionComparisonCard
            agentId={agentId}
            label="Se ejecuto"
            payload={payload}
            tone="effective"
          />
          <div className="agent-protocol-reason">
            <strong>Restriccion experimental</strong>
            <p>{auditText(protocolTrace.restriction_reason) ?? "La configuracion fue fijada por protocolo."}</p>
            <div className="agent-inspector-chip-row">
              {auditStringArray(protocolTrace.overridden_fields).map((field) => (
                <span key={field}>cambio · {field.replace(/_/g, " ")}</span>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <DecisionComparisonCard
          agentId={agentId}
          label="Decision efectiva"
          payload={payload}
          tone="effective"
        />
      )}

      {alternatives.length > 0 ? (
        <section className="agent-alternative-section">
          <div className="agent-inspector-subheading">
            <GitBranch size={14} />
            <span>Alternativas consideradas · {alternatives.length}</span>
          </div>
          <div className="agent-alternative-grid">
            {alternatives.map((alternative, index) => (
              <AlternativeCard
                alternative={alternative}
                index={index}
                key={auditText(alternative.alternative_id) ?? `alternative-${index}`}
              />
            ))}
          </div>
        </section>
      ) : null}

      {visibleEvidenceRefs.length > 0 || toolClaims.length > 0 ? (
        <section className="agent-inspector-sources">
          {visibleEvidenceRefs.length > 0 ? (
            <div>
              <strong>Indice agregado de referencias declaradas</strong>
              <div className="agent-inspector-chip-row evidence">
                {visibleEvidenceRefs.map((ref) => <span key={ref}>{ref}</span>)}
                {evidenceRefs.length > visibleEvidenceRefs.length ? (
                  <span>+{evidenceRefs.length - visibleEvidenceRefs.length} referencias</span>
                ) : null}
              </div>
            </div>
          ) : null}
          {toolClaims.length > 0 ? (
            <div>
              <strong>Herramientas declaradas o propuestas</strong>
              <p>No equivalen a observaciones ejecutadas mientras no exista una tool observation enlazada.</p>
              <div className="agent-inspector-chip-row tools">
                {toolClaims.map((tool) => <span key={tool}>{tool}</span>)}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {state.policyOverlay ? (
        <section className="agent-overlay-callout">
          <strong>Overlay determinista de seguridad</strong>
          <p>La salida efectiva fue completada o endurecida después de la respuesta LLM.</p>
          {overlayIds.length > 0 ? (
            <div className="agent-inspector-chip-row">
              {overlayIds.map((issueId) => <span key={issueId}>{issueId}</span>)}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function MonitoringEvidenceSelection({
  catalog,
}: {
  catalog: MonitoringEvidenceCatalogViewModel;
}) {
  const selected = new Set(catalog.selectedHandles);
  const selectedCount = catalog.selectedHandles.length;
  return (
    <section
      aria-label={`Evidencia causal: ${selectedCount} de ${catalog.totalCount} registros usados`}
      className="agent-record-evidence"
    >
      <header className="agent-record-evidence-heading">
        <div>
          <span><Database size={14} /> Soporte causal por registro</span>
          <strong>{selectedCount}/{catalog.totalCount} registros usados</strong>
        </div>
        <span className="agent-record-evidence-seal">
          <ShieldCheck size={13} /> Catálogo sellado
        </span>
      </header>

      <div
        aria-label="Registros disponibles y seleccionados"
        className="agent-record-evidence-rail"
        role="list"
      >
        {catalog.availableHandles.map((handle) => {
          const isSelected = selected.has(handle);
          return (
            <span
              aria-label={`${handle}: ${isSelected ? "seleccionado" : "disponible no seleccionado"}`}
              className={isSelected ? "selected" : "available"}
              key={handle}
              role="listitem"
            >
              {handle}
            </span>
          );
        })}
      </div>

      <div
        aria-label="Registros de soporte seleccionados"
        className="agent-record-evidence-cards"
      >
        {catalog.selectedRecords.map((record) => (
          <MonitoringEvidenceRecordCard key={record.handle} record={record} />
        ))}
      </div>
    </section>
  );
}

function MonitoringEvidenceRecordCard({
  record,
}: {
  record: MonitoringEvidenceRecordViewModel;
}) {
  const observedAt = compactEvidenceTime(record.sourceTime, record.snapshotId);
  const assetChannel = [record.assetId, record.channelId]
    .filter((value): value is string => value !== null)
    .map(humanizeEvidenceToken)
    .join(" · ");
  return (
    <article
      aria-label={`Registro seleccionado ${record.handle}`}
      className="agent-record-evidence-card"
    >
      <header>
        <strong>{record.handle}</strong>
        <span>{evidenceAnalysisLabel(record)}</span>
      </header>
      <div className="agent-record-evidence-context">
        {observedAt ? (
          <time dateTime={record.sourceTime ?? undefined}>{observedAt}</time>
        ) : null}
        {assetChannel ? <span>{assetChannel}</span> : null}
      </div>
      <div className="agent-record-evidence-facts">
        {record.healthState ? (
          <span>{evidenceHealthLabel(record.healthState)}</span>
        ) : null}
        {record.scoreRatio !== null ? (
          <span>Ratio {formatEvidenceRatio(record.scoreRatio)}×</span>
        ) : null}
        {record.gapDetected ? <span className="warning">Gap</span> : null}
      </div>
    </article>
  );
}

function MonitoringPolicyContributionCard({
  contribution,
  proposal,
}: {
  contribution: MonitoringPolicyProposalContributionViewModel;
  proposal: MonitoringPolicyProposalViewModel;
}) {
  return (
    <section
      aria-label="Propuesta consultiva de política"
      className="agent-policy-contribution"
    >
      <header className="agent-policy-heading">
        <span>
          <Lightbulb size={14} /> {policyContributionOriginLabel(contribution)}
        </span>
        <span className="agent-policy-statuses">
          <em>Consultiva</em>
          <em>No aplicada</em>
        </span>
      </header>
      <strong>{policyActionLabel(contribution.recommendedAction)}</strong>
      <PolicyAdvisoryEffect contribution={contribution} />
      <div className="agent-policy-evidence" aria-label="Evidencias de la propuesta">
        {contribution.evidenceHandles.map((handle) => <span key={handle}>{handle}</span>)}
      </div>
      <p><b>Fundamento declarado:</b> {contribution.actionRationale}</p>
      <span className={`agent-policy-human ${contribution.requiresHumanReview ? "required" : "not-required"}`}>
        {contribution.requiresHumanReview
          ? "Revisión humana solicitada en esta contribución"
          : "Revisión humana no solicitada en esta contribución"}
      </span>
      <details className="compact-disclosure agent-policy-risks">
        <summary>Riesgos declarados · {contribution.riskNotes.length}</summary>
        {contribution.riskNotes.map((risk) => <p key={risk}>{risk}</p>)}
      </details>
      <small>{policyAgreementLabel(proposal.agreementStatus)}</small>
    </section>
  );
}

function MonitoringPolicyProposalAudit({
  proposal,
}: {
  proposal: MonitoringPolicyProposalViewModel;
}) {
  const actionCounts = proposal.contributions.reduce<Record<string, number>>(
    (counts, item) => ({
      ...counts,
      [item.recommendedAction]: (counts[item.recommendedAction] ?? 0) + 1,
    }),
    {},
  );
  return (
    <section
      aria-label="Síntesis consultiva de política"
      className={`agent-policy-audit agreement-${proposal.agreementStatus}`}
    >
      <header className="agent-policy-audit-heading">
        <div>
          <span>Síntesis de siete recomendaciones</span>
          <strong>{policyAgreementLabel(proposal.agreementStatus)}</strong>
        </div>
        <span className="agent-policy-statuses">
          <em>Consultiva</em>
          <em>No aplicada</em>
        </span>
      </header>
      <div className="agent-policy-audit-facts">
        <span><strong>{proposal.contributions.length}</strong> roles</span>
        <span><strong>{Object.keys(actionCounts).length}</strong> acciones distintas</span>
        <span>
          <strong>{proposal.humanReviewRecommended ? "Sí" : "No"}</strong>
          revisión humana recomendada
        </span>
      </div>
      {proposal.aggregateAction ? (
        <p className="agent-policy-aggregate">
          Acción común: <strong>{policyActionLabel(proposal.aggregateAction)}</strong>
        </p>
      ) : proposal.agreementStatus === "invalid_review" ? (
        <p className="agent-policy-aggregate warning">
          No se agrega ninguna acción: la revisión contiene salidas no LLM o protocolarias.
        </p>
      ) : (
        <p className="agent-policy-aggregate warning">
          No existe una acción común: se conservan las siete posiciones.
        </p>
      )}
      <div className="agent-policy-contribution-list" role="list" aria-label="Contribuciones a la propuesta">
        {proposal.contributions.map((contribution) => (
          <article key={contribution.agentId} role="listitem">
            <header>
              <strong>{agentLabel(contribution.agentId)}</strong>
              <span>{policyActionLabel(contribution.recommendedAction)}</span>
            </header>
            {contribution.generationOrigin !== "llm" ? (
              <small className="warning">
                {policyContributionOriginLabel(contribution)}; no se atribuye al LLM.
              </small>
            ) : null}
            <PolicyAdvisoryEffect contribution={contribution} />
            <div className="agent-policy-row-footer">
              <span>{contribution.evidenceHandles.join(" · ")}</span>
              {contribution.requiresHumanReview ? <em>Revisión humana</em> : null}
            </div>
            <details className="compact-disclosure agent-policy-risks">
              <summary>Fundamento y riesgos · {contribution.riskNotes.length}</summary>
              <p><b>Fundamento declarado:</b> {contribution.actionRationale}</p>
              {contribution.riskNotes.map((risk) => <p key={risk}>{risk}</p>)}
            </details>
          </article>
        ))}
      </div>
      <small className="agent-policy-audit-note">
        Esta síntesis no contiene parámetros ejecutables ni valida una mejora del detector.
      </small>
    </section>
  );
}

function PolicyAdvisoryEffect({
  contribution,
}: {
  contribution: MonitoringPolicyProposalContributionViewModel;
}) {
  return (
    <div
      aria-label={`Efecto consultivo: ${policySubjectLabel(contribution.advisorySubject)}`}
      className="agent-policy-effect"
    >
      <span>{policySubjectLabel(contribution.advisorySubject)}</span>
      <strong>{policyStateLabel(contribution.currentState)}</strong>
      <i aria-hidden="true">→</i>
      <strong>{policyStateLabel(contribution.proposedState)}</strong>
    </div>
  );
}

function policyActionLabel(action: string): string {
  return {
    maintain_policy: "Mantener política",
    intensify_observation: "Intensificar observación",
    request_human_review: "Solicitar revisión humana",
    pause_replay: "Solicitar pausa del replay",
    insufficient_evidence: "Abstenerse por evidencia insuficiente",
  }[action] ?? humanizeEvidenceToken(action);
}

function policyContributionOriginLabel(
  contribution: MonitoringPolicyProposalContributionViewModel,
): string {
  return {
    deterministic: "Proyección determinista del servidor",
    guardrail_fallback: "Salida de seguridad del servidor",
    protocol_restricted: "Salida protocolaria del servidor",
    unknown: "Salida de origen no verificable",
  }[contribution.generationOrigin] ?? "Propuesta de este rol";
}

function policyAgreementLabel(status: MonitoringPolicyProposalViewModel["agreementStatus"]): string {
  return {
    unanimous: "Acuerdo unánime",
    disagreement: "Desacuerdo entre agentes",
    invalid_review: "Revisión inválida para agregar",
  }[status];
}

function policySubjectLabel(subject: string): string {
  return {
    policy_configuration: "Configuración de política",
    observation_cadence: "Cadencia de observación",
    human_review: "Flujo de revisión humana",
    replay_execution: "Ejecución del replay",
    policy_change: "Cambio de política",
  }[subject] ?? humanizeEvidenceToken(subject);
}

function policyStateLabel(state: string): string {
  return {
    unchanged: "Sin cambios",
    current_schedule: "Cadencia actual",
    intensification_requested: "Intensificación solicitada",
    not_requested: "No solicitada",
    requested: "Solicitada",
    current_execution: "Ejecución actual",
    pause_requested: "Pausa solicitada",
    withheld: "Cambio retenido",
  }[state] ?? humanizeEvidenceToken(state);
}

function compactEvidenceTime(
  sourceTime: string | null,
  snapshotId: string | null,
): string | null {
  const match = sourceTime?.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/,
  );
  if (match) return `${match[3]}/${match[2]} ${match[4]}:${match[5]}`;
  return snapshotId ? compactAuditText(snapshotId.replace(/_/g, " "), 28) : null;
}

function humanizeEvidenceToken(value: string): string {
  return value.replace(/_/g, " ");
}

function evidenceAnalysisLabel(record: MonitoringEvidenceRecordViewModel): string {
  if (record.gapDetected) return "Gap detectado";
  const labels: Record<string, string> = {
    modeled: "Modelado",
    telemetry_only: "Telemetría",
    unavailable: "No disponible",
  };
  return record.analysisStatus ? labels[record.analysisStatus] ?? record.analysisStatus : "Registro causal";
}

function evidenceHealthLabel(value: string): string {
  const labels: Record<string, string> = {
    nominal: "Nominal",
    watch: "Vigilancia",
    warning: "Aviso",
    critical: "Crítico",
  };
  return labels[value] ?? humanizeEvidenceToken(value);
}

function formatEvidenceRatio(value: number): string {
  return new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(value);
}

function GenerationTraceStrip({ state }: { state: DecisionAgenticState }) {
  const traces = [
    state.proposalTrace ? { label: "Propuesta", trace: state.proposalTrace } : null,
    state.primaryTrace ? { label: "Efectiva", trace: state.primaryTrace } : null,
  ].filter(
    (item): item is { label: string; trace: Record<string, unknown> } => item !== null,
  );
  if (traces.length === 0) {
    return <p className="agent-trace-missing">Sin generation_trace: no puede probarse el origen.</p>;
  }
  return (
    <div className="agent-generation-strip" aria-label="Intentos de generacion observables">
      {traces.map(({ label, trace }) => {
        const origin = generationOrigin(trace);
        const status = auditText(trace.validation_status) ?? "desconocida";
        const attempt = auditScalarText(trace.attempt_index) ?? "-";
        const fallbackCause = auditText(trace.fallback_cause);
        return (
          <article className={`tone-${generationTone(origin, status)}`} key={`${label}-${auditText(trace.attempt_id) ?? attempt}`}>
            <span>{label}</span>
            <strong>{generationOriginLabel(origin)} · intento {attempt}</strong>
            <em>{generationValidationLabel(status)}</em>
            {fallbackCause ? <small title={fallbackCause}>{compactAuditText(fallbackCause, 150)}</small> : null}
          </article>
        );
      })}
    </div>
  );
}

function DecisionComparisonCard({
  agentId,
  label,
  payload,
  tone,
}: {
  agentId: string;
  label: string;
  payload: Record<string, unknown>;
  tone: "proposal" | "effective";
}) {
  const facts = decisionConfigurationFacts(payload);
  return (
    <article className={`agent-comparison-card ${tone}`}>
      <span>{label}</span>
      <strong>{roleChosenDecision(agentId, payload)}</strong>
      {facts.length > 0 ? (
        <div className="agent-comparison-facts">
          {facts.map((fact) => <em key={fact}>{fact}</em>)}
        </div>
      ) : null}
      <p>{compactAuditText(auditText(payload.rationale) ?? "Sin justificacion estructurada.", 260)}</p>
    </article>
  );
}

function AlternativeCard({
  alternative,
  index,
}: {
  alternative: Record<string, unknown>;
  index: number;
}) {
  const facts = decisionConfigurationFacts(alternative);
  const title = auditText(alternative.alternative_id)
    ?? auditText(alternative.name)
    ?? `Alternativa ${index + 1}`;
  return (
    <article className="agent-alternative-card">
      <span>Opcion {index + 1}</span>
      <strong>{title.replace(/_/g, " ")}</strong>
      {facts.length > 0 ? (
        <div className="agent-comparison-facts">
          {facts.map((fact) => <em key={fact}>{fact}</em>)}
        </div>
      ) : null}
      {auditText(alternative.rationale) ? <p>{compactAuditText(auditText(alternative.rationale)!, 220)}</p> : null}
      {auditText(alternative.expected_effect) ? (
        <small>Efecto esperado: {compactAuditText(auditText(alternative.expected_effect)!, 180)}</small>
      ) : null}
    </article>
  );
}

function decisionHypotheses(
  payload: Record<string, unknown>,
): AgentHypothesisViewModel[] {
  return hypothesisViewModelsForPayload(payload);
}

function hypothesisAssessmentLabel(
  status: AgentHypothesisViewModel["assessmentStatus"],
): string {
  const labels: Record<AgentHypothesisViewModel["assessmentStatus"], string> = {
    pending: "Pendiente de contraste",
    supported_in_run: "Apoyada en esta run",
    partially_supported: "Apoyo parcial",
    contradicted_in_run: "Refutada en esta run",
    inconclusive: "Inconclusa",
    not_evaluable: "No evaluable",
  };
  return labels[status];
}

function decisionConfigurationFacts(payload: Record<string, unknown>): string[] {
  const config = auditRecord(payload.modeling_config)
    ?? auditRecord(payload.retry_config)
    ?? auditRecord(payload.structuring_config)
    ?? auditRecord(payload.cleaning_config);
  if (!config) return [];
  const keys: Array<[string, string]> = [
    ["model_name", "modelo"],
    ["threshold_quantile", "cuantil"],
    ["n_estimators", "estimadores"],
    ["window_size", "ventana"],
    ["overlap", "solape"],
    ["label_mode", "etiquetado"],
    ["normalization", "normalizacion"],
    ["selected_channel", "canal"],
  ];
  const facts = keys.flatMap(([key, label]) => {
    const value = auditScalarText(config[key]);
    return value === null ? [] : [`${label}: ${value}`];
  });
  const features = auditStringArray(config.features);
  if (features.length > 0) facts.push(`features: ${features.slice(0, 3).join(", ")}${features.length > 3 ? ` +${features.length - 3}` : ""}`);
  return facts.slice(0, 6);
}

function decisionGateTone(state: DecisionAgenticState): "ok" | "warning" | "danger" | "muted" {
  if (state.fallback || state.nonAgentic) return "danger";
  if (state.policyOverlay || state.repaired || state.protocolRestricted) return "warning";
  if (state.firstPass) return "ok";
  return "muted";
}

function decisionGateLabel(state: DecisionAgenticState): string {
  if (state.fallback) return "Fallo · fallback";
  if (state.nonAgentic) return "Fallo · no agentica";
  if (state.policyOverlay) return "LLM + overlay";
  if (state.repaired) return "LLM reparada";
  if (state.protocolRestricted) return "LLM + protocolo";
  if (state.firstPass) return "LLM intento logico 1";
  return "Origen incompleto";
}

function generationOriginLabel(origin: AuditGenerationOrigin): string {
  const labels: Record<AuditGenerationOrigin, string> = {
    llm: "LLM",
    deterministic: "Determinista",
    guardrail_fallback: "Fallback",
    protocol_restricted: "Protocolo",
    unknown: "Desconocido",
  };
  return labels[origin];
}

function generationValidationLabel(status: string): string {
  const labels: Record<string, string> = {
    validated: "validada en el intento logico 1",
    repaired: "reparada por el LLM",
    fallback_applied: "fallback aplicado",
    unknown: "validacion desconocida",
  };
  return labels[status] ?? status.replace(/_/g, " ");
}

function generationTone(
  origin: AuditGenerationOrigin,
  status: string,
): "ok" | "warning" | "danger" | "muted" {
  if (origin === "guardrail_fallback" || origin === "deterministic") return "danger";
  if (status === "repaired" || origin === "protocol_restricted") return "warning";
  if (origin === "llm") return "ok";
  return "muted";
}

function DecisionFact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="agent-decision-fact">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function runtimeSignalChips(
  event: AgentRuntimeEvent,
): Array<{ label: string; value: string; tone: "neutral" | "warning" | "danger" }> {
  const payload = decisionPayload(event);
  const hasRecordCatalog = monitoringEvidenceCatalogModel(event) !== null;
  const chips: Array<{ label: string; value: string; tone: "neutral" | "warning" | "danger" }> = [];
  const signalKeys: Array<{ key: string; label: string; tone?: "neutral" | "warning" | "danger" }> = [
    { key: "tool_names", label: "herr. declaradas/propuestas" },
    { key: "tool_calls", label: "herr. declaradas/propuestas" },
    { key: "tools_used", label: "herr. declaradas/propuestas" },
    { key: "used_tools", label: "herr. declaradas/propuestas" },
    { key: "evidence_refs", label: "evidencia" },
    { key: "guardrail_checks", label: "guardrails", tone: "warning" },
    { key: "required_corrections", label: "correcciones", tone: "warning" },
    { key: "changes_summary", label: "cambios" },
    { key: "accepted_issue_ids", label: "issues aceptadas" },
    { key: "rejected_issue_ids", label: "issues rechazadas", tone: "warning" },
    { key: "policy_overlay_issue_ids", label: "issues de overlay", tone: "warning" },
  ];

  for (const signal of signalKeys) {
    if (hasRecordCatalog && signal.key === "evidence_refs") continue;
    const values = stringArrayFromUnknown(payload[signal.key]);
    if (values.length > 0) {
      chips.push({
        label: signal.label,
        value: compactList(values),
        tone: signal.tone ?? "neutral",
      });
    }
  }

  for (const key of ["fallback_reason", "fallback_mode", "fallback_used", "repair_error", "error"]) {
    const value = stringFromUnknown(payload[key]);
    if (value) {
      chips.push({
        label: key.replace(/_/g, " "),
        value,
        tone: key === "error" || key === "repair_error" ? "danger" : "warning",
      });
    }
  }

  const verificationStatus = stringFromUnknown(payload.verification_status);
  if (verificationStatus) {
    chips.push({
      label: "verificacion",
      value: verificationStatus,
      tone:
        verificationStatus === "approved" || verificationStatus === "ok"
          ? "neutral"
          : "warning",
    });
  }

  return chips;
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => stringFromUnknown(item))
      .filter((item): item is string => item !== null);
  }
  const scalar = stringFromUnknown(value);
  return scalar ? [scalar] : [];
}

function stringFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value && typeof value === "object") {
    const candidate = value as { name?: unknown; tool_name?: unknown };
    for (const field of [candidate.name, candidate.tool_name]) {
      if (typeof field === "string" && field.trim().length > 0) {
        return field.trim();
      }
    }
  }
  return null;
}

function compactList(values: string[]): string {
  const visible = values.slice(0, 3);
  const suffix = values.length > visible.length ? ` +${values.length - visible.length}` : "";
  return `${visible.join(", ")}${suffix}`;
}

function AgentEventTranslation({ event }: { event: AgentRuntimeEvent }) {
  return (
    <section className="agent-translation" aria-label="Traduccion del evento JSON">
      <div>
        <span>Lectura humana</span>
        <strong>{agentEventPlainText(event)}</strong>
      </div>
    </section>
  );
}

function AgentConversation({
  messages,
  onSelectAgent,
}: {
  messages: AgentConversationMessage[];
  onSelectAgent: (agentId: string) => void;
}) {
  if (messages.length === 0) {
    return (
      <p className="empty-state compact-empty">
        Sin conversacion agentica todavia
      </p>
    );
  }

  return (
    <div className="agent-chat" aria-label="Conversacion agentica">
      {messages.map((message) => (
        <button
          className={`chat-message ${message.status}`}
          key={message.id}
          type="button"
          onClick={() => onSelectAgent(message.agentId)}
        >
          <span className="chat-avatar">{agentInitials(message.agentLabel)}</span>
          <span className="chat-bubble">
            <span className="chat-meta">
              <strong>{message.agentLabel}</strong>
              <em>{formatEventTime(message.createdAt)}</em>
            </span>
            <span className="chat-role">{message.role}</span>
            <span className="chat-title">{message.title}</span>
            <span className="chat-text">{message.text}</span>
            {message.badges.length > 0 ? (
              <span className="chat-chip-row">
                {message.badges.map((badge) => (
                  <span className="chat-chip" key={`${message.id}-${badge}`}>
                    {badge}
                  </span>
                ))}
              </span>
            ) : null}
          </span>
        </button>
      ))}
    </div>
  );
}
