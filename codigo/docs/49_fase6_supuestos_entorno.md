# Supuestos de entorno Fase 6

Fecha: 2026-05-31.

## Objetivo

Cerrar el primer paso de Fase 6 antes de escribir Dockerfiles: fijar supuestos
de entorno, puertos, dependencias, volumenes persistentes y decision inicial
sobre Ollama.

## Inventario previo

Busquedas realizadas:

```text
rg -n "uvicorn|fastapi|requirements|pyproject|package.json|vite|ollama|OLLAMA|TFM_|8010|5173|11434|docker|compose" codigo pyproject.toml requirements.txt AGENTS.md
rg --files codigo/docker codigo/frontend codigo/app codigo/tests codigo/docs | sort
```

Piezas encontradas:

- `requirements.txt` es la fuente actual de dependencias Python. No existe
  `pyproject.toml`.
- `codigo/app/api/app.py` expone la aplicacion FastAPI canonica mediante
  `codigo.app.api:app`.
- `codigo/app/api/routes.py` contiene los endpoints de salud, runs, jobs,
  memoria, LLM y visualizacion.
- `codigo/app/services/llm.py` configura Ollama mediante `TFM_LLM_PROVIDER`,
  `TFM_LLM_MODEL`, `OLLAMA_MODEL`, `OLLAMA_HOST`, `TFM_LLM_TIMEOUT_SECONDS` y
  `TFM_LLM_THINK`.
- `codigo/app/services/vector_memory.py` configura embeddings mediante
  `TFM_EMBEDDING_PROVIDER`, `TFM_EMBEDDING_MODEL`,
  `TFM_EMBEDDING_TIMEOUT_SECONDS`, `TFM_EMBEDDING_DIMENSION` y `OLLAMA_HOST`.
- `codigo/frontend/package.json` contiene `npm run dev`, `npm run build` y
  `npm run preview`.
- `codigo/frontend/vite.config.ts` usa el puerto `5173` y proxy `/api` hacia
  `http://127.0.0.1:8010`.
- `codigo/docker/` existe como directorio reservado, pero aun no contiene
  Dockerfiles ni compose.

Decision: `extend`.

Motivo: la aplicacion ya funciona localmente. La Fase 6 debe envolverla en un
entorno reproducible sin crear otro runner, otra API ni otro frontend.

Impacto en compatibilidad: no cambia contratos, endpoints, snapshots,
artefactos ni memoria.

## Modos de trabajo

La Fase 6 mantendra dos modos:

1. Desarrollo local rapido:
   - backend en `http://127.0.0.1:8010`;
   - frontend Vite en `http://127.0.0.1:5173`;
   - Ollama local en `http://127.0.0.1:11434`;
   - tests y builds ejecutados directamente sobre el entorno de desarrollo.

2. Validacion reproducible con Docker:
   - backend y frontend levantados por compose;
   - volumenes montados para datos, reports y memoria;
   - Ollama externo al compose inicial;
   - pruebas de humo contra los servicios dockerizados.

Docker no sustituye el flujo de desarrollo local. Sirve como verificacion
adicional y como base para la demo final.

## Decision sobre Ollama

Ollama queda externo al primer `docker-compose`.

Motivos:

- evita descargar o empaquetar modelos grandes dentro de imagenes;
- mantiene el modelo `qwen3.5:4b` y el embedding `qwen3-embedding:0.6b` como
  prerequisitos verificables;
- reduce el coste y tiempo de build;
- separa infraestructura de inferencia local del empaquetado de la aplicacion.

Configuracion prevista:

```text
Local sin Docker:
OLLAMA_HOST=http://127.0.0.1:11434

Backend dentro de Docker:
OLLAMA_HOST=http://host.docker.internal:11434
```

En Linux, el compose debera anadir `host.docker.internal` mediante
`host-gateway` o una alternativa documentada.

## Puertos

Puertos canonicos de desarrollo:

```text
Backend FastAPI: 8010
Frontend Vite: 5173
Ollama: 11434
```

Para la primera version dockerizada se conservaran estos puertos siempre que no
haya conflicto con servicios locales ya levantados. Si se necesita ejecutar
modo local y modo Docker a la vez, se documentara un override de puertos en
compose, no un cambio de contrato de la aplicacion.

## Comandos base

Backend:

```text
python -m uvicorn codigo.app.api:app --host 0.0.0.0 --port 8010
```

Frontend local:

```text
npm run dev
npm run build
```

En contenedor frontend, si se usa Vite dev server, debera exponerse con host
`0.0.0.0`. Si se usa build estatico, el servidor ligero se decidira en el hito
de imagen frontend.

## Variables de entorno esperadas

LLM de chat:

```text
TFM_LLM_PROVIDER=ollama
TFM_LLM_MODEL=qwen3.5:4b
OLLAMA_HOST=http://host.docker.internal:11434
TFM_LLM_TIMEOUT_SECONDS=60
TFM_LLM_THINK=false
```

Embeddings:

```text
TFM_EMBEDDING_PROVIDER=ollama
TFM_EMBEDDING_MODEL=qwen3-embedding:0.6b
TFM_EMBEDDING_TIMEOUT_SECONDS=60
```

Para pruebas sin Ollama se podra usar:

```text
TFM_EMBEDDING_PROVIDER=local_hash
TFM_EMBEDDING_DIMENSION=128
```

No se versionaran secretos ni tokens en ficheros de entorno.

## Volumenes persistentes

Los siguientes directorios deben montarse como volumenes o bind mounts, no
copiarse dentro de imagenes:

```text
codigo/data/
codigo/reports/
codigo/models/
codigo/experiments/
```

Motivos:

- `codigo/data/raw/` contiene datasets locales potencialmente pesados;
- `codigo/data/raw/uploads/` es usado por la API para ingesta local controlada;
- `codigo/reports/runs/` contiene snapshots, metricas, informes y artefactos;
- `codigo/reports/reasoning_memory/` contiene memoria agentica persistida;
- `codigo/models/` puede crecer con modelos entrenados;
- `codigo/experiments/` contiene evidencia experimental agregada.

Las imagenes deben contener codigo y dependencias, no datos ni resultados.

## CORS y proxy

En desarrollo local, Vite resuelve `/api/*` mediante proxy hacia FastAPI. Para
Docker hay dos opciones futuras:

- mantener un proxy frontend hacia backend;
- servir frontend y backend bajo una configuracion que evite CORS.

No se modificara CORS en este hito. Si una fase posterior necesita exponer
frontend y backend en origenes distintos, se añadira una configuracion local
explicita y acotada.

## Pruebas de humo previstas

Las primeras pruebas de humo deberan comprobar:

```text
GET /health
GET /datasets/adapters
GET /llm/status
GET /runs
POST /runs con dry_run=true sobre CWRU
```

La prueba de `GET /llm/status` debe diferenciar:

- API caida;
- Ollama no accesible;
- modelo Qwen no instalado;
- proveedor LLM no soportado.

## Criterio de cierre del hito

Hito 1 queda cerrado cuando:

- Fase 5 esta documentada como referencia historica;
- Fase 6 esta declarada como guia activa;
- Ollama externo queda decidido para el compose inicial;
- puertos, variables y volumenes quedan documentados;
- la memoria academica menciona la transicion.
