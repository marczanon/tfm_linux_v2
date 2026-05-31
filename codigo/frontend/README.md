# Frontend Fase 5

Aplicacion local para operar la API FastAPI del pipeline multiagente.

## Comandos

```bash
npm install
npm run dev
npm run build
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
