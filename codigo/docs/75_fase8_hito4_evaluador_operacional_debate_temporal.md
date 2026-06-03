# Fase 8 - Hito 8.4 evaluador operacional y debate temporal

Fecha: 2026-06-03.

## Objetivo

Convertir al agente `evaluator` en auditor operacional del perfil
`run_to_failure_degradation`. El evaluador no debe limitarse a aprobar o
rechazar metricas: debe juzgar si la deteccion temprana es defendible en un
contexto industrial y dejar debate temporal trazable.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Hacer que el evaluator audite run-to-failure con herramientas, evidencia,
assessment operacional, debate temporal y guardarrails metodologicos.
```

Inventario revisado:

- `codigo/app/agents/evaluator.py`;
- `codigo/app/schemas/agent_decisions.py`;
- `codigo/app/services/agent_tools.py`;
- `codigo/app/services/decision_memory.py`;
- `codigo/tests/test_evaluator_agent.py`;
- `codigo/tests/test_decision_memory.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/74_fase8_hito3_modeler_estratega_run_to_failure.md`.

Decision:

```text
extend
```

Motivo: `EvaluationDecision` ya es el contrato canonico del evaluador y ya
contiene aprobacion, limitaciones y memoria. Se extiende con campos opcionales
en lugar de crear un `TemporalDebateRecord` separado en esta base del hito.

## Cambios de contrato

`EvaluationDecision` incorpora:

- `tool_names`;
- `evidence_refs`;
- `operational_assessment`;
- `temporal_debate_points`;
- `temporal_guardrail_checks`.

Los campos son compatibles con ejecuciones binarias. Para
`run_to_failure_degradation`, el evaluador debe rellenarlos y pasan a estar
validados por el agente.

## Guardarrails obligatorios

En una decision temporal valida, `temporal_guardrail_checks` debe incluir:

- `isolated_spike_not_failure`;
- `sustained_alert_required`;
- `rul_not_estimated`;
- `proxy_labels_not_official`;
- `f1_auxiliary_only`.

Ademas:

- `tool_names` debe incluir `temporal_health_lookup` y
  `degradation_metrics_lookup`;
- `evidence_refs` debe citar ambas herramientas y evidencia temporal o metricas
  de degradacion;
- `operational_assessment` debe mencionar RUL no estimado, picos aislados y
  avisos sostenidos;
- `temporal_debate_points` debe debatir picos, persistencia, falsas alarmas y
  etiquetas proxy.

## Debate temporal

Este hito no crea todavia un contrato independiente `TemporalDebateRecord`.
La base del debate queda dentro de `EvaluationDecision`:

- el evaluador puede aprobar con cautelas;
- puede rechazar aunque haya metricas parciales si la defensa operacional no es
  suficiente;
- puede bloquear implicitamente errores metodologicos al caer al fallback
  validado;
- deja puntos de debate que el `report_writer` y `report_verifier` pueden
  convertir en informe o correcciones.

## Memoria de decisiones

`decision_memory.py` conserva ahora la auditoria operacional:

- incluye `operational_assessment` en el resumen del episodio;
- guarda herramientas y refs como evidencia usada;
- incluye guardarrails temporales como tradeoffs observados;
- anade lecciones reutilizables sobre guardarrails y defendibilidad
  operacional.

## Verificacion

Tests ejecutados durante el hito:

```bash
python -m unittest codigo.tests.test_evaluator_agent
python -m unittest codigo.tests.test_evaluator_agent codigo.tests.test_decision_memory
```

Resultados: OK.

## Siguiente paso logico

El siguiente hito es `8.5`: recomendacion agentica en frontend. Con modeler y
evaluator declarando herramientas, evidencia, estrategia y auditoria
operacional, el panel puede mostrar una recomendacion agentica trazable en lugar
de limitarse a metricas y estado visual.
