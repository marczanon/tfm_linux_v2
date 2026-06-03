# Fase 8 - Hito 8.5 recomendacion agentica en frontend

Fecha: 2026-06-03.

## Objetivo

Hacer visible en el panel principal `run_to_failure_degradation` la
interpretacion operacional del agente. El usuario no debe ver solo salud,
riesgo, score y ventanas: tambien debe ver que recomienda Qwen/LLM, con que
evidencia, que confianza declara, que cautelas mantiene y cual es el siguiente
paso propuesto.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Mostrar una recomendacion agentica operacional en la visualizacion
run-to-failure, derivada de decisiones persistidas de modeler/evaluator.
```

Inventario revisado:

- `codigo/app/schemas/api_visualization.py`;
- `codigo/app/services/run_visualization.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/frontend/src/types.ts`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/styles.css`;
- `codigo/tests/test_run_visualization.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/75_fase8_hito4_evaluador_operacional_debate_temporal.md`.

Decision:

```text
extend
```

Motivo: la visualizacion de runs ya tiene un endpoint canonico,
`GET /runs/{run_id}/visualization`, y ya carga snapshot, estado, artefactos y
metricas. Se extiende ese contrato con `agent_recommendation` en lugar de crear
un endpoint paralelo o una interpretacion generada en frontend.

## Contrato API

Se anade `AgentOperationalRecommendation` dentro de
`RunVisualizationData`. La recomendacion contiene:

- disponibilidad;
- agente fuente;
- `decision_id`;
- estado operacional (`approved`, `caution`, `needs_revision`, `blocked`,
  `unavailable`);
- titulo y resumen;
- confianza;
- siguiente accion;
- valoracion operacional;
- referencias de evidencia;
- herramientas usadas;
- limitaciones;
- puntos de debate temporal;
- comprobaciones de guardarrail;
- resumen de la estrategia del `modeler`.

El backend deriva estos campos leyendo los mensajes JSON persistidos en el
estado de la run. La prioridad es:

1. ultima decision del `evaluator`;
2. ultima decision del `modeler` como contexto de estrategia;
3. fallback trazable cuando no existe decision agentica persistida.

## Integracion frontend

La pestana `Visualizacion` incorpora un panel de `Recomendacion agentica` solo
para `run_to_failure_degradation`. El panel muestra:

- estado de recomendacion;
- confianza;
- accion siguiente;
- numero de herramientas y evidencias;
- estrategia resumida del modelador;
- evidencia citada;
- herramientas consultadas;
- guardarrails;
- cautelas;
- puntos de debate.

El componente no inventa diagnosticos. Solo renderiza la decision persistida por
los agentes. Si hay limitaciones metodologicas, una aprobacion se representa
como `caution`, porque en este perfil una run puede ser defendible para
investigacion pero no equivaler a RUL estimado ni a ground truth industrial por
ventana.

## Papel agentico

Este hito refuerza el principio rector de la fase: los LLM Qwen siguen siendo
protagonistas de la investigacion. Las herramientas deterministas preparan
evidencia y el frontend la muestra, pero la recomendacion visible procede de
decisiones estructuradas de agentes. La interfaz hace auditables sus razones y
mantiene juntas tres capas:

- estado operacional calculado desde predicciones;
- evidencia y metricas temporales;
- interpretacion agentica con debate y cautelas.

## Verificacion

Tests ejecutados durante el hito:

```bash
python -m unittest codigo.tests.test_run_visualization codigo.tests.test_api_runs
npm run build
git diff --check
```

Resultados: OK.

El test de visualizacion crea una run temporal sintetica con mensajes
persistidos de `modeler` y `evaluator` y comprueba que
`agent_recommendation` contiene estado, confianza, herramientas, evidencias,
limitaciones, guardarrails y resumen de estrategia.

## Siguiente paso logico

El siguiente hito es `8.6`: post-mortem y memoria especifica del perfil
temporal. Con la recomendacion ya visible, el sistema puede empezar a guardar
episodios de aprendizaje sobre aciertos, cautelas y decisiones agenticas
run-to-failure para reutilizarlos en futuras runs.
