# Compose local Fase 6

Fecha: 2026-05-31.

## Objetivo

Completar el Hito 5 de Fase 6 creando un `docker-compose.yml` minimo para
levantar backend y frontend con un comando reproducible, sin empaquetar datos,
artefactos ni modelos dentro de las imagenes y manteniendo Ollama como
dependencia externa documentada.

## Inventario previo

Busquedas realizadas:

```text
rg -n "compose|docker compose|host.docker.internal|TFM_API_PORT|TFM_FRONTEND_PORT|BIND|volumen|volumes" codigo/docs codigo/docker AGENTS.md
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml config
```

Piezas encontradas:

- `codigo/docker/backend.Dockerfile` ya construye la API FastAPI.
- `codigo/docker/frontend.Dockerfile` ya construye y sirve el frontend.
- `codigo/docker/frontend.nginx.conf.template` ya proxyfica `/api`.
- `codigo/docker/.env.example` ya define puertos, variables LLM y bind mounts.
- No existia `docker-compose.yml`.

Decision: `new`.

Motivo: faltaba la pieza de orquestacion local. El compose no introduce otro
runner, otra API ni otra UI: solo coordina las imagenes ya validadas.

Impacto en compatibilidad: no cambia contratos FastAPI, contratos TypeScript,
persistencia de runs, memoria agentica ni rutas de artefactos. El modo local
sin Docker sigue funcionando igual.

## Implementacion

Archivo creado:

- `codigo/docker/docker-compose.yml`.

Servicios:

- `backend`: construye `tfm-backend:fase6` desde
  `codigo/docker/backend.Dockerfile`, expone el puerto interno `8010`, monta
  datos, reports, modelos y experimentos, y anade
  `host.docker.internal:host-gateway` para alcanzar Ollama local.
- `frontend`: construye `tfm-frontend:fase6` desde
  `codigo/docker/frontend.Dockerfile`, expone el puerto interno `5173`, espera
  a que el backend este healthy y usa `TFM_BACKEND_URL=http://backend:8010`.

Volumenes montados:

```text
codigo/data        -> /workspace/codigo/data
codigo/reports     -> /workspace/codigo/reports
codigo/models      -> /workspace/codigo/models
codigo/experiments -> /workspace/codigo/experiments
```

Ollama se mantiene fuera del compose:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

## Uso normal

Desde la raiz del repositorio:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build
```

En segundo plano:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build -d
```

Parada sin borrar datos ni artefactos:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml down
```

## Puertos alternativos

Si el modo local ya ocupa `8010` o `5173`, se pueden cambiar los puertos
publicados en el host sin modificar los puertos internos de los contenedores:

```text
TFM_API_PORT=8016 TFM_FRONTEND_PORT=5175 docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build -d
```

En ese caso:

```text
Backend en host:  http://127.0.0.1:8016
Frontend en host: http://127.0.0.1:5175
```

## Verificacion realizada

Primero se renderizo la configuracion efectiva:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml config
```

Resultado: correcto. Los bind mounts resuelven a:

```text
/home/mzp2003/tfm_linux_v2/codigo/data
/home/mzp2003/tfm_linux_v2/codigo/reports
/home/mzp2003/tfm_linux_v2/codigo/models
/home/mzp2003/tfm_linux_v2/codigo/experiments
```

Como `8010` estaba ocupado por la API local, el stack se valido con puertos
alternativos:

```text
TFM_API_PORT=8016 TFM_FRONTEND_PORT=5175 docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml -p tfm-fase6-hito5 up --build -d
```

Servicios resultantes:

```text
backend  -> 0.0.0.0:8016->8010/tcp, healthy
frontend -> 0.0.0.0:5175->5173/tcp, healthy
```

Smoke ejecutado:

```text
curl -sS http://127.0.0.1:8016/health
curl -sS http://127.0.0.1:8016/llm/status
curl -sS http://127.0.0.1:5175/healthz
curl -sS http://127.0.0.1:5175/
curl -sS http://127.0.0.1:5175/api/health
curl -sS http://127.0.0.1:5175/api/datasets/adapters
```

Resultados:

- backend y frontend quedan en estado `healthy`;
- `GET /health` responde desde el backend dockerizado;
- `GET /llm/status` alcanza Ollama externo mediante
  `host.docker.internal:11434` y confirma `qwen3.5:4b`;
- `GET /healthz` responde desde el frontend dockerizado;
- `/` sirve el HTML compilado del dashboard;
- `/api/health` y `/api/datasets/adapters` responden a traves del proxy Nginx.

## Siguiente paso

Hito 6: crear pruebas de humo reproducibles que automaticen estas comprobaciones
basicas de API, frontend/proxy y disponibilidad LLM.
