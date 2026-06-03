# Fase 8 - Memoria M4.1: quality gate y benchmark controlado

Fecha: 2026-06-03.

## Objetivo

Cerrar el siguiente tramo del camino de memoria sin introducir todavia memoria
consolidada. La memoria consolidada/reflexiva se pospone deliberadamente porque
podria fijar conclusiones demasiado pronto y limitar futuras deliberaciones de
los agentes Qwen.

M4.1 se centra en dos piezas:

- un quality gate determinista para recuerdos recuperados;
- etiquetas de variante controlada dentro del benchmark de efecto de memoria.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Marcar la calidad de recuerdos recuperados y documentar variantes controladas
memoria off/on/filtrada sin crear otro sistema de ejecucion ni consolidar
recuerdos.
```

Inventario revisado:

- `codigo/app/services/memory_effect_benchmark.py`;
- `codigo/app/services/vector_memory.py`;
- `codigo/app/schemas/reasoning.py`;
- `codigo/app/services/transversal_memory_audit.py`;
- `codigo/docs/82_fase8_memoria_m4_pre_benchmark_efecto_memoria.md`.

Decision:

```text
extend
```

Motivo: el benchmark M4-pre ya lee snapshots, contextos recuperados y decisiones
agenticas. M4.1 anade una capa de calidad sobre esos recuerdos y metadatos de
variante, sin alterar el pipeline ni decidir por el agente.

## Implementacion

Se anade:

```text
codigo/app/services/memory_quality_gate.py
codigo/tests/test_memory_quality_gate.py
```

Y se amplia:

```text
codigo/app/services/memory_effect_benchmark.py
codigo/scripts/benchmark_memory_effect.py
codigo/tests/test_memory_effect_benchmark.py
```

El quality gate clasifica cada recuerdo recuperado como:

- `pass`: se puede pasar al agente sin advertencia especial;
- `caution`: puede ser util, pero debe tratarse como warning/caso frontera,
  baja similitud, veredicto parcial o fuente de auditoria;
- `exclude_candidate`: no deberia entrar en el prompt en un benchmark
  controlado o deberia revisarse antes.

No se borra nada automaticamente. No se consolida memoria. No se transforma el
recuerdo en una reflexion global. Solo se anade una etiqueta auditable.

## Criterios del quality gate

Motivos de cautela:

- similitud por debajo de `min_pass_similarity`;
- `memory_role` igual a `warning`, `negative_example` o `boundary_case`;
- `source_type=memory_usage_audit`;
- `human_verdict=partially_correct` o `needs_more_evidence`;
- perfil de supervision no identificable.

Motivos de exclusion candidata:

- similitud muy baja;
- dataset distinto al de la query;
- agente objetivo incompatible;
- tags de exclusion manual o benchmark contaminado;
- conflicto explicito de perfil, por ejemplo memoria binaria usada como si
  fuera run-to-failure;
- veredicto humano incorrecto o unsafe.

Las cautelas pueden seguir llegando al agente. La diferencia es que ahora se
ven y se auditan.

## Benchmark controlado

El script acepta etiquetas:

```bash
--variant run_id=memory_off
--variant run_id=memory_full
--variant run_id=memory_filtered
--variant run_id=memory_conflict_excluded
--variant run_id=retrieval_only
```

El informe agrega:

- conteo de variantes;
- runs con advertencias del quality gate;
- por agente: pass/caution/exclude;
- IDs citados que el gate marcaria con cautela o exclusion candidata.

## Smoke real actualizado

Comando ejecutado:

```bash
python -m codigo.scripts.benchmark_memory_effect \
  --baseline-run-id cwru-memory-transversal-fase4-001 \
  --run-id cwru-memory-transversal-fase4-001 \
  --run-id cwru-memory-transversal-fase4-002-llm \
  --variant cwru-memory-transversal-fase4-001=memory_off \
  --variant cwru-memory-transversal-fase4-002-llm=memory_full \
  --output-dir codigo/reports/memory_benchmarks/cwru-memory-transversal-fase4-m4-pre
```

Resultado:

- variantes: `memory_off=1`, `memory_full=1`;
- memoria usada: `cwru-memory-transversal-fase4-002-llm`;
- agentes que citan memoria: `structurer`, `evaluator`;
- uso invalido: 0;
- advertencias del quality gate: 0;
- metricas frente al baseline: sin cambio.

Interpretacion:

```text
En este par CWRU la memoria usada pasa el quality gate y aporta trazabilidad a
la deliberacion. No demuestra mejora numerica, pero tampoco introduce
contaminacion detectable.
```

## Alcance excluido

Queda fuera de M4.1:

- memoria consolidada;
- reflexiones globales escritas por el sistema;
- borrado automatico;
- Qdrant;
- reranking Qwen;
- ejecucion automatica de baterias completas.

## Siguiente paso

Preparar una primera bateria controlada real para `run_to_failure_degradation`
cuando el espacio de datos y herramientas sea mas rico:

- `memory_off`;
- `memory_full`;
- `memory_filtered`;
- `memory_conflict_excluded`;
- `retrieval_only`.

Mientras tanto, CWRU/NASA actuales sirven como regresion, trazabilidad y prueba
de que el sistema mide correctamente el uso de memoria.
