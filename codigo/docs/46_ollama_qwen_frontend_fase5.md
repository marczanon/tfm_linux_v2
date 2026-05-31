# Ollama/Qwen desde la aplicacion web Fase 5

Fecha: 2026-05-31.

## Objetivo

Hacer que la opcion `Agentes LLM` de la aplicacion web active realmente llamadas
locales a Ollama con el modelo Qwen usado en las fases previas, manteniendo los
guardarrailes de API y los contratos Pydantic existentes.

## Inventario previo

Busquedas realizadas:

```text
rg -n "qwen|Qwen|OLLAMA_MODEL|TFM_LLM_MODEL|use_llm|OllamaJSONClient|TFM_.*_MODE|Agentes LLM|API execution with use_llm" codigo/app codigo/scripts codigo/tests codigo/docs memoria/capitulos codigo/frontend/src
```

Piezas encontradas:

- `OllamaJSONClient` en `codigo/app/services/llm.py`.
- Agentes con `llm_client` y `use_llm=True` en `cleaner.py`,
  `structurer.py`, `modeler.py`, `evaluator.py`, `report_writer.py` y
  `supervisor.py`.
- Scripts historicos que ya usaban `qwen3.5:4b`.
- `PipelineRunRequest.use_llm`, ya presente en el contrato comun.
- Bloqueo explicito en API para `use_llm=true`, heredado de la ejecucion
  controlada inicial.

Decision: `extend`.

Motivo: ya existian cliente Ollama, contratos y agentes LLM. La pieza pendiente
era conectar el contrato API/UI con esos agentes de forma controlada y visible.

Impacto en compatibilidad: `use_llm=false` conserva el comportamiento
determinista previo. `use_llm=true` exige que Ollama este disponible y que el
modelo configurado exista antes de ejecutar.

## Implementacion

Backend:

- `DEFAULT_OLLAMA_CHAT_MODEL = "qwen3.5:4b"` queda como modelo de chat por
  defecto si no se define `TFM_LLM_MODEL` ni `OLLAMA_MODEL`.
- `GET /llm/status` devuelve proveedor, modelo, host, disponibilidad y modelos
  instalados.
- `build_ollama_pipeline_agents(...)` centraliza la creacion de agentes que
  fuerzan `use_llm=True` con un cliente Ollama.
- `run_dataset_pipeline(...)` construye agentes Ollama cuando
  `PipelineRunRequest.use_llm=true` y no se inyectan agentes externos.
- `POST /runs` deja de bloquear `use_llm=true`; antes de ejecutar comprueba que
  Ollama y el modelo esten disponibles.
- La memoria RAG desde API sigue bloqueada de momento: este avance solo activa
  decisiones LLM, no retrieval ni embeddings durante la run web.

Frontend:

- la carga inicial consulta `GET /llm/status`;
- la banda operativa muestra el estado/modelo LLM;
- el formulario muestra un panel compacto de Ollama/Qwen;
- al ejecutar con `Agentes LLM`, la UI refresca el estado de Ollama y bloquea si
  el modelo no esta disponible;
- el checkbox `Agentes LLM` pasa a activar ejecuciones reales con Qwen en lugar
  de provocar un rechazo fijo de la API.

## Limitaciones

- Si Qwen devuelve JSON invalido o falla una llamada durante una decision, el
  agente conserva su fallback determinista y registra menor confianza en la
  decision.
- La activacion de memoria RAG por API sigue fuera de este incremento.
- La disponibilidad se comprueba contra `/api/tags`; no se hace una llamada de
  generacion de prueba antes de cada run para evitar coste extra.

## Verificacion

Comandos ejecutados:

```text
python -m py_compile codigo/app/services/llm.py codigo/app/services/llm_agents.py codigo/app/services/pipeline_runner.py codigo/app/api/routes.py codigo/app/schemas/api_llm.py
python -m unittest codigo.tests.test_llm_service codigo.tests.test_api_runs
python -m unittest codigo.tests.test_api_runs codigo.tests.test_llm_service codigo.tests.test_graph_pipeline codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner codigo.tests.test_api_memory codigo.tests.test_run_visualization
npm run build
pdflatex -interaction=nonstopmode main.tex
curl -sS http://127.0.0.1:8010/llm/status
```

Resultado:

- la suite focal ampliada completa 61 tests correctamente;
- el frontend compila correctamente;
- la memoria LaTeX compila correctamente;
- `GET /llm/status` confirma `available=true` y
  `model_available=true` para `qwen3.5:4b`;
- una llamada directa al cliente Ollama devuelve JSON valido;
- un `POST /runs` en `dry_run=true` con `use_llm=true` devuelve un plan CWRU
  ejecutable sin rechazar el campo LLM.
