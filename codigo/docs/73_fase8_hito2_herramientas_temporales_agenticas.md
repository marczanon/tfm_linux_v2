# Fase 8 - Hito 8.2 herramientas temporales agenticas

Fecha: 2026-06-03.

## Objetivo

Convertir el evidence pack temporal del Hito 8.1 en herramientas explicitas que
los agentes Qwen/LLM puedan elegir durante una run `run_to_failure_degradation`.
El objetivo es aumentar el protagonismo agentico sin permitir ejecucion de
codigo arbitrario ni decisiones automaticas fuera de contrato.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Permitir que los agentes consulten salud temporal y metricas de degradacion con
herramientas read-only especificas, citables y trazables.
```

Inventario revisado:

- `codigo/app/services/agent_tools.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/run_visualization.py`;
- `codigo/tests/test_agent_tools.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- `codigo/docs/72_fase8_hito1_evidence_pack_temporal_agentes.md`.

Decision:

```text
extend
```

Motivo: `agent_tools.py` ya centraliza el catalogo de herramientas seguras y
`build_state_evidence_catalog` ya contiene el paquete temporal. El hito extiende
ese catalogo con herramientas enfocadas en lugar de crear servicios paralelos o
runners nuevos.

## Herramientas implementadas

### `temporal_health_lookup`

Herramienta read-only disponible para los agentes actuales. Devuelve:

- disponibilidad de serie temporal;
- estado actual de salud/riesgo;
- primer pico;
- primer aviso sostenido;
- episodios de alerta;
- puntos aislados;
- racha maxima;
- referencia de fallo historico;
- advertencias metodologicas.

Guardarrail: observa salud temporal, pero no estima RUL, no aprueba runs y no
convierte un pico aislado en fallo real.

### `degradation_metrics_lookup`

Herramienta read-only disponible para los agentes actuales. Devuelve:

- metricas primarias run-to-failure;
- alias citables de metricas;
- contexto de etiquetas;
- advertencias sobre etiquetas proxy;
- recordatorio de que F1/recall/precision son auxiliares en este perfil.

Guardarrail: observa metricas temporales, pero no elige modelo, no aprueba la
run y no presenta etiquetas proxy como oficiales.

## Gestion de elecciones agenticas

El catalogo de herramientas queda asi:

- `evidence_lookup`: evidencia general y seccion temporal agregada;
- `temporal_health_lookup`: salud temporal enfocada;
- `degradation_metrics_lookup`: metricas run-to-failure enfocadas;
- `threshold_analysis`: diagnostico de sensibilidad de umbral, limitado a
  `modeler` y `evaluator`.

Estas herramientas no sustituyen las decisiones de agentes:

- `cleaner` sigue decidiendo `CleaningDecision`;
- `structurer` sigue decidiendo ventanas, solape y features;
- `modeler` sigue decidiendo modelo e hiperparametros;
- `evaluator` sigue decidiendo aprobacion y limitaciones;
- los ejecutores siguen aplicando acciones deterministas.

Las nuevas herramientas dan al agente mas evidencia para decidir dentro de esos
contratos.

## Evidencias citables

Las observaciones pueden citar, entre otras:

- `tool:temporal_health_lookup`;
- `tool:degradation_metrics_lookup`;
- `temporal:first_spike`;
- `temporal:first_persistent_alert`;
- `temporal:isolated_alert_points`;
- `temporal:longest_alert_streak`;
- `temporal:current_health_state`;
- `metric:mean_lead_time_to_failure`;
- `metric:mean_false_alarm_rate_nominal`;
- `metric:mean_score_trend_spearman`;
- `label_source:temporal_proxy`.

## Verificacion

Tests ejecutados durante el hito:

```bash
python -m unittest codigo.tests.test_agent_tools
```

Resultado inicial: OK, 18 tests.

La verificacion final del bloque debe incluir tambien agentes relacionados y
`git diff --check`.

## Continuacion

El Hito 8.3 queda implementado en
`74_fase8_hito3_modeler_estratega_run_to_failure.md`. A partir de las
herramientas temporales, el `modeler` ya declara estrategia, herramientas,
objetivos y politica temporal citando evidencia.
