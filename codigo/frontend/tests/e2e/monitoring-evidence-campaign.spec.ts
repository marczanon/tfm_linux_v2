import { expect, test } from "@playwright/test";

import {
  MONITORING_CAMPAIGN_RESOLVED_SCENARIO,
  MONITORING_CAMPAIGN_SCENARIO,
} from "./fixtures/monitoringReplay";
import { expectNoHorizontalOverflow } from "./support/agentHarness";
import {
  openMonitoringReplay,
  verifyAndDisposeMonitoringHarness,
} from "./support/monitoringHarness";


test.describe("campaña de evidencia NASA", () => {
  test("captura preflight 16:9 versionada", async ({ page }, testInfo) => {
    const captureEnabled = (
      globalThis as typeof globalThis & {
        process?: { env?: Record<string, string | undefined> };
      }
    ).process?.env?.TFM_CAPTURE_CINEMATIC_PREFLIGHT === "1";
    test.skip(
      !captureEnabled || testInfo.project.name !== "desktop-chromium",
      "Captura explícita; no escribe artefactos durante la regresión normal.",
    );
    await page.setViewportSize({ width: 2_000, height: 1_200 });
    const harness = await openMonitoringReplay(page, MONITORING_CAMPAIGN_RESOLVED_SCENARIO);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      await expect(page.getByTestId("monitoring-hypothesis")).toContainText(
        /plantea una recomendación consultiva/i,
      );
      const stage = page.getByTestId("monitoring-cinematic-stage");
      await expect(stage).toContainText("FIXTURE · PREFLIGHT");
      await stage.evaluate((element) => {
        element.style.boxSizing = "border-box";
        element.style.width = "1920px";
        // Chromium redondea el borde inferior del locator a un píxel adicional.
        element.style.height = "1079px";
        element.style.aspectRatio = "auto";
      });
      await stage.screenshot({
        animations: "disabled",
        path: "../reports/validation_figures/monitoring_cinematic_preflight.png",
      });
      await stage.screenshot({
        animations: "disabled",
        path: "../../memoria/figuras/captura_web_cinematica_monitorizacion_preflight.png",
      });
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("observa la sesión publicada sin avanzar ni despachar desde el navegador", async ({ page }) => {
    const harness = await openMonitoringReplay(page, MONITORING_CAMPAIGN_SCENARIO);
    try {
      const campaign = page.getByRole("region", { name: "Pre-roll causal en curso" });
      await expect(campaign).toBeVisible();
      await expect(campaign).toContainText("55 h 50 min");
      await expect(campaign).toContainText("1/689 ticks");
      await expect(campaign).toContainText("0/4");
      await expect(campaign).toContainText("0/28");
      await expect(campaign).toContainText("0 fallback");
      await expect(campaign).toContainText("propuestas no aplicadas");
      await expect(campaign).toContainText("Histórico acelerado");
      await expect(campaign).toContainText("Memoria OFF");
      await expect(campaign).toContainText("política no aplicada");
      await expect(
        campaign.getByRole("list", { name: "Cuatro revisiones primarias de la campaña" })
          .getByRole("listitem"),
      ).toHaveCount(4);
      await expect(campaign).toContainText("cursor 353");
      await expect(
        campaign.getByText("Sellos de prerregistro y publicación"),
      ).toBeVisible();

      await campaign.getByRole("button", { name: "Abrir sesión" }).click();
      await expect(page.getByRole("tab", { name: "Cinemática" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await expect(page.getByTestId("monitoring-cinematic-stage")).toBeVisible();
      await expect(page.getByTestId("monitoring-bearing-rig")).toContainText("Solo telemetría");
      await expect(page.getByTestId("monitoring-score-ratio-trend")).toHaveAttribute("data-scale", "log10");
      await page.getByRole("tab", { name: "Replay 2D" }).click();
      await expect(page.locator(".monitoring-score-chart")).toHaveAttribute("aria-label", /1 snapshots ejecutados/);
      await expect(page.locator(".monitoring-managed-rate")).toContainText("60×");
      await expect(page.getByRole("button", { name: "Ejecutar un paso" })).toBeDisabled();
      await expect(page.getByRole("button", { name: "Reproducir mediante pasos causales" })).toBeDisabled();
      expect(harness.api.sessionRequests).toHaveLength(0);
      expect(harness.api.stepRequests).toHaveLength(0);
      expect(harness.api.dispatchRequests).toHaveLength(0);

      await expect.poll(() => harness.api.campaignRequests, { timeout: 6_000 }).toBeGreaterThan(1);
      expect(harness.api.stepRequests).toHaveLength(0);
      expect(harness.api.dispatchRequests).toHaveLength(0);
      await expectNoHorizontalOverflow(page);
      await page.goto("about:blank");
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("visualiza una revisión resuelta sin convertir hipótesis en diagnóstico", async ({ page }) => {
    const harness = await openMonitoringReplay(page, MONITORING_CAMPAIGN_RESOLVED_SCENARIO);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      const stage = page.getByTestId("monitoring-cinematic-stage");
      await expect(stage).toBeVisible();
      await expect(stage).toContainText("FIXTURE · PREFLIGHT");
      await expect(stage).toContainText("Estado y telemetría observados");
      await expect(stage).toContainText("Esquema, no gemelo digital");
      await expect(stage.locator(".monitoring-bearing-readings article.analysis-telemetry_only")).toHaveCount(3);
      await expect(stage.getByText("Solo telemetría", { exact: true })).toHaveCount(3);

      const heatmap = page.getByTestId("monitoring-evidence-heatmap");
      await expect(heatmap.locator(".monitoring-agent-heat-cell")).toHaveCount(28);
      await expect(heatmap.locator(".monitoring-agent-heat-cell.state-first_pass")).toHaveCount(7);
      await expect(page.getByTestId("monitoring-hypothesis")).toContainText(/plantea una recomendación consultiva/i);
      await expect(page.getByTestId("monitoring-hypothesis")).toContainText(/catálogo E0/i);
      await expect(stage).toContainText("NO APLICADA");
      await expect(stage).toContainText("no diagnóstico físico");
      await expect(stage).toContainText("No es probabilidad");
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("incorpora ticks incrementales sin recargar la sesión completa en cada heartbeat", async ({ page }) => {
    const scenario = structuredClone(MONITORING_CAMPAIGN_SCENARIO);
    const initial = structuredClone(scenario.campaign!);
    const advanced = structuredClone(initial);
    advanced.current_revision = 2;
    advanced.execution_cursor = 1;
    advanced.progress_ratio = 2 / 689;
    advanced.runtime_elapsed_seconds = 22;
    advanced.updated_at = "2026-08-18T10:00:22Z";
    // El heartbeat oficial llega cada 5 s y el observador consulta cada 4 s:
    // una respuesta sin cambios no puede detener el bucle incremental.
    scenario.campaignUpdates = [initial, initial, advanced];
    const harness = await openMonitoringReplay(page, scenario);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      expect(harness.api.sessionGetRequests).toBe(1);
      await expect.poll(() => harness.api.tickListAfterSequences.length, { timeout: 11_000 }).toBe(1);
      expect(harness.api.tickListAfterSequences).toEqual([1]);
      expect(harness.api.sessionGetRequests).toBe(1);
      await expect(page.getByTestId("monitoring-cinematic-stage")).toContainText("2/689");
      await expect(page.getByTestId("monitoring-health-trend").getByRole("img")).toHaveAttribute(
        "aria-label",
        /2 observaciones/,
      );
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("acepta una timeline post-hoc de 726 beats sin esperas temporales", async ({ page }) => {
    await installInjectedCinematicTimeline(page);
    const harness = await openMonitoringReplay(page, MONITORING_CAMPAIGN_RESOLVED_SCENARIO);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      const slider = page.getByRole("slider", { name: "Seleccionar acto de la cinemática" });
      await expect(slider).toHaveAttribute("min", "0");
      await expect(slider).toHaveAttribute("max", "725");
      await slider.fill("354");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(0);
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator("article").first().getByLabel("0 de 7 agentes")).toHaveCount(1);
      await expect(page.getByTestId("monitoring-hypothesis")).toContainText("Sin hipótesis revelada");
      await expect(page.getByTestId("monitoring-cinematic-stage")).not.toContainText("NO APLICADA");
      await slider.fill("355");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(1);
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator("article").first().getByLabel("1 de 7 agentes")).toHaveCount(1);
      await expect(page.getByTestId("monitoring-hypothesis")).toContainText("Hipótesis post-hoc de supervisor");
      await slider.fill("362");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(7);
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator("article").first().getByLabel("7 de 7 agentes")).toHaveCount(1);
      await expect(page.getByTestId("monitoring-cinematic-stage")).toContainText("NO APLICADA");
      await slider.fill("716");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(21);
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator("article").nth(3).getByLabel("0 de 7 agentes")).toHaveCount(1);
      await slider.fill("717");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(22);
      await slider.fill("724");
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator(".state-first_pass")).toHaveCount(28);
      await expect(page.getByTestId("monitoring-evidence-heatmap").locator("article").nth(3).getByLabel("7 de 7 agentes")).toHaveCount(1);
      await slider.fill("725");
      await expect(page.getByTestId("monitoring-cinematic-stage")).toHaveAttribute(
        "data-beat-index",
        "725",
      );
      await expect(page.getByTestId("monitoring-cinematic-stage")).toContainText(
        "Veredicto de evidencia: passed",
      );
      await expect(page.getByRole("slider", { name: "Seleccionar acto de la cinemática" })).toHaveCount(1);
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("distingue una revisión no válida de un desacuerdo", async ({ page }) => {
    await installInjectedCinematicTimeline(page, true);
    const harness = await openMonitoringReplay(page, MONITORING_CAMPAIGN_RESOLVED_SCENARIO);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      await page.getByRole("slider", { name: "Seleccionar acto de la cinemática" }).fill("362");
      const stage = page.getByTestId("monitoring-cinematic-stage");
      await expect(stage).toContainText("Revisión no válida");
      await expect(stage).not.toContainText("Desacuerdo visible");
      await expect(stage).toContainText("NO APLICADA");
      await expect(
        page.getByTestId("monitoring-evidence-heatmap").locator("article").first(),
      ).toHaveAttribute("data-lifecycle", "failed");
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("mantiene el bloqueo observador si falla el polling", async ({ page }) => {
    const scenario = structuredClone(MONITORING_CAMPAIGN_SCENARIO);
    scenario.campaignFailure = { afterRequestCount: 1, status: 503 };
    const harness = await openMonitoringReplay(page, scenario);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      await expect(page.getByRole("button", { name: "Ejecutar un paso" })).toBeDisabled();
      await expect(
        page.getByRole("heading", { name: "No se pudo consultar la campaña" }),
      ).toBeVisible({ timeout: 6_000 });
      await expect(page.getByRole("button", { name: "Ejecutar un paso" })).toBeDisabled();
      await expect(
        page.getByRole("button", { name: "Reproducir mediante pasos causales" }),
      ).toBeDisabled();
      expect(harness.api.stepRequests).toHaveLength(0);
      expect(harness.api.dispatchRequests).toHaveLength(0);
      consumeExpectedHttpError(harness.browserErrors, 503);
      await page.goto("about:blank");
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("recupera el polling tras un fallo transitorio sin habilitar mutaciones", async ({ page }) => {
    const scenario = structuredClone(MONITORING_CAMPAIGN_SCENARIO);
    const initial = structuredClone(scenario.campaign!);
    const advanced = structuredClone(initial);
    advanced.current_revision = 2;
    advanced.execution_cursor = 1;
    advanced.progress_ratio = 2 / 689;
    advanced.updated_at = "2026-08-18T10:00:22Z";
    scenario.campaignUpdates = [initial, initial, advanced];
    scenario.campaignFailure = {
      afterRequestCount: 1,
      status: 503,
      untilRequestCount: 2,
    };
    const harness = await openMonitoringReplay(page, scenario);
    try {
      await page.getByRole("button", { name: "Abrir sesión" }).click();
      await expect(
        page.getByRole("heading", { name: "No se pudo consultar la campaña" }),
      ).toBeVisible({ timeout: 6_000 });
      await expect.poll(() => harness.api.tickListAfterSequences.length, {
        timeout: 11_000,
      }).toBe(1);
      await expect(page.getByTestId("monitoring-cinematic-stage")).toContainText("2/689");
      await expect(page.getByRole("button", { name: "Ejecutar un paso" })).toBeDisabled();
      expect(harness.api.stepRequests).toHaveLength(0);
      expect(harness.api.dispatchRequests).toHaveLength(0);
      consumeExpectedHttpError(harness.browserErrors, 503);
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("distingue un conflicto de integridad de un fallo de consulta", async ({ page }) => {
    const scenario = structuredClone(MONITORING_CAMPAIGN_SCENARIO);
    scenario.campaignFailure = { afterRequestCount: 1, status: 409 };
    const harness = await openMonitoringReplay(page, scenario);
    try {
      await expect(
        page.getByRole("heading", { name: "Publicación no verificable" }),
      ).toBeVisible({ timeout: 6_000 });
      await expect(page.getByText(/no supera la verificación de integridad/i)).toBeVisible();
      consumeExpectedHttpError(harness.browserErrors, 409);
      await page.goto("about:blank");
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });
});

function consumeExpectedHttpError(errors: string[], status: number): void {
  const marker = `status of ${status}`;
  expect(errors.filter((item) => item.includes(marker))).toHaveLength(1);
  const unexpected = errors.filter((item) => !item.includes(marker));
  errors.splice(0, errors.length, ...unexpected);
}

async function installInjectedCinematicTimeline(
  page: import("@playwright/test").Page,
  invalidProposal = false,
) {
  await page.addInitScript(({ invalidProposal: useInvalidProposal }) => {
    const assets = [1, 2, 3, 4].map((index) => ({
      analysis_status: index === 1 ? "modeled" : "telemetry_only",
      asset_id: `bearing_${index}`,
      asset_label: `B${index}`,
      channel_id: `channel_${index}`,
      gap_detected: false,
      health_index: index === 1 ? 28 : null,
      health_state: index === 1 ? "warning" : null,
      health_state_label: index === 1 ? "Advertencia" : null,
      risk_index: index === 1 ? 72 : null,
      score: index === 1 ? 1.35 : null,
      score_ratio: index === 1 ? 1.35 : null,
      signal_peak_abs: 0.7 * index,
      signal_rms: 0.13 * index,
      threshold: index === 1 ? 1 : null,
    }));
    const agents = [
      ["supervisor", "Supervisor"],
      ["cleaner", "Limpiador"],
      ["structurer", "Estructurador"],
      ["modeler", "Modelador"],
      ["evaluator", "Evaluador"],
      ["report_writer", "Redactor"],
      ["report_verifier", "Verificador"],
    ];
    const contexts = [
      { cursor: 353, ordinal: 1, proposalIndex: 362, triggerIndex: 354, triggerType: "state_transition", triggerLabel: "Cambio de estado" },
      { cursor: 498, ordinal: 2, proposalIndex: 516, triggerIndex: 508, triggerType: "persistent_alert", triggerLabel: "Alerta persistente" },
      { cursor: 499, ordinal: 3, proposalIndex: 526, triggerIndex: 518, triggerType: "state_transition", triggerLabel: "Cambio de estado" },
      { cursor: 688, ordinal: 4, proposalIndex: 724, triggerIndex: 716, triggerType: "session_close", triggerLabel: "Cierre de sesión" },
    ];
    const beats = Array.from({ length: 726 }, (_, beatIndex) => {
      const final = beatIndex === 725;
      const context = contexts.find(
        (item) => beatIndex >= item.triggerIndex && beatIndex <= item.proposalIndex,
      ) ?? null;
      const trigger = context !== null && beatIndex === context.triggerIndex;
      const decisionOffset = context ? beatIndex - context.triggerIndex - 1 : -1;
      const decisionAgent = decisionOffset >= 0 && decisionOffset < agents.length
        ? agents[decisionOffset]
        : null;
      const proposal = context !== null && beatIndex === context.proposalIndex;
      const completedContexts = contexts.filter(
        (item) => item.proposalIndex < beatIndex,
      ).length;
      const cursor = context?.cursor ?? Math.min(688, beatIndex - completedContexts * 9);
      return {
        beat_index: beatIndex,
        beat_sha256: String(beatIndex % 10).repeat(64),
        campaign_id: "fixture-cinematic-726",
        child_run_id: context ? `fixture-child-${context.ordinal}` : null,
        cursor,
        decision_id: decisionAgent ? `fixture-decision-${decisionAgent[0]}` : null,
        decision_sha256: null,
        display_projection: {
          assets,
          cursor,
          decision: decisionAgent ? {
            action_label: "Mantener política",
            agent_name: decisionAgent[0],
            confidence: 0.82,
            evidence_handles: ["E02"],
            expected_observation: "La tendencia continuará dentro del prefijo visible.",
            falsification_criterion: "Una observación posterior contradice la tendencia.",
            generation_origin: "llm",
            generation_validation_status: "validated",
            hypothesis: `Hipótesis post-hoc de ${decisionAgent[0]} en acto ${context?.ordinal}`,
            recommended_action: "maintain_policy",
            role_label: decisionAgent[1],
          } : null,
          phase: final ? "closing" : beatIndex < 353 ? "pre_roll" : "agentic_window",
          proposal: proposal ? {
            action_counts: { maintain_policy: 7 },
            aggregate_action: useInvalidProposal ? null : "maintain_policy",
            agreement_label: useInvalidProposal ? "Revisión no válida" : "Acuerdo unánime",
            agreement_status: useInvalidProposal ? "invalid_review" : "unanimous",
            application_status: "not_applied",
            human_review_recommended: false,
            status: useInvalidProposal ? "invalid_review" : "advisory_not_applied",
          } : null,
          source_time: final ? "2004-02-19T06:22:39" : "2004-02-16T22:32:39",
          subtitle: final ? "Cierre determinista de fixture" : "Beat post-hoc de fixture",
          title: final ? "Fixture completada" : "Fixture cinemática",
          trigger: trigger && context ? {
            cutoff_cursor: context.cursor,
            ordinal: context.ordinal,
            summary: `Trigger ${context.ordinal} visible en la fixture.`,
            trigger_type: context.triggerType,
            trigger_type_label: context.triggerLabel,
          } : null,
          verdict: final ? {
            agentic: "passed",
            blockers: [],
            evidence: "passed",
            operational: "passed",
          } : null,
        },
        duration_frames: 1,
        event_id: null,
        kind: final
          ? "final_verdict"
          : trigger
            ? "trigger"
            : decisionAgent
              ? "agent_decision"
              : proposal
                ? "policy_proposal"
                : "tick",
        previous_beat_sha256: beatIndex === 0 ? "0".repeat(64) : String((beatIndex - 1) % 10).repeat(64),
        proposal_id: null,
        proposal_sha256: null,
        replay_commit_sha256: "a".repeat(64),
        schema_version: "monitoring_cinematic_beat_v1",
        session_id: "e2e-monitoring-replay",
        source_time: final ? "2004-02-19T06:22:39" : "2004-02-16T22:32:39",
        tick_id: `fixture-tick-${beatIndex}`,
        wall_time: null,
      };
    });
    const target = window as typeof window & {
      __TFM_MONITORING_CINEMATIC_TIMELINE__?: unknown;
    };
    target.__TFM_MONITORING_CINEMATIC_TIMELINE__ = beats;
  }, { invalidProposal });
}
