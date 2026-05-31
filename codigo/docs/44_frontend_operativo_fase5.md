# Frontend operativo de Fase 5

Fecha: 2026-05-29.

## Objetivo

Cerrar el Hito 7 de Fase 5 consolidando el frontend como herramienta operativa
local: desde la seleccion de dataset y preflight hasta la ejecucion, seguimiento
de job, consulta de runs, informe, artefactos, memoria y observabilidad
agentica.

## Inventario previo

Busquedas realizadas:

```text
rg -n "health|dataset|Planificar|Ejecutar|Run|Agentes|memory|report|artifact|comparison|job" codigo/frontend/src/App.tsx
rg -n "Hito 7|frontend operativo|Siguiente paso" codigo/docs memoria/capitulos/05_implementacion.tex
```

Piezas encontradas:

- `GET /health`, `GET /datasets/adapters` y `POST /datasets/describe` ya
  alimentan el selector y preflight de dataset.
- `POST /runs`, `GET /run-jobs/{job_id}` y el polling local ya ejecutan runs en
  segundo plano.
- `GET /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/report`,
  `GET /runs/{run_id}/artifacts` y `GET /runs/compare` ya cubren registro,
  detalle, informe, artefactos y comparacion.
- `GET /memory/collections`, `GET /memory/records` y
  `GET /memory/records/{memory_record_id}` ya cubren memoria persistida.
- La pestaña `Agentes` ya muestra eventos runtime de jobs vivos.

Decision: `extend`.

Motivo: el flujo operativo ya estaba compuesto por piezas existentes. El hito
no necesitaba nuevos endpoints, runners ni contratos, sino cerrar la integracion
visual y mantener el contexto de ejecucion siempre visible.

Impacto en compatibilidad: no cambia la API ni el backend. Se mantiene el
frontend como consumidor de contratos existentes.

## Implementacion

Se consolida la primera pantalla como dashboard operativo local, no como
landing page. El frontend queda organizado en dos vistas:

- `Pipeline`: seleccion de adaptador, ruta raw, preflight, Human Review,
  ejecucion en background, estado de job, runs locales, filtros, detalle,
  metricas, informe, artefactos y comparacion.
- `Agentes`: jerarquia supervisor-agentes, eventos runtime, memoria recuperada,
  colecciones persistidas, busqueda y detalle de recuerdos.

Ademas se anade una banda de contexto fija con:

- `dataset_id`;
- `run_id`;
- modo de ejecucion;
- politica de dataset;
- numero de fases efectivas o solicitadas;
- estado del plan;
- estado del job.

Esta banda satisface la decision de UX de mantener visibles dataset, politica,
`run_id` y modo durante todo el uso de la aplicacion, incluso al cambiar de
pestaña o revisar agentes.

## Criterios de aceptacion

- La UI permite lanzar una run CWRU completa mediante `POST /runs` con
  `background=true`.
- La UI muestra estado del job, snapshot, metricas, informe y artefactos.
- La UI permite consultar memoria local persistida por agente.
- El flujo principal no requiere ejecutar scripts manualmente.
- Las limitaciones metodologicas de datasets como NASA IMS se muestran mediante
  descriptor, politica, capacidades y bloqueos del plan.

## Verificacion

Comandos ejecutados:

```text
npm run build
python -m unittest codigo.tests.test_api_runs codigo.tests.test_api_memory codigo.tests.test_graph_pipeline codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
pdflatex -interaction=nonstopmode main.tex
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:5173/api/health
```

Resultado obtenido:

- `npm run build` compila correctamente;
- la suite backend relevante ejecuta 49 tests correctamente;
- `pdflatex` recompila `memoria/main.pdf` correctamente;
- el frontend local responde en `http://127.0.0.1:5173/`;
- el proxy local responde en `http://127.0.0.1:5173/api/health`.

## Limitaciones

- La subida multipart de datasets sigue fuera de este cierre porque el entorno
  no fija todavia `python-multipart`.
- La pestaña `Agentes` muestra eventos runtime de jobs vivos; la reconstruccion
  completa desde snapshots historicos queda para un incremento posterior.
- El empaquetado local reproducible de comandos backend/frontend corresponde al
  Hito 8.
