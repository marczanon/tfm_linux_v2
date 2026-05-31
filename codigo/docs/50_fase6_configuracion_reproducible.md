# Configuracion reproducible Fase 6

Fecha: 2026-05-31.

## Objetivo

Completar el Hito 2 de Fase 6 preparando configuracion reproducible antes de
crear imagenes Docker: plantilla de entorno, documentacion operativa y proxy
frontend configurable.

## Inventario previo

Busquedas realizadas:

```text
rg -n ".env|env.example|ENV|OLLAMA_HOST|TFM_LLM|TFM_EMBEDDING|VITE_|docker|compose|CORS|allow_origins|5173|8010|11434" .gitignore AGENTS.md codigo/docs codigo/frontend codigo/app requirements.txt
rg --files -g ".env*" -g "*env*" -g "Dockerfile*" -g "*compose*" -g "README.md" . codigo/docker codigo/frontend codigo/docs | sort
```

Piezas encontradas:

- `.gitignore` ya ignora ficheros `.env` y `codigo/frontend/.env`.
- `codigo/frontend/.env.example` ya existia con `VITE_API_BASE_URL=/api`.
- `codigo/frontend/src/api.ts` ya permite configurar `VITE_API_BASE_URL`.
- `codigo/frontend/vite.config.ts` tenia el proxy `/api` fijado a
  `http://127.0.0.1:8010`.
- `codigo/docker/` no tenia README ni plantilla de entorno.

Decision: `extend`.

Motivo: ya existia una configuracion frontend minima. Se amplia sin cambiar
contratos ni crear un compose prematuro.

Impacto en compatibilidad: el modo local sigue funcionando igual porque el
proxy conserva `http://127.0.0.1:8010` como valor por defecto.

## Implementacion

Cambios realizados:

- `codigo/docker/.env.example`: plantilla sin secretos para el futuro compose,
  con puertos, variables LLM, embeddings y rutas de bind mounts.
- `codigo/docker/README.md`: documentacion operativa del directorio Docker,
  estado actual, decision sobre Ollama externo y volumenes previstos.
- `codigo/frontend/.env.example`: se anade `VITE_DEV_PROXY_TARGET`.
- `codigo/frontend/vite.config.ts`: el proxy de desarrollo usa
  `VITE_DEV_PROXY_TARGET` si existe y mantiene `http://127.0.0.1:8010` como
  fallback.

Variables principales:

```text
TFM_API_PORT=8010
TFM_FRONTEND_PORT=5173
VITE_API_BASE_URL=/api
VITE_DEV_PROXY_TARGET=http://backend:8010
TFM_LLM_PROVIDER=ollama
TFM_LLM_MODEL=qwen3.5:4b
OLLAMA_HOST=http://host.docker.internal:11434
TFM_EMBEDDING_PROVIDER=ollama
TFM_EMBEDDING_MODEL=qwen3-embedding:0.6b
```

Volumenes previstos:

```text
codigo/data/
codigo/reports/
codigo/models/
codigo/experiments/
```

## CORS y proxy

No se modifica CORS en este hito. La decision para la primera iteracion es
mantener el patron ya usado por Vite: el navegador llama a `/api` y el servidor
frontend redirige al backend. Para Docker, `VITE_DEV_PROXY_TARGET` permitira
apuntar al servicio `backend` sin cambiar codigo.

## Verificacion prevista

La verificacion tecnica de este hito es:

```text
npm run build
pdflatex -interaction=nonstopmode main.tex
```

No se ejecuta `docker compose` porque todavia no existe compose. El siguiente
hito creara la imagen backend minima.

## Siguiente paso

Hito 3: imagen backend.

Antes de implementarla, revisar:

```text
requirements.txt
codigo/app/api/app.py
codigo/app/api/routes.py
codigo/docker/.env.example
```
