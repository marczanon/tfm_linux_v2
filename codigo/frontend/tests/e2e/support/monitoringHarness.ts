import { expect, type Page } from "@playwright/test";

import type { MonitoringReplayScenario } from "../fixtures/monitoringReplay";
import {
  installMonitoringMockApi,
  type MonitoringMockApiController,
} from "./mockApi";

export interface MonitoringPageHarness {
  api: MonitoringMockApiController;
  browserErrors: string[];
}

export async function openMonitoringReplay(
  page: Page,
  scenario: MonitoringReplayScenario,
): Promise<MonitoringPageHarness> {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      browserErrors.push(`console: ${message.text()}`);
    }
  });

  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  const api = await installMonitoringMockApi(page, scenario);
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Vistas principales" });
  await navigation.getByRole("button", { name: "Monitorización" }).click();
  await expect(
    navigation.getByRole("button", { name: "Monitorización" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    page.getByRole("heading", { name: "Centro de monitorización NASA" }),
  ).toBeVisible();
  await expect(page.getByText("REPLAY HISTÓRICO · no tiempo real")).toBeVisible();

  return { api, browserErrors };
}

export async function verifyAndDisposeMonitoringHarness(
  harness: MonitoringPageHarness,
): Promise<void> {
  expect.soft(
    harness.api.unhandledApiRequests,
    "La suite no debe dejar ninguna llamada /api sin contrato.",
  ).toEqual([]);
  expect.soft(
    harness.browserErrors,
    "La vista no debe producir errores de página o consola.",
  ).toEqual([]);
  await harness.api.dispose();
}
