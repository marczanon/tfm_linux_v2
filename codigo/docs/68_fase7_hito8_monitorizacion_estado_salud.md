# Fase 7 - Hito 8.2: monitorizacion de estado de salud run-to-failure

Fecha: 2026-06-03.

## Objetivo

Anadir una capa determinista de monitorizacion industrial sobre las series
run-to-failure. La aplicacion no debe mostrar solo `anomaly_score`; debe traducir
ese score a un estado operacional por ventana y por trayectoria para que el
analista vea si el activo esta nominal, en vigilancia, en alerta o en estado
critico.

## Capacidad buscada

```text
Derivar health_index, risk_index y health_state desde anomaly_score, umbral y
metadatos temporales, sin prometer RUL exacto cuando el dataset no lo permite.
```

## Inventario previo anti-duplicacion

Busquedas realizadas:

```text
rg -n "TemporalSeriesPoint|TemporalRunSeries|temporal_series|health|warning|critical" codigo/app codigo/frontend/src codigo/tests codigo/docs
```

Piezas encontradas:

- `codigo/app/schemas/api_visualization.py`: contrato canonico de visualizacion.
- `codigo/app/services/run_visualization.py`: derivador read-only de
  visualizaciones desde artefactos persistidos.
- `codigo/frontend/src/types.ts`: espejo TypeScript.
- `codigo/frontend/src/App.tsx`: panel temporal existente.
- `codigo/frontend/src/styles.css`: estilos de la visualizacion temporal.
- `codigo/tests/test_run_visualization.py`: tests enfocados del endpoint y
  servicio de visualizacion.

Decision:

```text
extend
```

Motivo: ya existia `temporal_series` como frontera de visualizacion temporal.
Crear otra vista o endpoint para estado de salud duplicaria la misma
responsabilidad.

## Cambios implementados

Backend:

- `TemporalSeriesPoint` incluye:
  - `score_ratio`;
  - `risk_index`;
  - `health_index`;
  - `health_state`;
  - `state_reason`.
- `TemporalRunSeries` incluye estado actual de la trayectoria:
  - `current_health_state`;
  - `current_health_index`;
  - `current_risk_index`;
  - `current_time_to_failure_seconds` cuando existe en replay historico;
  - conteo de puntos en alerta, warning y critico.
- `run_visualization.py` calcula esos campos de forma determinista:
  - si hay umbral, usa `anomaly_score / threshold`;
  - si no hay umbral, usa normalizacion min-max del score dentro de la
    trayectoria;
  - eleva el estado a `warning` si el score supera el umbral o hay prediccion de
    anomalia;
  - eleva a `critical` si la alerta esta activa con riesgo muy alto o la vida
    relativa esta cerca del fallo.

Frontend:

- La visualizacion temporal muestra estado actual, salud, riesgo y numero de
  alertas.
- Los puntos de la curva se colorean por `health_state`.
- El tooltip de cada punto muestra estado, salud, score y posicion temporal.
- La leyenda diferencia warning y critico.

## Fronteras mantenidas

- No se estima RUL real si el modelo no lo predice.
- `time_to_failure_seconds` se muestra solo cuando el replay historico lo trae.
- No se recalculan estados en frontend.
- No se cambia la evaluacion oficial ni el entrenamiento.
- No se introduce agente LLM en el bucle de ventanas.

## Verificacion

Pruebas ejecutadas:

```text
python -m unittest codigo.tests.test_run_visualization
npm run build
curl -sS 'http://127.0.0.1:8010/runs/fase7-paso7-nasa-common-long-v2/visualization?max_points=80'
```

Resultado:

- `4` tests de visualizacion OK;
- build frontend OK.
- la run real `fase7-paso7-nasa-common-long-v2` devuelve
  `current_health_state=critical`, `current_health_index=0`,
  `alert_points=56` y puntos temporales con `health_state`.

## Siguiente paso

Usar esta capa de estado para construir vistas de monitorizacion mas completas:

- small multiples por modelo/run;
- indicador de salud suavizado;
- bandas de estado en la curva temporal;
- costes o severidad de falsas alarmas;
- cola de activos en `warning` o `critical`.
