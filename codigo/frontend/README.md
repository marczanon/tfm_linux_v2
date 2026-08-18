# Frontend Fase 5

Aplicacion local para operar la API FastAPI del pipeline multiagente.

## Comandos

```bash
npm install
npm run dev
npm run build
npm run test:e2e
```

Por defecto, Vite expone la app en `http://127.0.0.1:5173` y enruta `/api/*`
hacia `http://127.0.0.1:8010`.

## Contratos reutilizados

- `GET /health`
- `GET /llm/status`
- `GET /runs`
- `POST /runs` con `dry_run=true`

La UI no planifica pipelines ni aplica politicas de dataset: envia
`ApiRunRequest` al backend y muestra el `DatasetPipelinePlan` devuelto.
Al activar `Agentes LLM`, la ejecucion requiere Ollama local con el modelo
`qwen3.5:4b` disponible.

La pantalla esta organizada como dashboard operativo: shell con navegacion
lateral, resumen de salud, configuracion de run, preflight, ejecucion, historial
de runs, agentes, memoria y visualizacion en areas separadas.

## Pruebas E2E reproducibles

La suite Playwright construye el frontend de produccion, lo sirve en el puerto
aislado `4173` e intercepta toda la API con ejecuciones sinteticas congeladas.
No necesita FastAPI, Qdrant, Ollama ni una llamada a Qwen. Comprueba la historia
visual de los siete agentes, la divulgacion de la auditoria, el comportamiento
responsive y la diferencia entre memoria recuperada, utilizada, ignorada,
filtrada y no disponible.

Antes del build, `test:e2e:typecheck` valida tambien la configuracion, fixtures,
mocks y especificaciones. El build de pruebas fija `VITE_API_BASE_URL=/api`, de
modo que un archivo de entorno local no puede desviar las peticiones fuera del
interceptor.

En una maquina nueva hay que instalar una vez el navegador de Playwright:

```bash
npx playwright install chromium
```

En Linux limpio puede ser necesario instalar tambien sus dependencias del
sistema:

```bash
npx playwright install --with-deps chromium
```

Los artefactos de fallo quedan en `test-results/` y el informe HTML en
`playwright-report/`; ambos directorios son locales y no se versionan.
