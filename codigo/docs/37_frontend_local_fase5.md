# Frontend local Fase 5

Fecha: 2026-05-29.

## Objetivo

Crear el primer esqueleto de interfaz local para operar la API FastAPI del
pipeline sin duplicar logica de planificacion, politicas de dataset,
persistencia ni memoria.

## Inventario previo

Busquedas realizadas:

```text
rg -n "FastAPI|APIRouter|health|runs|PipelineRunRequest|dry_run|frontend|vite|react|package.json" AGENTS.md codigo/docs/36_hoja_ruta_fase_5_aplicacion.md codigo/app codigo/tests codigo/docs
rg --files | sort
```

Piezas encontradas:

- API canonica en `codigo/app/api/routes.py`.
- Contrato comun `PipelineRunRequest` en `codigo/app/schemas/pipeline_run.py`.
- Contrato `ApiRunRequest` en `codigo/app/schemas/api_runs.py`.
- Registro de runs en `run_persistence.py` y `run_registry.py`.
- Planificador comun en `pipeline_runner.py`.
- No existia `package.json`, frontend ni configuracion Vite/React previa.

Decision: `new`.

Motivo: la responsabilidad de frontend no tenia propietario previo. La nueva
pieza solo renderiza estado, recoge parametros y llama a la API existente.

Impacto en compatibilidad: no cambia contratos Python ni rutas FastAPI.

## Implementacion

Se ha creado `codigo/frontend/` con:

- React + TypeScript + Vite;
- cliente HTTP tipado en `src/api.ts`;
- tipos espejo minimos de los contratos publicos de API en `src/types.ts`;
- pantalla operativa en `src/App.tsx`;
- estilos locales en `src/styles.css`;
- proxy Vite `/api/* -> http://127.0.0.1:8010/*`;
- documentacion de arranque en `codigo/frontend/README.md`.

La pantalla inicial consume:

```text
GET /health
GET /datasets/adapters
POST /datasets/describe
GET /runs
POST /runs con dry_run=true
```

La UI muestra estado de API, catalogo de adaptadores servido por backend,
resumen de runs persistidas, formulario de preflight, descriptor de dataset y el
`DatasetPipelinePlan` devuelto por backend.

Tras el avance de jobs, la misma pantalla permite lanzar ejecuciones reales en
segundo plano con `background=true`, seguir el estado en `GET /run-jobs/{job_id}`
y abrir el snapshot persistido al completar.

Tras el avance de detalle de runs, el panel de registro permite filtrar
ejecuciones, abrir snapshot, metricas, artefactos e informe Markdown, y comparar
dos o mas runs mediante el endpoint `GET /runs/compare`.

Tras el avance de observabilidad agentica, el frontend anade la pestaña
`Agentes`. Esta vista consume los eventos runtime incluidos en
`GET /run-jobs/{job_id}` y muestra jerarquia supervisor-agentes, timeline de
comunicacion, decision estructurada, `rationale`, confianza, memoria citada y
payload observable por evento.

Tras el avance de memoria persistida, la pestaña `Agentes` muestra tambien la
coleccion asociada al agente seleccionado, recuerdos reutilizables filtrados por
la API, busqueda textual y detalle completo de cada `memory_record_id`.

Tras el avance de Human Review, el formulario de ejecucion muestra razones de
revision devueltas por el backend, permite seleccionar puntos de revision,
recoger una aprobacion simple y bloquear la ejecucion en modo `required` hasta
que exista aprobacion explicita. En modo `passive`, las razones se muestran
como aviso no bloqueante.

## Verificacion

Comandos ejecutados:

```text
npm install
npm run build
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:5173/api/health
curl -sS -X POST http://127.0.0.1:5173/api/runs ...
```

Resultado:

- `npm install` completo sin vulnerabilidades;
- `npm run build` compila correctamente;
- Vite levanta en `http://127.0.0.1:5173/`;
- el proxy `/api/health` devuelve `{"status":"ok"}`;
- el `POST /runs` con `dry_run=true` devuelve un plan CWRU ejecutable.

Durante la prueba se detecto que una instancia antigua de FastAPI en el puerto
`8010` seguia viva y no aceptaba campos actuales como `background` y
`human_review`. Se reinicio el backend con el codigo vigente antes de validar el
frontend.

## Limitaciones

- Los defaults locales de ruta siguen existiendo solo como ayuda inicial por
  `dataset_id`; el catalogo visible sale de FastAPI.
- La pestaña `Agentes` muestra telemetria de jobs vivos en memoria; todavia no
  reconstruye eventos desde snapshots historicos persistidos.
- La vista de memoria es read-only y no reconstruye el indice desde la UI.

## Siguiente paso

Consolidar el frontend operativo completo y documentar los comandos locales de
arranque backend/frontend.
