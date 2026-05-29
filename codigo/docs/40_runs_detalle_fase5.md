# Detalle de runs Fase 5

Fecha: 2026-05-29.

## Objetivo

Convertir el registro local de runs en una vista operativa desde la aplicacion,
mostrando filtros, detalle, metricas, informe, artefactos y comparacion basica.

## Inventario previo

Busquedas realizadas:

```text
rg -n "runs/compare|runs/\\{run_id\\}|artifacts|report|RunSnapshot|RunIndexEntry|RunComparison|get_run_artifacts|read_run_report|compare_runs|metrics" codigo/app codigo/tests codigo/frontend/src codigo/docs
```

Piezas encontradas:

- `run_registry.py`: propietario canonico de `list_runs`, `get_run_artifacts`
  y `compare_runs`.
- `run_persistence.py`: contratos `RunIndexEntry` y `RunSnapshot`.
- `routes.py`: endpoints ya expuestos para lectura, artefactos, informe y
  comparacion.
- `codigo/frontend/src/api.ts`: cliente local ya usado por la UI.

Decision: `reuse`.

Motivo: el backend ya exponia todos los datos necesarios. La tarea era
construir vistas y llamadas frontend sin crear rutas ni servicios paralelos.

Impacto en compatibilidad: no cambian contratos Python ni endpoints FastAPI.

## Implementacion frontend

Se ha ampliado el cliente HTTP con:

```text
GET /runs con filtros opcionales
GET /runs/{run_id}
GET /runs/{run_id}/artifacts
GET /runs/{run_id}/report
GET /runs/compare?run_ids=...
```

La vista de runs ahora permite:

- filtrar por dataset, estado y aprobacion;
- seleccionar una run desde la tabla;
- cargar `RunSnapshot`;
- mostrar metricas principales desde `RunIndexEntry`;
- listar artefactos persistidos;
- previsualizar el informe Markdown;
- seleccionar dos o mas runs y pedir una comparacion basica.

La UI sigue tratando una run `completed` con `approved=false` como resultado
metodologico no aprobado, no como fallo de infraestructura.

## Verificacion

Comandos ejecutados:

```text
npm run build
python -m unittest codigo.tests.test_api_runs codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
curl -sS http://127.0.0.1:8010/runs
curl -sS http://127.0.0.1:8010/runs/hito3-cwru-bg-20260529-01/artifacts
curl -sS http://127.0.0.1:8010/runs/hito3-cwru-bg-20260529-01/report
curl -sS "http://127.0.0.1:8010/runs/compare?run_ids=hito3-cwru-bg-20260529-01&run_ids=cwru-runner-common-validation-fase4-001"
```

Resultado:

- `npm run build` compila correctamente el frontend.
- La suite `codigo.tests.test_api_runs`,
  `codigo.tests.test_dataset_adapters` y `codigo.tests.test_pipeline_runner`
  completa 42 tests correctamente.
- `GET /runs` lista runs persistidas sin recalcular experimentos.
- `GET /runs/hito3-cwru-bg-20260529-01/artifacts` devuelve 13 artefactos.
- `GET /runs/hito3-cwru-bg-20260529-01/report` devuelve el informe Markdown.
- `GET /runs/compare` compara
  `hito3-cwru-bg-20260529-01` y
  `cwru-runner-common-validation-fase4-001`; las metricas comunes tienen
  `spread=0.0` en esta comparacion.

## Siguiente paso

Avanzar al Hito 5: hacer visible la memoria local desde la aplicacion,
reutilizando `vector_memory.py`, `agent_memory.py` y
`reasoning_memory_index.py`.
