# Hoja de ruta Fase 6

Fecha de inicio propuesta: 2026-05-31.

Estado: cierre operativo alcanzado el 2026-05-31 en el Hito 5. El stack Docker
minimo backend/frontend queda reproducible mediante `docker compose`. Los hitos
6 y 7 se difieren hasta que la aplicacion reciba el siguiente bloque de mejoras
funcionales.

## Nombre de la fase

Fase 6: Dockerizacion, reproducibilidad local y preparacion de demo final.

## Punto de partida

La Fase 5 deja una aplicacion local avanzada:

- backend FastAPI con `POST /runs`, jobs locales, registro de runs, memoria,
  visualizacion y estado LLM;
- frontend React/Vite como dashboard operativo local;
- integracion real con Ollama/Qwen para `use_llm=true`;
- Human Review local;
- memoria agentica consultable desde UI;
- visualizacion de metricas y PCA sobre artefactos persistidos;
- documentacion tecnica y memoria academica actualizadas.

El empaquetado se traslada deliberadamente a esta fase para no mezclar
reestructuracion de producto con infraestructura.

## Objetivo de la Fase 6

Convertir la aplicacion local en un entorno reproducible y demostrable mediante
Docker y pruebas de humo, manteniendo intacta la metodologia del TFM:

- no duplicar runners, registros, memoria ni contratos;
- conservar FastAPI como entrada canonica de ejecucion;
- conservar el frontend como consumidor de API;
- mantener Ollama como dependencia local controlada o servicio externo
  documentado;
- separar codigo, datos, artefactos, modelos y memoria academica;
- generar evidencia reproducible para la demo final.

El objetivo no es desplegar una plataforma cloud ni crear un sistema
multiusuario productivo. El objetivo es poder levantar el sistema local de forma
repetible y defender la demo completa del TFM.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Empaquetar y verificar la aplicacion local backend/frontend sin cambiar la
arquitectura ni duplicar responsabilidades.
```

Inventario previo:

- `codigo/app/api/routes.py`: API FastAPI existente.
- `codigo/app/services/pipeline_runner.py`: runner canonico multi-dataset.
- `codigo/app/services/api_run_jobs.py`: jobs locales en memoria.
- `codigo/app/services/run_persistence.py` y `run_registry.py`: persistencia y
  consulta de runs.
- `codigo/frontend/package.json` y `vite.config.ts`: scripts y proxy frontend.
- `codigo/frontend/README.md`: comandos locales actuales.
- `codigo/docker/`: directorio reservado, actualmente sin definiciones.
- `codigo/docs/36_hoja_ruta_fase_5_aplicacion.md`: cierre de aplicacion local.
- `codigo/docs/35_protocolo_reutilizacion_anti_duplicacion.md`: metodologia
  obligatoria.

Decision:

```text
extend
```

Motivo: la aplicacion ya existe. La Fase 6 debe anadir la capa de entorno
reproducible alrededor de las piezas canonicas, no crear otra aplicacion ni otro
pipeline.

Impacto en compatibilidad: no debe cambiar contratos API, snapshots, memoria,
artefactos ni semantica de ejecucion.

## Metodologia obligatoria de Fase 6

La Fase 6 mantiene la misma metodologia usada en fases anteriores:

- antes de crear Dockerfiles, scripts o pruebas, buscar piezas existentes;
- documentar decision `reuse`, `adapt`, `extend` o `new`;
- crear piezas nuevas solo cuando no exista propietario claro;
- no mover logica de ejecucion al contenedor;
- no permitir que agentes escriban o ejecuten codigo arbitrario;
- no ocultar bloqueos metodologicos como si fueran errores tecnicos;
- actualizar documentacion tecnica y memoria academica en paralelo;
- verificar cada hito con pruebas pequenas y reproducibles.

## Arquitectura objetivo

```text
Navegador
  -> frontend local container o servidor Vite/build estatico
      -> backend FastAPI container
          -> codigo/app/*
          -> volumen data/raw
          -> volumen reports/runs
          -> volumen reports/reasoning_memory
          -> Ollama local externo o servicio documentado
```

Principios:

- los datasets no se copian dentro de imagenes Docker;
- los artefactos y snapshots viven en volumenes montados;
- Ollama no se empaqueta dentro de la imagen inicial salvo decision explicita;
- el modelo `qwen3.5:4b` se trata como prerequisito verificable;
- el frontend no lee ficheros internos directamente;
- las rutas internas se mantienen como detalle de backend, no como UX principal.

## Fuera de alcance de Fase 6

No se abordara salvo decision explicita:

- despliegue cloud;
- SLURM/HPC;
- autenticacion multiusuario real;
- cola persistida con Redis/Celery;
- observabilidad avanzada con Prometheus/Grafana;
- empaquetar datasets pesados dentro de imagenes;
- descargar automaticamente modelos grandes durante el build;
- fine-tuning o entrenamiento de nuevos modelos;
- cambiar la arquitectura de agentes o ejecutores.

## Hito 1: Cierre formal de Fase 5 y supuestos de entorno

Objetivo: declarar de forma limpia que Fase 5 queda cerrada y que Fase 6 asume
la aplicacion local como base.

Trabajo previsto:

- actualizar `AGENTS.md` para que la guia activa sea Fase 6;
- mantener Fase 5 como referencia historica;
- documentar puertos, servicios y dependencias esperadas;
- decidir explicitamente si Ollama queda externo al compose inicial.

Criterio de aceptacion:

- nuevas sesiones saben leer esta hoja de ruta antes de implementar;
- los limites de Fase 6 quedan claros;
- la memoria academica menciona la transicion.

Avance 2026-05-31:

- se documentan los supuestos de entorno en
  `codigo/docs/49_fase6_supuestos_entorno.md`;
- se confirma que `requirements.txt` es la fuente actual de dependencias Python
  y que no existe `pyproject.toml`;
- se confirma que `codigo/docker/` esta reservado pero sin definiciones;
- se decide que Ollama queda externo al primer compose;
- se fijan puertos canonicos `8010`, `5173` y `11434`;
- se identifican como volumenes persistentes `codigo/data/`,
  `codigo/reports/`, `codigo/models/` y `codigo/experiments/`;
- se mantiene el doble modo de trabajo: local para desarrollo rapido y Docker
  para validacion reproducible.

## Hito 2: Configuracion reproducible

Objetivo: separar configuracion local de codigo.

Trabajo previsto:

- crear o actualizar ejemplo de variables de entorno sin secretos;
- documentar `TFM_LLM_PROVIDER`, host de Ollama, modelo Qwen y rutas de
  volumenes;
- revisar CORS y origen local;
- documentar puertos `8010` y `5173` o los definitivos del compose;
- definir estrategia para datos y artefactos persistidos.

Criterio de aceptacion:

- una persona puede saber que variables necesita sin leer el codigo;
- no se versionan secretos;
- las rutas persistentes no dependen de estado accidental de la maquina.

Avance 2026-05-31:

- se completa el hito en `codigo/docs/50_fase6_configuracion_reproducible.md`;
- se crea `codigo/docker/.env.example` con puertos, variables LLM, embeddings y
  bind mounts previstos;
- se crea `codigo/docker/README.md` para explicar el estado de la carpeta,
  decision de Ollama externo y siguiente paso;
- se amplia `codigo/frontend/.env.example` con `VITE_DEV_PROXY_TARGET`;
- `codigo/frontend/vite.config.ts` permite cambiar el proxy de desarrollo sin
  alterar el valor por defecto local `http://127.0.0.1:8010`;
- no se crea todavia `docker-compose.yml`: queda para los hitos de imagenes y
  compose.

## Hito 3: Imagen backend

Objetivo: contenerizar FastAPI sin duplicar logica.

Trabajo previsto:

- crear `Dockerfile` backend o definicion equivalente en `codigo/docker/`;
- instalar dependencias Python necesarias;
- exponer `8010`;
- montar datos, reports y memoria como volumenes;
- ejecutar `python -m uvicorn codigo.app.api:app --host 0.0.0.0 --port 8010`;
- definir healthcheck contra `GET /health`.

Criterio de aceptacion:

- la API arranca en contenedor;
- `GET /health` responde;
- `GET /datasets/adapters` responde;
- `GET /llm/status` informa correctamente si Ollama esta o no disponible.

Avance 2026-05-31:

- se prepara el hito en `codigo/docs/51_fase6_imagen_backend.md`;
- se crea `.dockerignore` para excluir caches, frontend generado, datasets,
  reports, modelos, experimentos, memoria LaTeX y recursos academicos del
  contexto Docker;
- se crea `codigo/docker/backend.Dockerfile` con `python:3.11-slim`,
  instalacion de `requirements.txt`, copia de `codigo/app`, directorios base,
  `EXPOSE 8010`, healthcheck y arranque Uvicorn;
- se actualiza `codigo/docker/README.md` con comandos de build, run manual y
  smoke esperado;
- la verificacion local `python -m compileall -q codigo/app` pasa;
- la imagen `tfm-backend:fase6-hito3` construye correctamente;
- el contenedor se valida publicado en `8015:8010` para no interferir con la
  API local ya activa en `8010`;
- `GET /health`, `GET /datasets/adapters` y `GET /llm/status` responden desde
  el contenedor;
- `GET /llm/status` alcanza Ollama externo mediante
  `host.docker.internal:11434` y confirma `qwen3.5:4b`;
- el healthcheck Docker queda en estado `healthy`.

## Hito 4: Imagen frontend

Objetivo: servir la aplicacion web de forma reproducible.

Trabajo previsto:

- decidir entre Vite dev container o build estatico servido por un servidor
  ligero;
- reutilizar `codigo/frontend/package.json`;
- no duplicar contratos TypeScript;
- configurar proxy o URL backend via entorno;
- exponer el puerto frontend definido.

Criterio de aceptacion:

- el frontend arranca desde contenedor;
- la UI comunica con la API contenida o con backend local documentado;
- `npm run build` sigue pasando fuera y dentro del flujo previsto.

Avance 2026-05-31:

- se prepara el hito en `codigo/docs/52_fase6_imagen_frontend.md`;
- se crea `codigo/docker/frontend.Dockerfile` con build multi-stage:
  `node:22-alpine` para `npm ci` y `npm run build`, y `nginx:1.27-alpine`
  para servir el resultado estatico;
- se crea `codigo/docker/frontend.nginx.conf.template` para mantener `/api`
  como frontera del navegador y redirigirlo a `TFM_BACKEND_URL`;
- el contenedor expone `5173` y define healthcheck contra `/healthz`;
- `npm run build` pasa en local;
- la imagen `tfm-frontend:fase6-hito4` construye correctamente;
- el contenedor se valida publicado en `5174:5173` para no interferir con Vite;
- `/healthz`, `/`, `/api/health` y `/api/datasets/adapters` responden desde el
  contenedor;
- el healthcheck Docker queda en estado `healthy`.

## Hito 5: Compose local

Objetivo: levantar backend y frontend con un comando reproducible.

Trabajo previsto:

- crear `docker-compose.yml` o equivalente bajo `codigo/docker/`;
- montar volumenes para `codigo/data`, `codigo/reports` y, si procede,
  `codigo/models`;
- documentar como conectar con Ollama en host Linux;
- evitar incluir datasets grandes en imagen;
- dejar claro como limpiar contenedores sin borrar artefactos.

Criterio de aceptacion:

- `docker compose up` levanta el stack local;
- el navegador puede abrir el frontend;
- el frontend consume el backend;
- los snapshots quedan persistidos fuera del contenedor.

Avance 2026-05-31:

- se prepara el hito en `codigo/docs/53_fase6_compose_local.md`;
- se crea `codigo/docker/docker-compose.yml` con servicios `backend` y
  `frontend`;
- el backend se construye desde `backend.Dockerfile`, monta `codigo/data`,
  `codigo/reports`, `codigo/models` y `codigo/experiments`, y alcanza Ollama
  externo mediante `host.docker.internal:11434`;
- el frontend se construye desde `frontend.Dockerfile`, espera al backend
  healthy y usa `TFM_BACKEND_URL=http://backend:8010`;
- los puertos publicados se parametrizan mediante `TFM_API_PORT` y
  `TFM_FRONTEND_PORT`;
- `docker compose config` resuelve correctamente rutas, imagenes y volumenes;
- el stack se valida con puertos alternativos `8016` y `5175` para no
  interferir con la API local activa;
- backend y frontend quedan `healthy`;
- `GET /health`, `GET /llm/status`, `/healthz`, `/`, `/api/health` y
  `/api/datasets/adapters` responden correctamente desde el stack dockerizado.

## Hito 6: Pruebas de humo reproducibles

Objetivo: convertir las pruebas manuales de Fase 5 en comprobaciones repetibles.

Trabajo previsto:

- crear script de humo para API: `GET /health`, adaptadores, runs y LLM status;
- crear prueba de humo de frontend/proxy;
- ejecutar un dry-run CWRU por API;
- opcionalmente lanzar una run background pequena si el tiempo lo permite;
- registrar salida esperada y modo de fallo.

Criterio de aceptacion:

- existe un comando documentado de smoke test;
- falla de forma clara si API, frontend u Ollama no estan listos;
- no genera artefactos pesados salvo que se pida una demo completa.

Estado: diferido. La decision de cierre operativo es no automatizar todavia
estas pruebas porque la aplicacion volvera a evolucionar funcionalmente. Se
retomaran cuando la superficie final de la app este mas estabilizada.

## Hito 7: Demo final reproducible

Objetivo: preparar evidencia defendible del sistema completo.

Demo candidata:

1. Levantar stack local.
2. Verificar `GET /health`.
3. Abrir frontend.
4. Ver estado de Ollama/Qwen.
5. Planificar CWRU.
6. Ejecutar run background.
7. Seguir job.
8. Consultar snapshot, metricas, informe, agentes y memoria.
9. Abrir visualizacion.
10. Ejecutar preflight NASA IMS y mostrar politica/bloqueo metodologico.

Criterio de aceptacion:

- existe una secuencia documentada;
- se conservan capturas o evidencia textual;
- la memoria academica describe la demo y sus limitaciones;
- no se han duplicado runners, contratos ni persistencia.

Estado: diferido. La demo final debe prepararse sobre la version de aplicacion
que se quiera defender, no sobre el minimo Docker intermedio.

## Cierre operativo 2026-05-31

La Fase 6 se considera cerrada operativamente tras el Hito 5. El objetivo minimo
de reproducibilidad local queda cubierto:

- backend dockerizado;
- frontend dockerizado;
- compose local backend/frontend;
- volumenes persistentes;
- Ollama externo documentado;
- validacion manual de API, frontend, proxy y LLM.

El siguiente bloque de trabajo vuelve a la aplicacion: pulido funcional,
mejoras de frontend/backend, ampliacion de capacidades y revision de fronteras.
La forma de trabajo sera desarrollar en local, mantener documentacion y memoria
en paralelo y reconstruir/validar Docker cuando los cambios afecten al stack.

Documento de cierre: `codigo/docs/54_cierre_operativo_fase6.md`.

## Orden recomendado de ejecucion

1. Cerrar Fase 5 en documentacion y memoria.
2. Actualizar `AGENTS.md` con Fase 6 como guia activa.
3. Definir variables y supuestos de entorno.
4. Crear contenedor backend.
5. Crear contenedor frontend.
6. Crear compose local.
7. Diferir pruebas de humo hasta estabilizar el siguiente bloque funcional.
8. Diferir demo final hasta cerrar la version defendible de la app.
9. Actualizar memoria, resultados y conclusiones.

## Primer paso concreto siguiente

Antes de escribir Dockerfiles:

```text
rg -n "uvicorn|fastapi|requirements|pyproject|package.json|vite|ollama|8010|5173" codigo pyproject.toml requirements.txt
rg --files codigo/docker codigo/frontend codigo/app codigo/tests codigo/docs | sort
```

Despues:

- decidir si el primer compose usara Ollama externo;
- crear una configuracion minima de backend;
- verificar `GET /health` dentro del contenedor;
- documentar cada decision en esta hoja o en un documento tecnico asociado.
