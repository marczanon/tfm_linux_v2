import { expect, test } from "@playwright/test";

import { MONITORING_GATE_SCENARIO } from "./fixtures/monitoringReplay";
import {
  openMonitoringReplay,
  verifyAndDisposeMonitoringHarness,
} from "./support/monitoringHarness";


test.describe("gate agentivo publicado", () => {
  test("muestra el v3 bloqueado, resume 3 × 4 × 7 y enlaza sus runs", async ({ page }) => {
    const harness = await openMonitoringReplay(page, MONITORING_GATE_SCENARIO);
    try {
      const gate = page.getByRole("region", { name: "Gate agentivo bloqueado" });
      await expect(gate).toBeVisible();
      await expect(gate).toContainText("qwen3.5:4b");
      await expect(gate).toContainText("Memoria OFF");
      await expect(gate).toContainText("3/3");
      await expect(gate).toContainText("11/12");
      await expect(gate).toContainText("84/84");
      await expect(page.getByRole("heading", { name: "El replay todavía no ha comenzado" })).toBeVisible();

      await gate.getByRole("button", { name: "Ver batería" }).click();
      await expect(gate.locator(".monitoring-gate-role-row")).toHaveCount(7);
      await expect(gate.locator(".monitoring-gate-case")).toHaveCount(12);
      await expect(gate.locator(".monitoring-gate-case:enabled")).toHaveCount(12);
      await expect(gate.locator(".monitoring-gate-coverage-grid article")).toHaveCount(3);
      await expect(gate.getByText("Hipótesis completas")).toBeVisible();
      await expect(gate.getByText("Evidencia dentro del cutoff")).toBeVisible();
      await expect(gate.getByText("Trigger → decisión → resultado")).toBeVisible();
      await gate.getByText("Alcance del resultado").click();
      await expect(gate.getByText("3 condiciones bloqueantes.")).toBeVisible();

      const firstCase = gate.locator(".monitoring-gate-case").first();
      await expect(firstCase).toContainText("7/7 roles");
      await expect(firstCase).toContainText("requiere auditoría");
      await firstCase.click();

      const context = page.getByRole("region", {
        name: "Contexto de revisión desde Monitorización",
      });
      await expect(context).toBeVisible();
      await expect(context).toContainText(MONITORING_GATE_SCENARIO.childRunScenario!.run.run_id);
      await expect(page.getByRole("heading", { name: "Una historia de decisiones y memoria" })).toBeVisible();
      await page.waitForLoadState("networkidle");
    } finally {
      await verifyAndDisposeMonitoringHarness(harness);
    }
  });
});
