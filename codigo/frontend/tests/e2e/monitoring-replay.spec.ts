import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  MONITORING_AGENT_BRIDGE_SCENARIO,
  MONITORING_DISPATCH_SCENARIO,
  MONITORING_REPLAY_SCENARIO,
} from "./fixtures/monitoringReplay";
import { expectNoHorizontalOverflow } from "./support/agentHarness";
import {
  openMonitoringReplay,
  verifyAndDisposeMonitoringHarness,
} from "./support/monitoringHarness";

test.describe("Centro de monitorización histórica", () => {
  test("mantiene separado el avance causal de la inspección visual", async ({ page }) => {
    const harness = await openMonitoringReplay(page, MONITORING_REPLAY_SCENARIO);
    try {
      const source = page.getByRole("combobox", { name: "Escenario" });
      await expect(source).toHaveValue(MONITORING_REPLAY_SCENARIO.source.scenario_id);
      await expect(source).toContainText("NASA IMS Set 2 · replay causal PCA");
      const policy = page.getByRole("combobox", { name: "Política de activación" });
      await expect(policy).toHaveValue("P3");
      await expect(policy.locator("option")).toHaveCount(2);
      await expect(policy).toContainText("P3 · eventos con persistencia (recomendada)");
      await expect(policy).toContainText("P0 · observación sin triggers");
      await policy.selectOption("P0");
      await expect(policy).toHaveValue("P0");
      await policy.selectOption("P3");

      const createSession = page.getByRole("button", { name: "Preparar sesión" });
      await expect(createSession).toBeEnabled();
      await createSession.click();
      await expect(page.getByRole("button", { name: "Nueva sesión" })).toBeVisible();
      expect(harness.api.sessionRequests).toEqual([
        {
          activation_policy_kind: "P3",
          scenario_id: MONITORING_REPLAY_SCENARIO.source.scenario_id,
        },
      ]);
      await expect(sessionSignal(page, "Política")).toContainText("P3 · e2e-event-driven-p3-v1");

      const assetGroup = page.getByRole("group", {
        name: "Seleccionar canal para inspección",
      });
      await expect(assetGroup.getByRole("button")).toHaveCount(4);
      await expect(
        assetGroup.getByRole("button", { name: /Bearing 1.*Canal modelado/ }),
      ).toBeVisible();
      await expect(
        assetGroup.getByRole("button", { name: /Bearing 2.*Solo telemetría/ }),
      ).toBeVisible();

      const step = page.getByRole("button", { name: "Ejecutar un paso" });
      await step.click();
      await expect(page.locator(".monitoring-live-status")).toContainText("Tick causal confirmado");
      await expect(page.locator(".monitoring-view [role='status']")).toHaveText("");
      expect(harness.api.stepRequests).toHaveLength(1);
      expect(harness.api.stepRequests[0]).toMatchObject({ expected_revision: 0 });
      expect(harness.api.stepRequests[0].command_id).toMatch(/^mon-step-[A-Za-z0-9-]+$/);

      const modeledCard = assetGroup.getByRole("button", {
        name: /Bearing 1.*Canal modelado/,
      });
      await expect(modeledCard).toBeVisible();
      await expect(modeledCard).toContainText("Advertencia");
      await expect(modeledCard).toHaveAccessibleName(/HI 30,0.*riesgo 70,0/);
      const statusPanel = page.locator(".monitoring-status-card");
      await expect(statusPanel).toContainText("Score");
      await expect(statusPanel).toContainText("1,000");
      await expect(statusPanel).toContainText("El score no supera el umbral congelado");
      await expect(statusPanel).toContainText(
        "La etiqueta de salud combina score, riesgo y política temporal",
      );

      const telemetryCard = assetGroup.getByRole("button", {
        name: /Bearing 2.*Solo telemetría.*sin diagnóstico/,
      });
      await telemetryCard.click();
      await expect(telemetryCard).toHaveAttribute("aria-pressed", "true");
      await expect(statusPanel).toContainText("No se infiere estado de salud");
      await expect(statusPanel.locator(".monitoring-metric")).toHaveCount(4);
      await expect(
        statusPanel.locator(".monitoring-metric").filter({ hasText: "Diagnóstico" }),
      ).toContainText("No disponible");
      await expect(
        statusPanel.locator(".monitoring-metric").filter({
          hasText: /Índice de salud|Riesgo|Score|Umbral/,
        }),
      ).toHaveCount(0);

      await page.getByRole("tab", { name: "Replay 2D" }).click();
      const chart = page.locator(".monitoring-score-chart");
      await expect(chart).toHaveAttribute("aria-label", /1 snapshots ejecutados/);
      await expect(page.locator(".monitoring-chart-future")).toHaveCount(1);
      await expectPolylinePointCount(page, 1);

      await step.click();
      await expect.poll(() => harness.api.stepRequests.length).toBe(2);
      expect(harness.api.stepRequests[1]).toMatchObject({ expected_revision: 1 });
      await expect(chart).toHaveAttribute("aria-label", /2 snapshots ejecutados/);
      await expectPolylinePointCount(page, 2);
      await expect(sessionSignal(page, "Cursor ejecutado")).toContainText(
        "2 · 2004.02.14.12.01.00",
      );
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText(
        "2 · 2004-02-14 12:01:00",
      );
      await expect(page.locator(".monitoring-view [role='status']")).toContainText(
        "2 triggers actualizados en el snapshot 2004.02.14.12.01.00",
      );
      const triggerBadge = modeledCard.locator(".monitoring-asset-trigger-badge");
      await expect(triggerBadge).toHaveAttribute("data-lifecycle", "emitted");
      await expect(triggerBadge).toContainText("2");

      const groupedTriggerMarker = page.locator(
        '.monitoring-trigger-marker[data-trigger-id="trg-monitoring-critical"]',
      );
      await expect(groupedTriggerMarker).toHaveAttribute("data-trigger-count", "2");
      await expect(groupedTriggerMarker).toHaveAttribute("data-lifecycle", "emitted");
      await expect(groupedTriggerMarker).toHaveAttribute("aria-pressed", "true");
      await expect(groupedTriggerMarker).toHaveAccessibleName(
        /2 triggers agrupados.*snapshot 2.*Cambio de estado.*Emitido.*sin run enlazada/,
      );
      await expectMinimumTargetSize(groupedTriggerMarker, 44);
      await groupedTriggerMarker.focus();
      await page.keyboard.press("Enter");
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText("2 ·");
      expect(harness.api.stepRequests).toHaveLength(2);
      await page.getByRole("tab", { name: "Estado" }).click();
      const selectedTriggerPanel = page.locator(".monitoring-trigger-card");
      await expect(selectedTriggerPanel.getByRole("heading", { name: "Trigger seleccionado" })).toBeVisible();
      await expect(selectedTriggerPanel).toContainText("Cambio de estado");
      await expect(selectedTriggerPanel).toContainText("Emitido · sin run");
      await expect(selectedTriggerPanel.getByText(/El canal modelado cambia/)).not.toBeVisible();
      await expect(selectedTriggerPanel.locator("details")).not.toHaveAttribute("open", "");
      await page.getByRole("tab", { name: "Replay 2D" }).click();

      await page.getByRole("button", { name: "Snapshot anterior para inspección" }).click();
      await expect(sessionSignal(page, "Cursor ejecutado")).toContainText("2 ·");
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText(
        "1 · 2004-02-14 12:00:00",
      );
      expect(harness.api.stepRequests).toHaveLength(2);

      await page
        .getByRole("button", { name: "Snapshot siguiente ya ejecutado para inspección" })
        .click();
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText(
        "2 · 2004-02-14 12:01:00",
      );
      expect(harness.api.stepRequests).toHaveLength(2);

      await step.click();
      await expect.poll(() => harness.api.stepRequests.length).toBe(3);
      expect(harness.api.stepRequests[2]).toMatchObject({ expected_revision: 2 });
      await expect(chart).toHaveAttribute(
        "aria-label",
        /3 snapshots ejecutados.*1 hueco de continuidad detectado/,
      );
      await expectPolylinePointCount(page, 3);
      await expect(page.locator(".monitoring-score-line")).toHaveCount(2);
      await expect(page.locator(".monitoring-gap-line")).toHaveCount(1);
      await expect(
        page.getByRole("button", {
          name: "Hueco de continuidad antes del snapshot 3, intervalo 20 minutos",
        }),
      ).toBeVisible();
      await expect(
        page.locator(".monitoring-state-segment.state-critical"),
      ).toHaveCount(2);

      const coalescedMarker = page.locator(
        '.monitoring-trigger-marker[data-trigger-id="trg-gap-coalesced"]',
      );
      await expect(coalescedMarker).toHaveAttribute("data-lifecycle", "coalesced");
      await expect(coalescedMarker).toHaveAttribute("data-trigger-count", "3");
      await expect(coalescedMarker).toHaveAttribute("aria-pressed", "true");
      await expectMinimumTargetSize(coalescedMarker, 44);

      await page.getByRole("tab", { name: "Eventos" }).click();
      const summary = page.getByRole("group", { name: "Resumen de triggers" });
      await expect(summary).toContainText("0 atención");
      await expect(summary).toContainText("0 en análisis");
      await expect(summary).toContainText("2 no ejecutados");
      await expect(summary).toContainText("1 cerrados");

      const triggerList = page.getByRole("list", { name: "Triggers de la sesión" });
      await expect(triggerList.getByRole("listitem")).toHaveCount(3);
      const failedRow = triggerList.locator('[data-trigger-id="trg-monitoring-critical"]');
      await expect(failedRow).toHaveAttribute("data-lifecycle", "failed");
      await expect(failedRow).toContainText("Fallido");
      await expect(failedRow).toContainText("Sin run");
      await expect(failedRow.locator("details")).not.toHaveAttribute("open", "");
      await expect(failedRow.getByText(/La revisión no llegó a despacharse/)).not.toBeVisible();
      await failedRow.locator("summary").click();
      await expect(failedRow.getByRole("list", { name: "Historial del trigger" }).getByRole("listitem")).toHaveCount(2);
      await expect(failedRow.getByRole("list", { name: "Historial del trigger" })).toContainText("Emitido");
      await expect(failedRow.getByRole("list", { name: "Historial del trigger" })).toContainText("Fallido");
      await expect(failedRow.getByText(/La revisión no llegó a despacharse/)).toBeVisible();
      await expect(failedRow).toContainText("No se ha ejecutado");
      await failedRow.getByRole("button", { name: "Examinar snapshot causal" }).click();
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText(
        "2 · 2004-02-14 12:01:00",
      );
      expect(harness.api.stepRequests).toHaveLength(3);
      const selectedFailedMarker = page.locator(
        '.monitoring-trigger-marker[data-trigger-id="trg-monitoring-critical"]',
      );
      await expect(selectedFailedMarker).toHaveAttribute("data-lifecycle", "failed");
      await expect(selectedFailedMarker).toHaveAttribute("aria-pressed", "true");
      await page.getByRole("tab", { name: "Eventos" }).click();
      await expect(failedRow).toHaveClass(/selected/);

      const suppressedRow = triggerList.locator('[data-trigger-id="trg-persistent-suppressed"]');
      await expect(suppressedRow).toContainText("Suprimido");
      await suppressedRow.locator("summary").click();
      await expect(suppressedRow).toContainText("trg-monitoring-critical");
      const coalescedRow = triggerList.locator('[data-trigger-id="trg-gap-coalesced"]');
      await expect(coalescedRow).toContainText("Agrupado");
      await coalescedRow.locator("summary").click();
      await expect(coalescedRow).toContainText("trg-monitoring-critical");
      await expect(page.getByText("Run enlazada", { exact: true })).toHaveCount(0);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("abre la run hija y vuelve al trigger sin avanzar el replay", async ({ page }) => {
    const harness = await openMonitoringReplay(
      page,
      MONITORING_AGENT_BRIDGE_SCENARIO,
    );
    try {
      await page.getByRole("button", { name: "Preparar sesión" }).click();
      const step = page.getByRole("button", { name: "Ejecutar un paso" });
      await step.click();
      await step.click();
      await step.click();
      expect(harness.api.stepRequests).toHaveLength(3);

      await page.getByRole("tab", { name: "Eventos" }).click();
      const triggerList = page.getByRole("list", { name: "Triggers de la sesión" });
      const runningRow = triggerList.locator(
        '[data-trigger-id="trg-monitoring-critical"]',
      );
      await expect(runningRow).toHaveAttribute("data-lifecycle", "running");
      await expect(runningRow).toContainText("En ejecución");
      await expect(runningRow).toContainText("Run enlazada");
      await runningRow.locator("summary").click();

      const childRunId = MONITORING_AGENT_BRIDGE_SCENARIO.childJob?.run_id;
      expect(childRunId).toBeTruthy();
      const openAgents = runningRow.getByRole("button", {
        name: new RegExp(`Ver agentes en curso.*run ${childRunId}`),
      });
      await expectMinimumTargetSize(openAgents, 44);
      await openAgents.focus();
      await openAgents.press("Enter");

      const navigation = page.getByRole("navigation", { name: "Vistas principales" });
      await expect(navigation.getByRole("button", { name: "Agentes" })).toHaveAttribute(
        "aria-current",
        "page",
      );
      const causalContext = page.getByRole("region", {
        name: "Contexto de revisión desde Monitorización",
      });
      await expect(causalContext).toBeFocused();
      await expect(causalContext).toContainText("Cambio de estado");
      await expect(causalContext).toContainText("En ejecución");
      await expect(causalContext).toContainText(childRunId ?? "");
      await expect(causalContext).toContainText(
        "Enlace a nivel de run · sin decisión exacta seleccionada",
      );
      await expect(page.locator(".run-context-disclosure")).toHaveCount(0);
      await expect(
        page.getByRole("heading", { name: "Una historia de decisiones y memoria" }),
      ).toBeVisible();

      const back = causalContext.getByRole("button", {
        name: "Volver al trigger Cambio de estado en Monitorización",
      });
      await expectMinimumTargetSize(back, 44);
      await back.click();

      await expect(
        navigation.getByRole("button", { name: "Monitorización" }),
      ).toHaveAttribute("aria-current", "page");
      await expect(page.getByRole("tab", { name: "Eventos" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await expect(sessionSignal(page, "Cursor ejecutado")).toContainText("3 ·");
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText("2 ·");
      const restoredRow = page
        .getByRole("list", { name: "Triggers de la sesión" })
        .locator('[data-trigger-id="trg-monitoring-critical"]');
      await expect(restoredRow).toHaveClass(/selected/);
      await expect(restoredRow.locator("summary")).toBeFocused();
      await expect(restoredRow).toContainText("En ejecución");
      await expect(restoredRow).toContainText("Run enlazada");
      expect(harness.api.stepRequests).toHaveLength(3);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });

  test("lanza manualmente una revisión y conserva el contexto causal", async ({ page }) => {
    const harness = await openMonitoringReplay(page, MONITORING_DISPATCH_SCENARIO);
    try {
      await page.getByRole("button", { name: "Preparar sesión" }).click();
      const step = page.getByRole("button", { name: "Ejecutar un paso" });
      await step.click();
      await step.click();
      expect(harness.api.stepRequests).toHaveLength(2);
      expect(harness.api.dispatchRequests).toHaveLength(0);

      const triggerPanel = page.getByRole("region", {
        name: "Trigger seleccionado: Cambio de estado",
      });
      await expect(triggerPanel).toContainText("Emitido · sin run");
      const dispatch = triggerPanel.getByRole("button", {
        name: /revisión para el trigger Cambio de estado/,
      });
      await expectMinimumTargetSize(dispatch, 44);
      await dispatch.focus();
      await dispatch.press("Enter");

      await expect.poll(() => harness.api.dispatchRequests.length).toBe(1);
      expect(harness.api.dispatchRequests[0]).toMatchObject({
        expected_child_revision: 0,
      });
      expect(harness.api.dispatchRequests[0].command_id).toMatch(
        /^mon-dispatch-[A-Za-z0-9-]+$/,
      );
      await expect(dispatch).toBeDisabled();
      await expect(dispatch).toHaveAttribute("aria-busy", "true");
      await expect(dispatch).toContainText("Lanzando…");
      expect(harness.api.stepRequests).toHaveLength(2);

      harness.api.releaseDispatchResponse();
      await expect(triggerPanel).toContainText("Despachado · con run");
      await expect(dispatch).toHaveCount(0);
      await expect(page.locator(".monitoring-live-status")).toContainText(
        "Revisión lanzada",
      );
      await expect(sessionSignal(page, "Cursor ejecutado")).toContainText("2 ·");
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText("2 ·");
      expect(harness.api.stepRequests).toHaveLength(2);
      expect(harness.api.dispatchRequests).toHaveLength(1);

      const childRunId = MONITORING_DISPATCH_SCENARIO.childJob?.run_id;
      expect(childRunId).toBeTruthy();
      const openAgents = triggerPanel.getByRole("button", {
        name: new RegExp(`Abrir run despachada.*run ${childRunId}`),
      });
      await expectMinimumTargetSize(openAgents, 44);
      await openAgents.click();

      const causalContext = page.getByRole("region", {
        name: "Contexto de revisión desde Monitorización",
      });
      await expect(causalContext).toBeFocused();
      await expect(causalContext).toContainText("Despachado");
      await expect(causalContext).toContainText(childRunId ?? "");
      await causalContext.getByRole("button", {
        name: "Volver al trigger Cambio de estado en Monitorización",
      }).click();

      await expect(triggerPanel).toBeFocused();
      await expect(triggerPanel).toContainText("Despachado · con run");
      await expect(sessionSignal(page, "Cursor ejecutado")).toContainText("2 ·");
      await expect(sessionSignal(page, "Cursor inspeccionado")).toContainText("2 ·");
      expect(harness.api.stepRequests).toHaveLength(2);
      expect(harness.api.dispatchRequests).toHaveLength(1);
      await expectNoHorizontalOverflow(page);
    } finally {
      harness.api.releaseDispatchResponse();
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });
});

function sessionSignal(page: Page, label: string) {
  return page.locator(".monitoring-session-bar > div").filter({ hasText: label });
}

async function expectPolylinePointCount(page: Page, expected: number): Promise<void> {
  await expect
    .poll(async () => {
      return page.locator(".monitoring-score-line").evaluateAll((lines) =>
        lines.reduce((count, line) => {
          const points = line.getAttribute("points") ?? "";
          return count + points.trim().split(/\s+/).filter(Boolean).length;
        }, 0),
      );
    })
    .toBe(expected);
}

async function expectMinimumTargetSize(locator: Locator, minimum: number): Promise<void> {
  const box = await locator.boundingBox();
  expect(box, "El marcador debe conservar un objetivo táctil visible.").not.toBeNull();
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(minimum);
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(minimum);
}
