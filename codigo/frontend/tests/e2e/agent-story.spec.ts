import { expect, test, type Page } from "@playwright/test";

import {
  EXACT_SEVEN_AGENTS_SCENARIO,
  MONITORING_RECORD_CATALOG_SCENARIO,
  MODELER_RAG_USED_SCENARIO,
} from "./fixtures/agentRuns";
import {
  expectNoHorizontalOverflow,
  openAgentStory,
  verifyAndDisposeAgentHarness,
} from "./support/agentHarness";

const MODEL_HYPOTHESIS =
  "Isolation Forest separara desviaciones persistentes del comportamiento nominal.";

test.describe("Historia visual de los agentes", () => {
  test("resume siete roles y deja el detalle tecnico bajo demanda", async ({ page }, testInfo) => {
    const harness = await openAgentStory(page, EXACT_SEVEN_AGENTS_SCENARIO);
    try {
      const storyMap = page.getByRole("group", { name: "Mapa resumido de agentes" });
      const agentCards = storyMap.locator(".agent-story-card");
      await expect(agentCards).toHaveCount(7);
      for (let index = 0; index < 7; index += 1) {
        await expect(agentCards.nth(index)).toBeVisible();
      }

      await expect(signal(page, "Agentes")).toContainText("7/7");
      await expect(signal(page, "LLM primer intento")).toContainText("7/7");
      await expect(signal(page, "Excepciones")).toContainText("0 fallback · 0 error");
      await expect(signal(page, "Memoria RAG")).toContainText("0 rec. · 0 usada");
      await expect(signal(page, "Resultado")).toContainText("Aprobada");

      const modelerCard = storyMap.getByRole("button", { name: /^Modelador:/ });
      await modelerCard.click();
      await expect(modelerCard).toHaveAttribute("aria-pressed", "true");

      const inspector = page.getByRole("region", { name: "Modelador" });
      await expect(inspector).toContainText("Cree");
      await expect(inspector).toContainText(MODEL_HYPOTHESIS);
      await expect(inspector).toContainText("Pendiente de contraste");
      await expect(inspector).toContainText("Elige");
      await expect(inspector).toContainText("isolation_forest");
      await expect(inspector).toContainText("Recuerda");
      await expect(inspector).toContainText("No recibio contexto RAG");
      await expect(inspector).toContainText("Ocurre");
      await expect(inspector).toContainText("Modelo entrenado.");
      await expect(inspector).toContainText("Enlace exacto registrado");

      const contrast = inspector.locator("details.agent-story-contrast");
      await expect(contrast).not.toHaveAttribute("open", "");
      await contrast.locator("summary").click();
      await expect(contrast.getByText("Esperaria observar")).toBeVisible();
      await expect(contrast.getByText("Se refutaria si")).toBeVisible();

      await expect(page.locator(".agent-story-workspace .runtime-json")).toHaveCount(0);
      await expectNoHorizontalOverflow(page);
      if (testInfo.project.name === "desktop-chromium") {
        const viewport = page.viewportSize();
        const cardBottoms = await agentCards.evaluateAll((cards) =>
          cards.map((card) => card.getBoundingClientRect().bottom),
        );
        expect(Math.max(...cardBottoms)).toBeLessThanOrEqual(viewport?.height ?? 1_000);
      }

      const auditCta = page.getByRole("button", { name: "Auditar traza" });
      await auditCta.focus();
      await auditCta.press("Enter");
      await expect(page.getByRole("region", { name: "Auditoria exacta" })).toBeFocused();
      await expect(page.getByRole("heading", { name: "Cobertura y procedencia" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Eventos reales" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Conversacion" })).toBeVisible();

      const payload = page.locator("details.runtime-payload-details");
      await expect(payload).not.toHaveAttribute("open", "");
      await expect(payload.locator("pre")).not.toBeVisible();
      await payload.locator("summary").click();
      await expect(payload.locator("pre")).toContainText('"modeling_config"');

      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("el recorrido temporal no muestra decisiones futuras", async ({ page }) => {
    const harness = await openAgentStory(page, MODELER_RAG_USED_SCENARIO);
    try {
      const storyMap = page.getByRole("group", { name: "Mapa resumido de agentes" });
      await storyMap.getByRole("button", { name: /^Modelador:/ }).click();
      const inspector = page.getByRole("region", { name: "Modelador" });
      const slider = page.getByRole("slider", {
        name: "Seleccionar evento de la historia",
      });

      await expect(slider).toHaveAttribute("aria-valuetext", /Evento \d+ de \d+:/);
      await slider.press("Home");
      await expect(slider).toHaveValue("0");
      await expect(slider).toHaveAttribute("aria-valuetext", /Evento 1 de \d+: Run iniciada/);
      await expect(inspector).toContainText("Este rol aun no ha participado");
      await expect(inspector).toContainText("No recibio contexto RAG");
      await expect(inspector).not.toContainText(MODEL_HYPOTHESIS);
      await expect(inspector).not.toContainText("Modelo entrenado.");
      await expect(inspector).not.toContainText("1 recuperado(s) y 1 utilizado(s)");

      await slider.press("End");
      await expect(slider).toHaveAttribute("aria-valuetext", /Run completada/);
      await expect(inspector).toContainText(MODEL_HYPOTHESIS);
      await expect(inspector).toContainText("1 recuperado(s) y 1 utilizado(s)");
      await expect(inspector).toContainText("Modelo entrenado.");
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("proyecta el catálogo causal sin exponer identificadores largos", async ({ page }) => {
    const harness = await openAgentStory(page, MONITORING_RECORD_CATALOG_SCENARIO);
    try {
      const storyMap = page.getByRole("group", { name: "Mapa resumido de agentes" });
      await storyMap.getByRole("button", { name: /^Modelador:/ }).click();
      const inspector = page.getByRole("region", { name: "Modelador" });
      const advisory = inspector.getByRole("region", {
        name: "Propuesta consultiva de política",
      });
      await expect(advisory).toBeVisible();
      await expect(advisory).toContainText("Consultiva");
      await expect(advisory).toContainText("No aplicada");
      await expect(advisory).toContainText("Intensificar observación");
      await expect(advisory).toContainText("Cadencia actual");
      await expect(advisory).toContainText("Intensificación solicitada");
      await expect(advisory).toContainText("E02");
      await expect(advisory).toContainText("E05");
      await expect(advisory).toContainText("Fundamento declarado");
      await expect(advisory).toContainText(
        "Revisión humana no solicitada en esta contribución",
      );
      await expect(advisory).toContainText("Desacuerdo entre agentes");
      await expect(advisory.getByRole("button", {
        name: /aplicar|activar|aprobar|rechazar/i,
      })).toHaveCount(0);

      const slider = page.getByRole("slider", {
        name: "Seleccionar evento de la historia",
      });
      await slider.press("Home");
      await expect(inspector.getByRole("region", {
        name: "Propuesta consultiva de política",
      })).toHaveCount(0);
      await slider.press("End");
      await expect(advisory).toBeVisible();
      await storyMap.getByRole("button", { name: /^Modelador:/ }).click();
      await page.getByRole("button", { name: "Auditar traza" }).click();

      const evidence = page.getByRole("region", {
        name: "Evidencia causal: 2 de 5 registros usados",
      });
      await expect(evidence).toBeVisible();
      await expect(evidence).toContainText("2/5 registros usados");
      await expect(evidence.getByRole("listitem")).toHaveCount(5);
      await expect(evidence.locator(".agent-record-evidence-rail .selected")).toHaveCount(2);
      await expect(evidence.locator(".agent-record-evidence-card")).toHaveCount(2);
      await expect(evidence.getByRole("article", { name: "Registro seleccionado E02" })).toContainText(
        "17/02 21:52",
      );
      await expect(evidence.getByRole("article", { name: "Registro seleccionado E02" })).toContainText(
        "Ratio 1,15×",
      );
      await expect(evidence.getByRole("article", { name: "Registro seleccionado E05" })).toContainText(
        "Gap detectado",
      );
      await expect(evidence).not.toContainText("causal-record:");

      const policyProposal = page.getByRole("region", {
        name: "Síntesis consultiva de política",
      });
      await expect(policyProposal).toBeVisible();
      await expect(policyProposal).toContainText("Desacuerdo entre agentes");
      await expect(policyProposal).toContainText("7 roles");
      await expect(policyProposal).toContainText("5 acciones distintas");
      await expect(policyProposal).toContainText("Sírevisión humana");
      await expect(policyProposal).toContainText("No existe una acción común");
      await expect(policyProposal.getByRole("listitem")).toHaveCount(7);
      const modelerContribution = policyProposal.getByRole("listitem").filter({
        hasText: "Modelador",
      });
      await expect(modelerContribution).toContainText("Cadencia actual");
      await expect(modelerContribution).toContainText("Intensificación solicitada");
      await expect(modelerContribution).toContainText("E02 · E05");
      await expect(policyProposal.getByRole("button", {
        name: /aplicar|activar|aprobar|rechazar/i,
      })).toHaveCount(0);
      await expect(policyProposal).not.toContainText("causal-record:");

      const technicalPayload = page.locator("details.runtime-payload-details");
      await expect(technicalPayload).not.toHaveAttribute("open", "");
      await expect(technicalPayload.locator("pre")).not.toBeVisible();
      await technicalPayload.locator("summary").click();
      await expect(technicalPayload.locator("pre")).toContainText("causal-record:");
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("el modo 3D conserva una alternativa accesible y movimiento reducido", async ({
    page,
  }) => {
    await instrumentAnimationFrames(page);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const harness = await openAgentStory(page, EXACT_SEVEN_AGENTS_SCENARIO);
    try {
      const mode = page.getByRole("group", { name: "Modo de oficina agentica" });
      const animationFramesBefore = await animationFrameCount(page);
      await mode.getByRole("button", { name: "3D" }).click();

      const shell = page.locator(".agent-office-3d-shell");
      const fallback = page.locator(".industrial-webgl-fallback");
      await expect(shell.or(fallback)).toBeVisible();
      if (await shell.count()) {
        await expect(shell).toHaveAttribute("data-motion", "reduced");
        await expect(shell.locator("canvas")).toBeVisible();
        const focus = page.getByRole("group", { name: "Foco de agente 3D" });
        await expect(focus.getByRole("button")).toHaveCount(7);
        const modeler = focus.getByRole("button", { name: /Enfocar Modelador/ });
        await modeler.click();
        await expect(modeler).toHaveAttribute("aria-pressed", "true");
        await expect(page.getByRole("region", { name: "Modelador" })).toBeVisible();
      } else {
        await expect(fallback).toContainText("3D no disponible");
        await expect(page.getByRole("region", { name: "Supervisor" })).toBeVisible();
      }
      expect(await animationFrameCount(page)).toBe(animationFramesBefore);
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });

  test("el fallback 3D forzado conserva la historia utilizable", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
        configurable: true,
        value: () => null,
      });
    });
    const harness = await openAgentStory(page, EXACT_SEVEN_AGENTS_SCENARIO);
    try {
      const mode = page.getByRole("group", { name: "Modo de oficina agentica" });
      await mode.getByRole("button", { name: "3D" }).click();
      const fallback = page.locator(".industrial-webgl-fallback");
      await expect(fallback).toBeVisible();
      await expect(fallback).toContainText("3D no disponible");
      await expect(page.locator(".agent-office-3d-shell")).toHaveCount(0);
      await expect(page.getByRole("region", { name: "Supervisor" })).toBeVisible();
      await mode.getByRole("button", { name: "2D" }).click();
      await expect(
        page.getByRole("group", { name: "Mapa resumido de agentes" }),
      ).toBeVisible();
      await expectNoHorizontalOverflow(page);
    } finally {
      await verifyAndDisposeAgentHarness(harness);
    }
  });
});

function signal(page: Page, label: string) {
  return page.locator(".agent-research-signal").filter({ hasText: label });
}

async function instrumentAnimationFrames(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const state = window as typeof window & { __agentStoryRafCalls: number };
    const requestAnimationFrame = window.requestAnimationFrame.bind(window);
    state.__agentStoryRafCalls = 0;
    window.requestAnimationFrame = (callback: FrameRequestCallback) => {
      state.__agentStoryRafCalls += 1;
      return requestAnimationFrame(callback);
    };
  });
}

async function animationFrameCount(page: Page): Promise<number> {
  return page.evaluate(() =>
    (window as typeof window & { __agentStoryRafCalls?: number }).__agentStoryRafCalls ?? 0,
  );
}
