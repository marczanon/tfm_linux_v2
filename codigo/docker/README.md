# Docker Fase 6

Este directorio contiene la preparacion de infraestructura local reproducible
para la Fase 6.

## Estado actual

Hito 5 completado: imagenes backend/frontend y compose local minimo definidos
y validados.

El compose local levanta backend y frontend con un comando, monta datos y
artefactos desde el host y mantiene Ollama como servicio externo.

- Docker no sustituye el desarrollo local rapido.
- La aplicacion existente no se reescribe para Docker.
- FastAPI sigue siendo la entrada canonica.
- El frontend sigue consumiendo API, no ficheros internos.
- Ollama queda externo al primer compose.
- Datos, reports, modelos y experimentos se montaran como volumenes.

## Archivos

```text
.env.example
backend.Dockerfile
docker-compose.yml
frontend.Dockerfile
frontend.nginx.conf.template
README.md
```

`.env.example` es una plantilla sin secretos para el futuro compose. Incluye
puertos, variables LLM, embeddings y rutas de bind mounts previstas.

`backend.Dockerfile` construye una imagen FastAPI minima a partir de
`python:3.11-slim`, instala `requirements.txt`, copia `codigo/app` y arranca
Uvicorn en el puerto `8010`.

`frontend.Dockerfile` construye el frontend con `npm run build` y sirve el
resultado estatico con Nginx en el puerto `5173`.

`frontend.nginx.conf.template` mantiene `/api` como frontera publica del
navegador y redirige esas peticiones a `TFM_BACKEND_URL`.

`docker-compose.yml` levanta los servicios `backend` y `frontend`, construye
las imagenes si hace falta, publica los puertos configurados y monta los
directorios persistentes desde el host.

## Puertos

```text
API FastAPI: 8010
Frontend: 5173
Ollama externo: 11434
```

## Ollama

En desarrollo local:

```text
OLLAMA_HOST=http://127.0.0.1:11434
```

Dentro del backend dockerizado:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

En Linux, el compose debera declarar `host.docker.internal` con
`host-gateway`.

## Volumenes previstos

```text
codigo/data/
codigo/reports/
codigo/models/
codigo/experiments/
```

Estos directorios no deben copiarse dentro de las imagenes. Deben montarse
desde el host para preservar datasets, snapshots, memoria y resultados.

## Build manual backend

Desde la raiz del repositorio:

```text
docker build -f codigo/docker/backend.Dockerfile -t tfm-backend:fase6-hito3 .
```

## Build manual frontend

Desde la raiz del repositorio:

```text
docker build -f codigo/docker/frontend.Dockerfile -t tfm-frontend:fase6-hito4 .
```

## Compose local

Desde la raiz del repositorio:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build
```

En segundo plano:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build -d
```

Para parar el stack sin borrar datos ni artefactos:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml down
```

Si `8010` o `5173` estan ocupados por el modo local de desarrollo, se pueden
sobrescribir solo los puertos publicados en el host:

```text
TFM_API_PORT=8016 TFM_FRONTEND_PORT=5175 docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build -d
```

El backend dentro del compose sigue escuchando en `8010` y el frontend dentro
del compose sigue escuchando en `5173`; esas variables solo cambian los puertos
del host.

## Run manual backend

Sin compose, montando los volumenes previstos:

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

## Run manual frontend

Contra un backend local activo en `8010`:

```text
docker run --rm \
  --name tfm-frontend-fase6 \
  --add-host=host.docker.internal:host-gateway \
  -e TFM_BACKEND_URL=http://host.docker.internal:8010 \
  -p 5173:5173 \
  tfm-frontend:fase6-hito4
```

Si el puerto `5173` ya esta ocupado por Vite, publicar en otro puerto del host:

```text
-p 5174:5173
```

## Verificacion esperada backend

```text
curl -sS http://127.0.0.1:8010/health
curl -sS http://127.0.0.1:8010/datasets/adapters
curl -sS http://127.0.0.1:8010/llm/status
```

`/llm/status` debe responder aunque Ollama no este disponible; en ese caso
debe informar `available=false` en lugar de romper la API.

## Verificacion esperada frontend

```text
curl -sS http://127.0.0.1:5173/healthz
curl -sS http://127.0.0.1:5173/
curl -sS http://127.0.0.1:5173/api/health
curl -sS http://127.0.0.1:5173/api/datasets/adapters
```

## Verificacion backend realizada

Como `8010` estaba ocupado por la API local, la prueba de contenedor se publico
en `8015:8010`.

Resultado:

```text
GET /health -> ok
GET /datasets/adapters -> 3 adaptadores
GET /llm/status -> available=true, model_available=true, qwen3.5:4b
Docker healthcheck -> healthy
```

## Verificacion frontend realizada

Como `5173` puede estar ocupado por Vite, la prueba de contenedor se publico en
`5174:5173`, apuntando a la API local activa en `8010`.

Resultado:

```text
GET /healthz -> ok
GET / -> HTML compilado del dashboard
GET /api/health -> ok a traves del proxy Nginx
GET /api/datasets/adapters -> 3 adaptadores
Docker healthcheck -> healthy
```

## Verificacion compose realizada

Como `8010` estaba ocupado por la API local, el compose se valido con puertos
alternativos `8016` y `5175`.

Resultado:

```text
GET /health en 8016 -> ok
GET /llm/status en 8016 -> available=true, model_available=true, qwen3.5:4b
GET /healthz en 5175 -> ok
GET /api/health en 5175 -> ok a traves del proxy Nginx
GET /api/datasets/adapters en 5175 -> 3 adaptadores
backend y frontend -> healthy
```

## Siguiente paso

Crear pruebas de humo reproducibles para API, frontend/proxy y preflight.
