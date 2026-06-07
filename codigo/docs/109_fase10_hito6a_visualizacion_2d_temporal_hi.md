# Fase 10 - Hito 10.6A - Visualizacion 2D temporal con Health Index

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Iniciar el Hito 10.6 reforzando la sala `Visualizacion` como lectura 2D
temporal: la curva de score sigue siendo la referencia principal, pero ahora se
acompaña de una lectura compacta de Health Index y episodios de alerta.

El alcance queda limitado a frontend. No se cambian backend, contratos API,
esquemas Pydantic, grafo, agentes ni ejecutores.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mejorar la lectura temporal 2D en Visualizacion usando TemporalRunSeries ya
expuesto por GET /runs/{run_id}/visualization.
```

Pieza canonica reutilizada:

- `codigo/frontend/src/components/visualization/VisualizationView.tsx`;
- `RunVisualizationData`;
- `TemporalRunSeries`;
- `TemporalSeriesPoint`;
- estilos existentes de `temporal-*`.

Decision:

```text
adapt
```

Motivo: la vista `Visualizacion` ya era el propietario correcto de score, PCA,
estado temporal y recomendacion agentica. El subhito mejora su lectura visual
sin crear una vista paralela ni pedir nuevos datos al backend.

## Cambios implementados

En `VisualizationView`:

- la curva principal de score conserva bandas, umbral, primer pico, aviso
  sostenido y fallo de referencia;
- se añade una grafica 2D secundaria de `Health Index` por ventana;
- se añade un rail de episodios de alerta con tramos `warning`/`critical`;
- se añaden marcadores compactos de primer pico, aviso sostenido y fallo;
- se calculan episodios solo desde `point.health_state`, sin inventar nuevas
  metricas.

En `styles.css`:

- se añaden estilos para la grafica de HI;
- se añade rail visual de episodios y marcadores;
- se mantiene la composicion responsive y compacta.

## Criterios metodologicos

La UI no inventa diagnosticos:

- el Health Index sale de `TemporalSeriesPoint.health_index`;
- los estados salen de `TemporalSeriesPoint.health_state`;
- los episodios se agrupan visualmente desde puntos `warning` o `critical`;
- los marcadores salen de `first_alert_x`, `first_persistent_alert_x` y
  `failure_x`;
- no se crea ningun endpoint ni contrato nuevo.

La comparacion visual de modelos queda para un subhito posterior, porque debe
encajar con `RunComparison` sin mezclar responsabilidades.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

## Siguiente paso

Hito 10.6B deberia centrarse en comparacion visual de modelos/runs dentro de
`Visualizacion`, reutilizando `RunComparison` o datos ya cargados por la vista
de historico, sin crear un backend paralelo de analitica visual.
