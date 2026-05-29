# Hoja de ruta Fase 5

Fecha de inicio propuesta: 2026-05-29.

## Nombre de la fase

Fase 5: Aplicacion local backend/frontend para operacion visual del pipeline.

Alias historico posible: `fase4_interfaz`. Para evitar ambiguedad, en la
documentacion nueva se usara `Fase 5`.

## Punto de partida

La Fase 4 deja una base preparada para construir una aplicacion usable:

- runner comun multi-dataset en `codigo/app/services/pipeline_runner.py`;
- contrato comun `PipelineRunRequest` para CLI, API y futura UI;
- API FastAPI con lectura de runs persistidas;
- `POST /runs` con `dry_run=true` por defecto;
- ejecucion controlada con guardarrailes de ruta, politica de dataset y
  duplicidad de `run_id`;
- jobs locales en memoria con `background=true` y `GET /run-jobs/{job_id}`;
- Human Review inicial con `off/passive/required`;
- memoria RAG local por agente y backend vectorial JSON;
- ejecuciones completas CWRU y NASA IMS con politica temporal versionada;
- documentacion metodologica de NASA IMS, memoria agentica y API controlada.

La Fase 5 debe convertir esa infraestructura en una aplicacion local funcional
que permita a una persona cargar o seleccionar un dataset, lanzar runs, seguir
su estado, revisar resultados, consultar artefactos y observar memoria local.

## Objetivo de la Fase 5

Construir una aplicacion local con backend y frontend que permita:

- seleccionar o registrar datasets locales;
- previsualizar descriptor, adaptador, politica y bloqueos antes de ejecutar;
- lanzar runs completas cuando la politica lo permita;
- seguir jobs en segundo plano;
- consultar runs, metricas, informes y artefactos;
- activar opciones controladas de memoria local;
- visualizar que memorias existen y como se reutilizan;
- mantener trazabilidad academica y tecnica de cada paso.

El objetivo no es crear una plataforma productiva multiusuario. El objetivo es
tener una aplicacion local defendible para demostrar el sistema completo del
TFM.

## Protocolo de reutilizacion aplicado

Inventario previo:

- `pipeline_runner.py`: propietario de planificacion y ejecucion multi-dataset.
- `api_runs.py`: contrato de `POST /runs`.
- `api_run_jobs.py`: estado local de jobs API.
- `run_persistence.py`: fuente de verdad para snapshots.
- `run_registry.py`: consulta, artefactos y comparaciones.
- `dataset_adapters.py`: deteccion y descriptor de dataset.
- `signal_adapters.py`: lectura de formatos de senal.
- `vector_memory.py`, `agent_memory.py`, `decision_memory.py`: memoria RAG local.
- `human_review.py`: puerta de revision humana.

Decision:

```text
extend
```

La Fase 5 no debe crear otro runner, otro registro de runs ni otra memoria. La
app debe consumir estas piezas existentes. Solo se crearan componentes nuevos
cuando no haya propietario canonico: por ejemplo, una capa frontend, endpoints
de catalogo/ingesta de datasets o vistas especificas de UI.

## Arquitectura objetivo de Fase 5

```text
Frontend local
  -> FastAPI
      -> dataset_adapters.py
      -> pipeline_runner.py
      -> api_run_jobs.py
      -> run_persistence.py / run_registry.py
      -> vector_memory.py / reasoning_memory_index.py
```

Backend:

- se mantiene FastAPI;
- se extiende con endpoints de app, no con logica duplicada;
- `POST /runs` sigue siendo la entrada canonica para ejecuciones;
- `GET /run-jobs/{job_id}` sigue siendo la entrada canonica para jobs locales;
- los snapshots persistidos siguen siendo la fuente de verdad final.

Frontend:

- aplicacion web local;
- primera opcion recomendada: React + TypeScript + Vite;
- debe mostrar una herramienta operativa, no una landing page;
- debe priorizar densidad, trazabilidad y claridad sobre estetica decorativa;
- debe consumir solo la API, no leer ficheros internos directamente.

## Fuera de alcance de Fase 5

No se abordara todavia:

- autenticacion real multiusuario;
- despliegue cloud;
- SLURM/HPC;
- cola persistida con Redis/Celery;
- cancelacion robusta de trabajos largos;
- edicion manual de memoria desde UI como fuente de verdad;
- aprobacion automatica por memoria;
- fine-tuning de modelos;
- evaluacion supervisada NASA IMS sin politica temporal declarada;
- soporte completo para archives NASA IMS anidados sin preparacion previa.

## Hito 1: Cierre operativo de Fase 4

Objetivo: declarar Fase 4 como base cerrada para construir la app.

Trabajo previsto:

- dejar documentado el cierre en `codigo/docs/32_hoja_ruta_fase_4.md`;
- actualizar `AGENTS.md` para que la guia activa sea Fase 5;
- mantener el protocolo anti-duplicacion como regla obligatoria;
- compilar memoria tras el cambio.

Criterio de aceptacion:

- existe hoja de ruta de Fase 5;
- Fase 4 queda como referencia historica activa, no como guia principal;
- la memoria menciona la transicion hacia aplicacion local.

## Hito 2: Backend de catalogo e ingesta controlada de datasets

Objetivo: que la aplicacion pueda recibir o seleccionar datasets sin rutas
arbitrarias inseguras.

Trabajo previsto:

- endpoint para listar adaptadores disponibles;
- endpoint para describir un dataset por ruta permitida;
- endpoint de preflight de dataset antes de run;
- directorio de staging controlado bajo `codigo/data/raw/uploads/`;
- ingesta inicial de dataset mediante ruta local permitida o subida simple;
- normalizar errores de formato, adaptador no soportado y politica bloqueante.

Reglas:

- no duplicar `dataset_adapters.py`;
- no crear manifiestos desde la ruta API directamente si ya lo hace el runner;
- no permitir rutas fuera de raices configuradas;
- NASA IMS grande o anidado puede requerir carpeta preextraida en esta fase.

Criterio de aceptacion:

- la UI puede ver datasets/adaptadores soportados;
- el backend devuelve descriptor y capacidades antes de ejecutar;
- un dataset fuera de raiz permitida se rechaza;
- CWRU y NASA IMS preextraido se distinguen de forma explicita.

Avance 2026-05-29:

- `GET /datasets/adapters` lista el catalogo canonico de
  `dataset_adapters.py`;
- `POST /datasets/describe` describe rutas `raw_path` bajo raices permitidas;
- `create_app(...)` configura staging local bajo `codigo/data/raw/uploads/` o
  bajo la primera raiz permitida de test;
- `plan_dataset_pipeline_run(...)` rechaza adaptadores explicitos que no
  soportan la ruta;
- el frontend consume el catalogo backend y solicita descriptor antes del
  dry-run de `POST /runs`;
- queda fuera de este avance la subida multipart porque `python-multipart` no
  esta fijado en el entorno.

## Hito 3: Ejecucion desde app con seguimiento de jobs

Objetivo: lanzar runs desde la aplicacion y seguir su estado.

Trabajo previsto:

- usar `POST /runs` con `dry_run=true` para preflight visual;
- usar `POST /runs` con `dry_run=false` y `background=true` para ejecutar;
- polling de `GET /run-jobs/{job_id}`;
- al completar, abrir automaticamente el snapshot via `GET /runs/{run_id}`;
- mostrar errores de job `failed` sin esconder detalle tecnico.

Criterio de aceptacion:

- se lanza una run CWRU completa desde API/UI;
- el usuario ve `queued/running/completed/failed`;
- el snapshot queda en `codigo/reports/runs/`;
- la UI no bloquea mientras corre la ejecucion.

Avance 2026-05-29:

- el frontend mantiene `Planificar` como dry-run visual;
- se anade `Ejecutar` para enviar `POST /runs` con `dry_run=false` y
  `background=true`;
- la UI consulta `GET /run-jobs/{job_id}` por polling;
- al completar, la UI obtiene el snapshot con `GET /runs/{run_id}` y refresca
  el registro local;
- los jobs `failed` muestran el detalle tecnico devuelto por backend;
- no se han creado rutas nuevas ni otro store de jobs.

Verificacion de humo:

- `hito3-cwru-bg-20260529-01` se lanzo con `background=true`;
- `GET /run-jobs/hito3-cwru-bg-20260529-01` devolvio `completed`;
- el snapshot quedo disponible en
  `codigo/reports/runs/hito3-cwru-bg-20260529-01`.

## Hito 4: Visualizacion de runs, metricas y artefactos

Objetivo: convertir el registro local en una vista operativa.

Trabajo previsto:

- lista de runs con filtros por dataset, estado y aprobacion;
- vista detalle de run;
- panel de metricas principales;
- enlace/vista de informe Markdown;
- lista de artefactos generados;
- comparacion basica entre runs seleccionadas.

Reutilizacion obligatoria:

- `run_registry.py`;
- `RunSnapshot`;
- `RunIndexEntry`;
- `RunComparison`.

Criterio de aceptacion:

- la UI muestra runs existentes sin recalcular;
- se puede abrir informe y artefactos;
- se puede comparar al menos dos runs;
- las metricas bajas se muestran como `completed` + `approved=false`, no como
  fallo de infraestructura.

Avance 2026-05-29:

- el frontend consume `GET /runs` con filtros por dataset, estado y aprobacion;
- la tabla permite seleccionar una run y cargar `GET /runs/{run_id}`;
- la vista detalle muestra metricas principales, snapshot, informe y artefactos;
- el informe se obtiene con `GET /runs/{run_id}/report`;
- los artefactos se obtienen con `GET /runs/{run_id}/artifacts`;
- la comparacion basica usa `GET /runs/compare` con dos o mas `run_ids`;
- no se han creado endpoints nuevos ni otro registro de runs.

Verificacion de humo:

- `GET /runs` lista runs existentes sin recalcular;
- `GET /runs/hito3-cwru-bg-20260529-01/artifacts` devuelve 13 artefactos;
- `GET /runs/hito3-cwru-bg-20260529-01/report` devuelve el informe Markdown;
- `GET /runs/compare` compara
  `hito3-cwru-bg-20260529-01` y
  `cwru-runner-common-validation-fase4-001` con `spread=0.0` en las metricas
  comunes.

## Hito 5: Memoria local visible desde la aplicacion

Objetivo: que la aplicacion muestre la memoria agentica local como evidencia
trazable.

Trabajo previsto:

- endpoint de resumen de colecciones de memoria;
- endpoint de consulta simple por agente/dataset;
- vista de registros recuperados;
- mostrar `memory_record_id`, agente, dataset, rol, veredicto humano y fuente;
- opcion controlada para reconstruir indice local si ya existe comando/servicio.

Reglas:

- la memoria no aprueba runs;
- la UI no edita memoria como fuente canonica en esta fase;
- cualquier reconstruccion debe reutilizar `reasoning_memory_index.py`.

Criterio de aceptacion:

- la UI muestra colecciones como `modeler_memory`, `structurer_memory` y
  `evaluator_memory`;
- una consulta devuelve recuerdos trazables;
- queda claro si un recuerdo es ejemplo positivo, advertencia o caso frontera.

Avance parcial 2026-05-29:

- se anade una capa de observabilidad agentica viva mediante
  `AgentRuntimeEvent` y `AgentRuntimeRecorder`;
- `ApiRunJobStatus` incluye `events` y se expone
  `GET /run-jobs/{job_id}/events`;
- el grafo emite eventos de supervisor, agentes, recuperacion de memoria,
  ejecutores, estado de job y errores;
- la UI incorpora la pestaña `Agentes` con jerarquia visual, timeline y detalle
  clicable de `rationale`, decision JSON, memoria citada y payload observable;
- no se expone cadena de pensamiento privada: solo decisiones estructuradas,
  justificacion declarada, memoria recuperada y resultados deterministas.

Pendiente tras el avance parcial de observabilidad:

- resumen de colecciones persistidas de memoria;
- consulta por agente/dataset contra memoria indexada;
- apertura de registros `memory_record_id` desde la UI.

Avance 2026-05-29:

- `GET /health` expone `memory_dir`;
- `GET /memory/collections` resume colecciones canonicas del store local;
- `GET /memory/records` lista recuerdos filtrables por agente, dataset, rol,
  reutilizacion y texto;
- `GET /memory/records/{memory_record_id}` abre un recuerdo completo bajo el
  contrato `ReasoningMemoryRecord`;
- la pestaña `Agentes` muestra memoria persistida del agente seleccionado junto
  a la telemetria runtime;
- la lectura reutiliza `LocalJsonVectorMemoryStore` y no crea otro indice ni
  otro backend de memoria.

Verificacion de humo:

- los endpoints de memoria pasan pruebas contra un store temporal;
- el frontend compila con el bloque de memoria persistida;
- queda fuera de esta entrega la reconstruccion del indice desde UI.

## Hito 6: Human Review operativa minima

Objetivo: permitir que la UI vea y envie aprobaciones simples cuando el backend
las requiere.

Trabajo previsto:

- mostrar razones de revision devueltas por `human_review_reasons`;
- formulario simple para `human_approval`;
- usar modo `passive` como observacion no bloqueante;
- usar modo `required` solo para acciones explicitamente marcadas.

Reglas:

- no crear otro contrato de aprobacion;
- reutilizar `HumanReviewSettings` y `HumanApproval`;
- no convertir Human Review en sistema multiusuario completo.

Criterio de aceptacion:

- una run en modo `passive` muestra aviso sin bloquear;
- una run en modo `required` no ejecuta hasta recibir aprobacion;
- la aprobacion queda persistida en snapshot.

Avance 2026-05-29:

- el frontend muestra controles de Human Review reutilizando `human_review` y
  `human_approval`;
- el dry-run conserva y muestra `human_review_reasons`;
- el modo `passive` se presenta como aviso no bloqueante;
- el modo `required` bloquea la accion de ejecutar en la UI hasta marcar una
  aprobacion explicita;
- la aprobacion viaja en `human_approval` hacia `POST /runs`;
- no se han creado contratos ni endpoints nuevos para aprobaciones.

Verificacion:

- los tests API existentes cubren `passive`, `required` bloqueante y
  persistencia de `human_approval` en snapshot;
- el frontend compila con los controles de revision humana;
- la memoria academica se recompila tras documentar el hito.

## Hito 7: Frontend operativo

Objetivo: construir la primera interfaz usable.

Vistas minimas:

- panel de salud de backend;
- selector/carga de dataset;
- preflight de run;
- lanzador de run;
- monitor de job;
- listado de runs;
- detalle de run;
- informe tecnico;
- artefactos;
- memoria local.

Decisiones de UX:

- primera pantalla: dashboard operativo, no landing;
- controles compactos y claros;
- mostrar bloqueos antes de ejecutar;
- mostrar siempre dataset, politica, run_id y modo de ejecucion;
- no ocultar limitaciones metodologicas de NASA IMS.

Criterio de aceptacion:

- un usuario puede lanzar una run CWRU completa desde la UI;
- puede ver estado, metricas e informe;
- puede consultar memoria local;
- no necesita ejecutar scripts manualmente para el flujo principal.

## Hito 8: Empaquetado local de desarrollo

Objetivo: facilitar que backend y frontend se levanten de forma reproducible.

Trabajo previsto:

- documentar comandos de arranque backend/frontend;
- definir puertos locales;
- configurar CORS solo para origen local;
- crear prueba de humo de API;
- crear prueba de humo frontend si el stack lo permite;
- evitar Docker Compose obligatorio en esta fase.

Criterio de aceptacion:

- backend levanta con un comando documentado;
- frontend levanta con un comando documentado;
- la UI puede comunicarse con la API local;
- la suite backend sigue pasando.

## Hito 9: Demo end-to-end de Fase 5

Objetivo: cerrar la fase con una ejecucion demostrable de aplicacion completa.

Demo candidata:

1. Abrir frontend local.
2. Seleccionar CWRU.
3. Ver preflight permitido.
4. Lanzar run en background.
5. Seguir job hasta completar.
6. Abrir snapshot.
7. Ver metricas, informe y artefactos.
8. Consultar memoria local.
9. Repetir preflight NASA IMS con politica temporal o bloqueo explicado.

Criterio de aceptacion:

- existe una run generada desde UI;
- existe evidencia documental de la demo;
- la memoria academica describe la aplicacion y sus limitaciones;
- no se han duplicado runners, contratos ni persistencia.

## Orden recomendado de ejecucion

1. Cerrar Fase 4 y activar Fase 5 en documentacion.
2. Crear esqueleto frontend y configuracion local.
3. Exponer endpoints de catalogo/adaptadores/dataset preflight.
4. Conectar preflight de run a la UI.
5. Conectar lanzamiento de run y polling de jobs.
6. Crear vistas de runs, detalle, informe y artefactos.
7. Crear vistas de memoria local.
8. Anadir Human Review minima en UI.
9. Ejecutar demo end-to-end.
10. Actualizar memoria y resultados.

## Primer paso concreto siguiente

El primer paso tecnico de Fase 5 era crear el esqueleto frontend local y una
pantalla operativa minima que consuma:

```text
GET /health
GET /runs
POST /runs con dry_run=true
```

Antes de implementar se aplicara de nuevo el protocolo anti-duplicacion:

- comprobar si ya existe configuracion frontend o scripts de arranque;
- decidir ubicacion (`codigo/frontend/` salvo que aparezca una convencion mejor);
- definir stack minimo;
- no duplicar logica de planificacion que ya vive en la API.

## Avance 2026-05-29: esqueleto frontend local

Estado: completado.

Se ha creado `codigo/frontend/` con React, TypeScript y Vite. La primera
pantalla operativa consume `GET /health`, `GET /datasets/adapters`,
`POST /datasets/describe`, `GET /runs` y `POST /runs` en modo `dry_run=true`,
mostrando el descriptor y el plan devuelto por la API sin ejecutar
transformaciones.

Documentacion tecnica asociada:

```text
codigo/docs/37_frontend_local_fase5.md
codigo/docs/38_catalogo_datasets_fase5.md
codigo/docs/39_jobs_frontend_fase5.md
codigo/docs/40_runs_detalle_fase5.md
codigo/docs/41_observabilidad_agentica_fase5.md
codigo/docs/42_memoria_persistida_frontend_fase5.md
codigo/docs/43_human_review_ui_fase5.md
codigo/frontend/README.md
```

Verificacion realizada:

```text
npm install
npm run build
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:5173/api/health
curl -sS http://127.0.0.1:5173/api/datasets/adapters
npm run build
curl -sS -X POST http://127.0.0.1:5173/api/runs ...
curl -sS http://127.0.0.1:5173/api/runs/hito3-cwru-bg-20260529-01/artifacts
```

El siguiente paso logico pasa a ser consolidar el Hito 7 como flujo frontend
operativo completo y preparar el empaquetado local de desarrollo del Hito 8.
