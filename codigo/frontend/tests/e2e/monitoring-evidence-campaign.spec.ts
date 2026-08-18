import { expect, test } from "@playwright/test";

import { MONITORING_CAMPAIGN_SCENARIO } from "./fixtures/monitoringReplay";
import { expectNoHorizontalOverflow } from "./support/agentHarness";
import {
  openMonitoringReplay,
  verifyAndDisposeMonitoringHarness,
} from "./support/monitoringHarness";


test.describe("campaña de evidencia NASA", () => {
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
      await expect(page.getByRole("tab", { name: "Replay 2D" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await expect(page.locator(".monitoring-score-chart")).toHaveAttribute(
        "aria-label",
        /1 snapshots ejecutados/,
      );
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
