# Memoria persistida visible Fase 5

Fecha: 2026-05-29.

## Objetivo

Completar el Hito 5 haciendo visible desde la aplicacion la memoria agentica
persistida: colecciones, registros filtrables y detalle de cada
`memory_record_id`.

## Inventario previo

Busquedas realizadas:

```text
rg -n "reasoning_memory_index|index_reasoning_memory|ReasoningMemoryRecord|VectorMemoryStore|memory_store|memory_record_id|collection" codigo/app codigo/scripts codigo/tests codigo/docs
rg --files codigo/reports codigo/data codigo/app codigo/tests | rg "reasoning_memory|memory_candidate|agent_memory|modeler_memory|structurer_memory|evaluator_memory"
```

Piezas encontradas:

- `LocalJsonVectorMemoryStore`: backend canonico JSON/vectorial.
- `ReasoningMemoryRecord`: contrato canonico de recuerdo persistido.
- `reasoning_memory_index.py`: reconstruccion canonica del indice desde
  post-mortems, auditorias y candidatos.
- `codigo/reports/reasoning_memory/`: indice ya materializado con
  `modeler_memory`, `structurer_memory` y `evaluator_memory`.
- `agent_memory.py`: formato de memoria recuperada para prompts de agentes.

Decision: `extend`.

Motivo: ya existia el store de memoria y los contratos. Solo faltaba una capa
read-only de consulta API y su vista frontend. No se crea otro indice ni otra
memoria.

Impacto en compatibilidad: no cambian contratos existentes; se anaden endpoints
de lectura y `memory_dir` en `GET /health`.

## Implementacion backend

Se anaden:

- `MemoryCollectionSummary` y `MemoryRecordSummary` en
  `codigo/app/schemas/api_memory.py`;
- servicio read-only `memory_registry.py`, que reutiliza
  `LocalJsonVectorMemoryStore.list_records(...)`;
- `memory_dir` configurable en `create_app(...)`;
- `GET /memory/collections`;
- `GET /memory/records` con filtros por `target_agent`, `dataset`,
  `memory_role`, `reusable_only` y `search_text`;
- `GET /memory/records/{memory_record_id}` para abrir el recuerdo completo.

La API no reindexa, no edita memoria y no ejecuta embeddings en esta entrega.
Solo lee el indice local existente.

## Implementacion frontend

La pestaña `Agentes` incorpora un bloque de memoria persistida para el agente
seleccionado.

La vista muestra:

- coleccion asociada al agente;
- numero de recuerdos, reutilizables, datasets y excluidos;
- busqueda textual local via API;
- listado de recuerdos con `memory_record_id`, dataset, rol y resumen;
- detalle del recuerdo con veredicto humano, `run_id`, `decision_id`, fuente y
  contenido completo.

Para el supervisor se consulta `shared_methodology_memory`; para agentes
especializados se consulta su coleccion canonica.

## Limites metodologicos

La memoria se presenta como evidencia trazable y contexto reutilizable. No
aprueba runs, no modifica decisiones y no sustituye la evaluacion de metricas.
La reconstruccion del indice queda fuera de la UI en este paso y debe seguir
pasando por `reasoning_memory_index.py`.

## Verificacion

Comandos ejecutados:

```text
python -m py_compile codigo/app/schemas/api_memory.py codigo/app/services/memory_registry.py codigo/app/api/app.py codigo/app/api/routes.py
python -m unittest codigo.tests.test_api_memory
python -m unittest codigo.tests.test_api_memory codigo.tests.test_api_runs codigo.tests.test_graph_pipeline codigo.tests.test_dataset_adapters codigo.tests.test_pipeline_runner
npm run build
pdflatex -interaction=nonstopmode main.tex
curl -sS http://127.0.0.1:8010/memory/collections
curl -sS "http://127.0.0.1:8010/memory/records?target_agent=modeler&reusable_only=true&search_text=threshold"
curl -sS http://127.0.0.1:5173/api/memory/collections
```

Resultado:

- los contratos y servicios backend compilan correctamente;
- los endpoints de memoria pasan pruebas con un store temporal;
- la suite focal de memoria, API, grafo, adaptadores y runner completa 49 tests
  correctamente;
- el frontend compila con la vista de memoria integrada.
- la memoria LaTeX compila correctamente;
- `GET /memory/collections` lista colecciones reales del indice local, con
  `modeler_memory`, `structurer_memory` y `evaluator_memory`;
- el proxy Vite `/api/memory/collections` responde correctamente.

## Siguiente paso

El siguiente bloque natural es el Hito 6: hacer operativa la revision humana
minima desde la UI reutilizando `HumanReviewSettings` y `HumanApproval`.
