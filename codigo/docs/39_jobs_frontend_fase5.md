# Jobs desde frontend Fase 5

Fecha: 2026-05-29.

## Objetivo

Permitir que la aplicacion lance una run real en segundo plano y siga su estado
sin bloquear la interfaz.

## Inventario previo

Busquedas realizadas:

```text
rg -n "run-jobs|background|ApiRunJob|submit\\(|dry_run|GET /run-jobs|poll" codigo/app codigo/tests codigo/frontend/src codigo/docs
```

Piezas encontradas:

- `POST /runs`: entrada canonica para dry-run y ejecucion.
- `ApiRunRequest`: ya contiene `dry_run` y `background`.
- `ApiRunJobStore`: propietario canonico del estado local de jobs en memoria.
- `GET /run-jobs/{job_id}`: consulta canonica de estado de job.
- `GET /runs/{run_id}`: consulta canonica de snapshot persistido.

Decision: `reuse`.

Motivo: no se necesitaba ampliar backend ni crear otro sistema de jobs. La
interfaz solo debia consumir las rutas existentes.

Impacto en compatibilidad: no cambian contratos Python ni rutas FastAPI.

## Implementacion frontend

Se ha ampliado el cliente HTTP en `codigo/frontend/src/api.ts` con:

```text
createBackgroundRun(...)
getRunJob(...)
getRun(...)
```

La pantalla de Fase 5 ahora:

- mantiene `Planificar` como dry-run visual con `dry_run=true`;
- habilita `Ejecutar` solo cuando el plan actual es ejecutable;
- envia `POST /runs` con `dry_run=false` y `background=true`;
- muestra un panel de job con `queued`, `running`, `completed` o `failed`;
- hace polling de `GET /run-jobs/{job_id}`;
- cuando el job termina, abre el snapshot via `GET /runs/{run_id}` y refresca la
  lista de runs.

Los errores de job `failed` se muestran con el detalle tecnico devuelto por el
backend.

## Verificacion

Comandos ejecutados:

```text
npm run build
python -m unittest codigo.tests.test_api_runs codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
curl -sS -X POST http://127.0.0.1:8010/runs ...
curl -sS http://127.0.0.1:8010/run-jobs/hito3-cwru-bg-20260529-01
curl -sS http://127.0.0.1:8010/runs/hito3-cwru-bg-20260529-01
```

Resultado:

- build TypeScript/Vite correcto;
- 42 tests backend correctos;
- la UI compila con los tipos de `ApiRunJobStatus` y `RunSnapshot`;
- no se ha introducido un mecanismo paralelo de jobs.
- la run CWRU `hito3-cwru-bg-20260529-01` completo en background con estado
  `completed`, `approved=true`, 13 artefactos y snapshot persistido en
  `codigo/reports/runs/hito3-cwru-bg-20260529-01`.

## Siguiente paso

Avanzar al Hito 4: abrir vistas de detalle de run, metricas, informes y
artefactos usando `run_registry.py` y los endpoints de lectura ya existentes.
