# Fase 8 - Hito 8.1 evidence pack temporal para agentes

Fecha: 2026-06-03.

## Objetivo

Preparar una primera base agentica para `run_to_failure_degradation` dando a
los agentes Qwen/LLM una evidencia temporal compacta, estructurada y citable.
Este hito no introduce todavia herramientas temporales independientes ni nuevos
agentes; extiende el catalogo existente para que el perfil temporal pueda ser
razonado por los agentes actuales desde el inicio de la run.

El punto metodologico clave es que `cleaner` tambien participa en esta base:
sus decisiones de canal, remuestreo, no finitos y normalizacion condicionan la
continuidad temporal y la estabilidad del score posterior. Por tanto, no se
trata como una fase previa invisible, sino como un agente con contexto temporal
propio.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Exponer a los agentes una lectura compacta del perfil run-to-failure: estado
actual, primer pico, aviso sostenido, episodios, picos aislados, metricas
temporales, contexto de etiquetas y papel del cleaner.
```

Inventario revisado:

- `codigo/app/services/agent_tools.py`;
- `codigo/app/services/run_visualization.py`;
- `codigo/app/agents/cleaner.py`;
- `codigo/tests/test_agent_tools.py`;
- `codigo/tests/test_cleaner_agent.py`;
- `codigo/tests/test_run_visualization.py`;
- `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`.

Decision:

```text
extend
```

Motivo: `agent_tools.py` ya es el propietario del catalogo de herramientas y de
`build_state_evidence_catalog`; `run_visualization.py` ya calcula la serie
temporal que alimenta el panel. Crear un servicio paralelo habria duplicado la
interpretacion de primer aviso, aviso sostenido, episodios y fallo historico.

## Implementacion

Cambios principales:

- `run_visualization.py` expone `build_temporal_series_from_predictions`, una
  entrada publica pequena que reutiliza la misma serie temporal del panel.
- `agent_tools.py` anade la seccion `temporal` a `evidence_lookup` y a las
  secciones por defecto.
- `build_state_evidence_catalog` construye `temporal_evidence` con:
  - contexto de perfil y etiquetas;
  - contexto especifico del `cleaner`;
  - metricas de degradacion y alias citables;
  - resumen por run de estado actual, primer pico, aviso sostenido, episodios,
    picos aislados, racha maxima y fallo historico;
  - advertencias sobre etiquetas proxy y RUL no estimado;
  - guia de uso por agente.
- Las metricas temporales de `metrics.extra` pasan a exponerse tambien como refs
  `metric:*`, manteniendo las refs historicas `metric_extra:*`.
- El prompt LLM de `cleaner` incorpora contexto temporal del perfil y reglas
  explicitas para razonar sobre continuidad temporal, canal y estabilidad del
  score posterior.

## Evidencias citables nuevas

Ejemplos de refs que puede citar un agente:

- `temporal:run_to_failure_profile`;
- `temporal:cleaner_signal_quality_context`;
- `temporal:first_spike`;
- `temporal:first_persistent_alert`;
- `temporal:isolated_alert_points`;
- `temporal:alert_episodes`;
- `temporal:longest_alert_streak`;
- `temporal:current_health_state`;
- `temporal:failure_reference`;
- `temporal:rul_not_estimated`;
- `metric:mean_lead_time_to_failure`;
- `metric:degradation_mean_lead_time_to_failure`;
- `metric_extra:degradation_mean_lead_time_to_failure`.

## Papel del cleaner

El `cleaner` no decide anomalias, fallos ni RUL. Su papel agentico en este
hito es preparar una senal fiable para que los agentes posteriores puedan
razonar sobre degradacion temporal:

- selecciona canal principal coherente con el perfil;
- respeta la frecuencia objetivo;
- elimina no finitos;
- evita transformaciones que rompan comparabilidad temporal si no estan
  justificadas;
- deja trazabilidad mediante `CleaningDecision`.

Esto mantiene el protagonismo de los LLM sin romper la frontera de seguridad:
el agente decide bajo contrato y el ejecutor aplica la limpieza de forma
determinista.

## Criterio de aceptacion

Cumplido en este hito:

- `evidence_lookup` acepta `include=["temporal"]`;
- `cleaner` esta autorizado a consultar esa evidencia;
- el payload temporal resume primer pico frente a aviso sostenido;
- las refs temporales son cerradas y citables;
- las metricas temporales proxy quedan diferenciadas de F1;
- el prompt del `cleaner` recibe contexto `run_to_failure_degradation`;
- la lectura temporal reutiliza la misma base que la visualizacion.

## Verificacion

Tests ejecutados:

```bash
python -m unittest codigo.tests.test_agent_tools codigo.tests.test_cleaner_agent codigo.tests.test_run_visualization
```

Resultado: OK, 23 tests.

## Continuacion

El Hito 8.2 queda implementado en
`73_fase8_hito2_herramientas_temporales_agenticas.md`. La evidencia temporal ya
puede consultarse mediante herramientas concretas, no solo como seccion agregada
dentro de `evidence_lookup`.
