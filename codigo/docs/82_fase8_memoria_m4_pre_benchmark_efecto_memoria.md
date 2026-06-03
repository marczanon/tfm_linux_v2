# Fase 8 - Memoria M4-pre: benchmark de efecto de memoria

Fecha: 2026-06-03.

## Objetivo

Antes de saltar a Qdrant, reranking o busqueda hibrida, se implementa una
evaluacion offline para responder a una pregunta concreta del TFM:

```text
La memoria esta haciendo algo?
```

La respuesta se separa en niveles:

- memoria no observada;
- memoria consultada sin recuerdos relevantes;
- memoria recuperada pero ignorada por el agente;
- memoria usada declaradamente por el agente;
- memoria usada de forma invalida o incompleta;
- senales comparativas frente a una run baseline.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Medir retrieval, citas, uso declarado y deltas frente a baseline usando
snapshots persistidos, sin crear un segundo sistema de runs ni repetir la
auditoria transversal existente.
```

Inventario revisado:

- `codigo/app/services/memory_usage_audit.py`;
- `codigo/app/services/transversal_memory_audit.py`;
- `codigo/app/services/run_persistence.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/schemas/state.py`;
- `codigo/scripts/audit_transversal_memory_run.py`;
- `codigo/docs/78_fase8_hoja_ruta_memoria_rag_avanzada.md`.

Decision:

```text
extend
```

Motivo: ya existian auditorias por decision y comparacion de runs. El nuevo
hito agrega esas evidencias en un benchmark de efecto de memoria, sin tocar la
ejecucion del pipeline.

## Implementacion

Se anaden:

```text
codigo/app/services/memory_effect_benchmark.py
codigo/scripts/benchmark_memory_effect.py
codigo/tests/test_memory_effect_benchmark.py
```

El servicio carga snapshots persistidos, lee decisiones agenticas, busca
artefactos `{agent}_retrieved_memory_context`, contrasta recuerdos recuperados
contra recuerdos citados y genera:

- `memory_effect_benchmark.json`;
- `memory_effect_benchmark.md`.

Agentes auditados en esta primera version:

- `cleaner`;
- `structurer`;
- `modeler`;
- `evaluator`;
- `report_writer`.

## Criterios de lectura

Una run se clasifica como:

- `no_memory_observed`: no hay retrieval ni uso declarado;
- `no_relevant_memory_returned`: hubo consulta, pero sin recuerdos;
- `retrieval_only`: se recupero memoria, pero el agente no declaro uso;
- `memory_used`: al menos un agente declaro uso valido de memoria;
- `memory_usage_invalid`: hay citas inventadas, IDs no recuperados o
  declaracion incompleta.

Por agente se mide:

- recuerdos recuperados;
- recuerdos citados;
- recuerdos ignorados;
- similitud minima/media/maxima;
- backend y modelo de embedding;
- conteos del quality gate `pass/caution/exclude_candidate`;
- IDs citados sin retrieval;
- declaraciones de uso ausentes;
- mitigaciones ausentes en warnings/casos frontera.

Si se proporciona `--baseline-run-id`, el informe compara:

- cambios en configuracion de limpieza, estructuracion o modelado;
- deltas de metricas binarias;
- deltas de metricas run-to-failure cuando existen.

La comparacion no afirma causalidad automaticamente. Solo indica senales
comparativas. Para defender causalidad habra que ejecutar pares controlados
donde la unica diferencia sea memoria activada/desactivada o memoria filtrada.

## Comando

Ejemplo:

```bash
python -m codigo.scripts.benchmark_memory_effect \
  --baseline-run-id cwru-memory-transversal-fase4-001 \
  --run-id cwru-memory-transversal-fase4-001 \
  --run-id cwru-memory-transversal-fase4-002-llm \
  --variant cwru-memory-transversal-fase4-001=memory_off \
  --variant cwru-memory-transversal-fase4-002-llm=memory_full \
  --output-dir codigo/reports/memory_benchmarks/cwru-memory-transversal-fase4-m4-pre
```

## Primer resultado real

Se ha generado un primer smoke real en:

```text
codigo/reports/memory_benchmarks/cwru-memory-transversal-fase4-m4-pre/
```

Resultado:

- runs analizadas: 2;
- baseline: `cwru-memory-transversal-fase4-001`;
- run con memoria usada: `cwru-memory-transversal-fase4-002-llm`;
- variantes: `memory_off` y `memory_full`;
- agentes con uso declarado: `structurer` y `evaluator`;
- uso invalido: 0;
- advertencias del quality gate: 0;
- recuerdos recuperados y citados: 2;
- metricas binarias frente al baseline: sin cambio.

Interpretacion:

```text
La memoria si hizo algo en la deliberacion agentica: fue recuperada y citada
por structurer y evaluator. En este par concreto no cambio las metricas, por lo
que el efecto observado es de trazabilidad/razonamiento, no de rendimiento.
```

## Siguiente paso

Construir una suite controlada de variantes:

- sin memoria;
- memoria completa;
- memoria filtrada manualmente;
- memoria con recuerdos conflictivos excluidos;
- memoria recuperada pero no obligatoria para el agente.

El objetivo sera pasar de "la memoria se usa" a "la memoria mejora, empeora o
solo explica decisiones" para el perfil `run_to_failure_degradation`.

Actualizacion M4.1:

- `83_fase8_memoria_m4_1_quality_gate_benchmark_controlado.md` formaliza el
  quality gate y las variantes controladas;
- no se introduce memoria consolidada;
- el gate no borra recuerdos ni sustituye la decision del agente.
