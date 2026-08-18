import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  AGENT_RUN_SCENARIOS,
  MODELER_RAG_FILTERED_NOT_USED_SCENARIO,
  MODELER_RAG_UNAVAILABLE_SCENARIO,
  MODELER_RAG_USED_SCENARIO,
  type AgentRunScenario,
} from "./fixtures/agentRuns";
import {
  buildAgentStoryModel,
  buildStoryMemorySummary,
} from "../../src/lib/agentStory";
import {
  expectNoHorizontalOverflow,
  openAgentStory,
  verifyAndDisposeAgentHarness,
} from "./support/agentHarness";

test.describe("Semantica visual de memoria RAG", () => {
  test("la proyeccion conserva expectativas y rechaza IDs causalmente imposibles", () => {
    for (const scenario of Object.values(AGENT_RUN_SCENARIOS)) {
      const story = buildAgentStoryModel(scenario.events, null, scenario.snapshot);
      expect(story.run.decisionCount).toBe(scenario.expected.decisionCount);
      expect(story.run.fallbackCount).toBe(scenario.expected.fallbackCount);
      expect(story.run.firstPassCount).toBe(scenario.expected.firstPassCount);
      expect(story.run.participatingAgentCount).toBe(
        scenario.expected.participatingAgentCount,
      );
      expect(story.run.memory.filteredCount).toBe(scenario.expected.filteredCount);
      expect(story.run.memory.ignoredCount).toBe(scenario.expected.ignoredCount);
      expect(story.run.memory.retrievedCount).toBe(scenario.expected.retrievedCount);
      expect(story.run.memory.usedCount).toBe(scenario.expected.usedCount);
      expect(
        scenario.events.filter(
          (event) => event.payload.retrieval_event === "retrieval_unavailable",
        ),
      ).toHaveLength(scenario.expected.unavailableEventCount);
    }

    const invalidCitationEvents = structuredClone(
      MODELER_RAG_USED_SCENARIO.events.filter((event) => event.kind === "memory_retrieval"),
    );
    const usage = invalidCitationEvents.find(
      (event) => event.payload.retrieval_event === "retrieval_used",
    );
    expect(usage).toBeDefined();
    usage!.memory_record_ids = ["mem-never-retrieved"];
    usage!.payload = {
      ...usage!.payload,
      cited_memory_record_ids: ["mem-never-retrieved"],
    };
    expect(buildStoryMemorySummary(invalidCitationEvents).state).toBe("inconsistent");

    const invalidFilterEvents = structuredClone(
      MODELER_RAG_FILTERED_NOT_USED_SCENARIO.events.filter(
        (event) => event.kind === "memory_retrieval",
      ),
    );
    const returned = invalidFilterEvents.find(
      (event) => event.payload.retrieval_event === "retrieval_returned",
    );
    expect(returned).toBeDefined();
    returned!.payload = {
      ...returned!.payload,
      quality_gate: {
        excluded: [{ memory_record_id: "mem-effective", reason_codes: ["invalid_fixture"] }],
      },
    };
    expect(buildStoryMemorySummary(invalidFilterEvents).state).toBe("inconsistent");
  });

  test("una recuperacion citada se presenta como memoria utilizada", async ({ page }) => {
    const harness = await openModelerScenario(page, MODELER_RAG_USED_SCENARIO);
    try {
      const inspector = page.getByRole("region", { name: "Modelador" });
      await expect(inspector).toContainText("1 recuperado(s) y 1 utilizado(s)");
      await expectMemoryFlow(inspector, { consulta: 1, recupera: 1, usa: 1, noUsa: 0 });
      await expect(runMemorySignal(page)).toContainText("1 rec. · 1 usada");
      await expect(inspector).toContainText("Pendiente de contraste");
      await expect(inspector).toContainText("Modelo entrenado.");

      await openMemoryWorkspace(page);
      await expect(page.locator(".memory-character-runtime")).toContainText("Memoria utilizada");
      await expectRuntimeMemoryFlow(page, { consulta: 1, recupera: 1, usa: 1, noUsa: 0 });

      const agentSelector = page.getByRole("group", {
        name: "Seleccion de agente para memoria",
      });
      await expect(agentSelector.getByRole("button")).toHaveCount(7);
      const citedRecord = page.getByRole("button", { name: /Citado en esta run/ });
      await expect(citedRecord).toHaveCount(1);
      await citedRecord.click();
      await expect(citedRecord).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("details.memory-technical-drawer")).not.toHaveAttribute("open", "");
      await expectCorpusIsConstant(page);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("el filtrado previo y el no uso del agente permanecen separados", async ({ page }) => {
    const harness = await openModelerScenario(
      page,
      MODELER_RAG_FILTERED_NOT_USED_SCENARIO,
    );
    try {
      const inspector = page.getByRole("region", { name: "Modelador" });
      await expect(inspector).toContainText("1 recuperado(s); el agente no los utilizo");
      await expect(inspector).toContainText("1 filtrada(s) antes del agente");
      await expectMemoryFlow(inspector, { consulta: 1, recupera: 1, usa: 0, noUsa: 1 });
      await expect(inspector.getByRole("button", { name: /mem-effective/ })).toHaveCount(1);
      await expect(inspector.getByRole("button", { name: /mem-filtered/ })).toHaveCount(0);
      await expect(runMemorySignal(page)).toContainText("1 rec. · 0 usada");

      await openMemoryWorkspace(page);
      await expect(page.locator(".memory-character-runtime")).toContainText(
        "Recuperada y no utilizada",
      );
      await expect(page.locator(".memory-character-runtime")).toContainText(
        "1 recuerdo(s) filtrado(s) antes del agente",
      );
      await expectRuntimeMemoryFlow(page, { consulta: 1, recupera: 1, usa: 0, noUsa: 1 });
      await expectCorpusIsConstant(page);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("un evento unavailable no se inventa como contexto de la decision", async ({ page }) => {
    const harness = await openModelerScenario(page, MODELER_RAG_UNAVAILABLE_SCENARIO);
    try {
      const inspector = page.getByRole("region", { name: "Modelador" });
      await expect(inspector).toContainText("No recibio contexto RAG en la traza seleccionada");
      await expect(inspector).not.toContainText("No se dispuso de contexto RAG");
      await expectMemoryFlow(inspector, { consulta: 0, recupera: 0, usa: 0, noUsa: 0 });
      await expect(runMemorySignal(page)).toContainText("0 rec. · 0 usada");

      await openMemoryWorkspace(page);
      await expect(page.locator(".memory-character-runtime")).toContainText(
        "Sin contexto disponible",
      );
      await expectRuntimeMemoryFlow(page, { consulta: 0, recupera: 0, usa: 0, noUsa: 0 });
      await expectCorpusIsConstant(page);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });
});

async function openModelerScenario(page: Page, scenario: AgentRunScenario) {
  const harness = await openAgentStory(page, scenario);
  const map = page.getByRole("group", { name: "Mapa resumido de agentes" });
  await map.getByRole("button", { name: /^Modelador:/ }).click();
  await expect(page.getByRole("region", { name: "Modelador" })).toBeVisible();
  return harness;
}

async function openMemoryWorkspace(page: Page): Promise<void> {
  const workspace = page.getByRole("group", { name: "Vista agentica" });
  await workspace.getByRole("button", { name: "Memoria" }).click();
  await expect(page.getByRole("heading", { name: "Seleccion de agentes" })).toBeVisible();
}

async function expectMemoryFlow(
  inspector: Locator,
  expected: { consulta: number; recupera: number; usa: number; noUsa: number },
): Promise<void> {
  const flow = inspector.locator('[aria-label="Flujo de memoria de la decision"]');
  await expectFlowStep(flow, "Consulta", expected.consulta);
  await expectFlowStep(flow, "Recupera", expected.recupera);
  await expectFlowStep(flow, "Usa", expected.usa);
  await expectFlowStep(flow, "No usa", expected.noUsa);
}

async function expectRuntimeMemoryFlow(
  page: Page,
  expected: { consulta: number; recupera: number; usa: number; noUsa: number },
): Promise<void> {
  const flow = page.getByRole("group", { name: "Flujo RAG del agente en esta run" });
  await expectFlowStep(flow, "consulta", expected.consulta);
  await expectFlowStep(flow, "recupera", expected.recupera);
  await expectFlowStep(flow, "usa", expected.usa);
  await expectFlowStep(flow, "no usa", expected.noUsa);
}

async function expectFlowStep(flow: Locator, label: string, value: number): Promise<void> {
  const steps = flow.locator(":scope > span");
  const labels = await steps.locator("small").allTextContents();
  const index = labels.findIndex(
    (candidate) => candidate.trim().toLocaleLowerCase() === label.toLocaleLowerCase(),
  );
  expect(index, `Paso de memoria visible: ${label}`).toBeGreaterThanOrEqual(0);
  await expect(steps.nth(index).locator("strong")).toHaveText(String(value));
}

function runMemorySignal(page: Page): Locator {
  return page.locator(".agent-research-signal").filter({ hasText: "Memoria RAG" });
}

async function expectCorpusIsConstant(page: Page): Promise<void> {
  const readiness = page.locator(".memory-readiness-panel");
  await expect(readiness).toContainText("BLOQUEADO ANTES DE QWEN");
  await expect(readiness.locator(".memory-readiness-flow")).toContainText("indexados3");
  await expect(readiness.locator(".memory-readiness-flow")).toContainText("oficiales utiles3");
}
