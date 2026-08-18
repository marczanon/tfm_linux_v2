import { expect, type Page } from "@playwright/test";

import type { AgentRunScenario } from "../fixtures/agentRuns";
import {
  installAgentMockApi,
  type MockApiController,
} from "./mockApi";

export interface AgentPageHarness {
  api: MockApiController;
  browserErrors: string[];
}

export async function openAgentStory(
  page: Page,
  scenario: AgentRunScenario,
): Promise<AgentPageHarness> {
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      browserErrors.push(`console: ${message.text()}`);
    }
  });

  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  const api = await installAgentMockApi(page, scenario);
  await page.goto("/");

  const cockpitRun = page.locator(".cockpit-run-card");
  await expect(cockpitRun).toContainText(scenario.run.run_id);
  await cockpitRun.getByRole("button", { name: "Agentes" }).click();

  const navigation = page.getByRole("navigation", { name: "Vistas principales" });
  await expect(navigation.getByRole("button", { name: "Agentes" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.locator(".run-context-disclosure summary")).toContainText(
    scenario.run.run_id,
  );
  await expect(
    page.getByRole("heading", { name: "Una historia de decisiones y memoria" }),
  ).toBeVisible();

  return { api, browserErrors };
}

export async function verifyAndDisposeAgentHarness(
  harness: AgentPageHarness,
): Promise<void> {
  expect.soft(
    harness.api.unhandledApiRequests,
    "La suite no debe dejar ninguna llamada /api sin contrato.",
  ).toEqual([]);
  expect.soft(
    harness.browserErrors,
    "La vista no debe producir errores de pagina o consola.",
  ).toEqual([]);
  await harness.api.dispose();
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(() =>
        Math.max(
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
          document.body.scrollWidth - document.body.clientWidth,
        ),
      ),
    )
    .toBeLessThanOrEqual(1);
}
