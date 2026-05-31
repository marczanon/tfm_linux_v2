# Imagen backend Fase 6

Fecha: 2026-05-31.

## Objetivo

Preparar la primera imagen Docker del backend FastAPI sin duplicar logica de
ejecucion ni copiar datos, modelos o artefactos dentro de la imagen.

## Inventario previo

Busquedas realizadas:

```text
rg -n "uvicorn|FastAPI|create_app|requirements|numpy|scipy|sklearn|matplotlib|joblib|data/raw|reports|reasoning_memory|OLLAMA_HOST|TFM_LLM|TFM_EMBEDDING|allowed_raw_roots|runs_dir|memory_dir" requirements.txt codigo/app codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md codigo/docs/49_fase6_supuestos_entorno.md codigo/docs/50_fase6_configuracion_reproducible.md codigo/docker
rg --files -g "Dockerfile*" -g ".dockerignore" -g "*dockerignore" -g "*compose*" -g "*.yml" -g "*.yaml" . codigo/docker | sort
```

Piezas encontradas:

- `requirements.txt` contiene dependencias Python del backend.
- `codigo.app.api:app` es la aplicacion FastAPI canonica.
- `codigo/app/api/app.py` crea directorios de uploads y configura `runs_dir`,
  `allowed_raw_roots`, `dataset_uploads_dir` y `memory_dir`.
- `codigo/app/api/routes.py` expone `GET /health`, datasets, runs, jobs,
  memoria, LLM y visualizacion.
- `codigo/docker/.env.example` ya fija variables LLM/embeddings y puertos.
- No existia Dockerfile backend previo ni `.dockerignore`.

Decision: `new`.

Motivo: no existia una definicion Docker previa para el backend. La nueva pieza
solo empaqueta la API existente y no introduce otro runner ni otra entrada de
ejecucion.

Impacto en compatibilidad: no cambia contratos API, servicios Python,
snapshots, memoria ni rutas FastAPI.

## Implementacion

Archivos creados:

- `.dockerignore`;
- `codigo/docker/backend.Dockerfile`.

La imagen:

- usa `python:3.11-slim`;
- instala `requirements.txt`;
- copia `codigo/__init__.py` y `codigo/app`;
- crea directorios vacios para `codigo/data/raw/uploads`,
  `codigo/reports/runs`, `codigo/reports/reasoning_memory`, `codigo/models` y
  `codigo/experiments`;
- expone `8010`;
- arranca:

```text
python -m uvicorn codigo.app.api:app --host 0.0.0.0 --port 8010
```

El `.dockerignore` excluye caches, entornos locales, `node_modules`, `dist`,
datasets, reports, modelos, experimentos, memoria LaTeX y recursos academicos
del contexto de build.

## Comandos previstos

Build:

```text
docker build -f codigo/docker/backend.Dockerfile -t tfm-backend:fase6-hito3 .
```

Run manual:

```text
docker run --rm \
  --name tfm-backend-fase6 \
  --add-host=host.docker.internal:host-gateway \
  --env-file codigo/docker/.env.example \
  -p 8010:8010 \
  -v "$PWD/codigo/data:/workspace/codigo/data" \
  -v "$PWD/codigo/reports:/workspace/codigo/reports" \
  -v "$PWD/codigo/models:/workspace/codigo/models" \
  -v "$PWD/codigo/experiments:/workspace/codigo/experiments" \
  tfm-backend:fase6-hito3
```

Smoke esperado:

```text
curl -sS http://127.0.0.1:8010/health
curl -sS http://127.0.0.1:8010/datasets/adapters
curl -sS http://127.0.0.1:8010/llm/status
```

## Verificacion realizada

Verificacion local:

```text
python -m compileall -q codigo/app
```

Resultado: correcto.

Verificacion Docker:

```text
docker build -f codigo/docker/backend.Dockerfile -t tfm-backend:fase6-hito3 .
```

Resultado: imagen construida correctamente.

```text
tfm-backend:fase6-hito3
```

Como el puerto local `8010` ya estaba ocupado por la API de desarrollo, la
prueba manual del contenedor se publico en `8015:8010`:

```text
docker run --rm -d \
  --name tfm-backend-fase6-hito3-test \
  --add-host=host.docker.internal:host-gateway \
  --env-file codigo/docker/.env.example \
  -p 8015:8010 \
  -v /home/mzp2003/tfm_linux_v2/codigo/data:/workspace/codigo/data \
  -v /home/mzp2003/tfm_linux_v2/codigo/reports:/workspace/codigo/reports \
  -v /home/mzp2003/tfm_linux_v2/codigo/models:/workspace/codigo/models \
  -v /home/mzp2003/tfm_linux_v2/codigo/experiments:/workspace/codigo/experiments \
  tfm-backend:fase6-hito3
```

Smoke ejecutado:

```text
curl -sS http://127.0.0.1:8015/health
curl -sS http://127.0.0.1:8015/datasets/adapters
curl -sS http://127.0.0.1:8015/llm/status
```

Resultados:

- `GET /health` devuelve `{"status":"ok"}` y muestra los directorios montados;
- `GET /datasets/adapters` lista CWRU, NASA IMS y generic tabular;
- `GET /llm/status` responde desde el contenedor con
  `host="http://host.docker.internal:11434"`, `available=true` y
  `model_available=true` para `qwen3.5:4b`;
- el healthcheck Docker marca el contenedor como `healthy`;
- el contenedor de prueba se detiene tras la validacion.

## Siguiente paso

Avanzar al hito de imagen frontend o al compose local minimo.
