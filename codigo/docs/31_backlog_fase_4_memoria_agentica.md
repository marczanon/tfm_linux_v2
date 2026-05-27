# Backlog Fase 4: memoria agentica supervisada

## Idea

La Fase 4 podra introducir un RAG de memoria agentica supervisada para que los
agentes aprendan de ejecuciones anteriores sin hacer fine-tuning pesado ni
hardcodear reglas. La fuente principal de esta memoria seran los post-mortems
de razonamiento y las revisiones humanas generadas en Fase 3.

## Motivacion

Los LLM locales pueden razonar sobre evidencia, pero no deben depender de
conocimiento interno sobre datasets industriales de nicho. La memoria
supervisada permitiria recuperar experiencias previas como contexto:

- cambios que mejoraron metricas;
- cambios que fueron parcialmente correctos;
- casos de sobrecorreccion;
- razonamientos marcados como inseguros por una persona;
- patrones que no deben repetirse.

## Flujo propuesto

```text
run persistida
-> reasoning_postmortem.json
-> human_reasoning_review.json
-> indice de memoria supervisada
-> retrieval por dataset/modelo/fallo/metrica
-> contexto compacto para el agente
-> nueva decision estructurada
```

El RAG no ejecutaria nada. Solo aportaria memoria contextual a los agentes, que
seguirian limitados por esquemas Pydantic, validaciones y ejecutores
deterministas.

## Politica de inclusion

No todo post-mortem debe entrar en memoria. La Fase 4 deberia incluir solo
casos con una decision humana explicita:

| Veredicto humano | Uso recomendado |
| --- | --- |
| `correct` | ejemplo positivo reutilizable |
| `partially_correct` | caso frontera con advertencia |
| `incorrect` | ejemplo negativo o filtro |
| `unsafe` | patron a penalizar o bloquear por contexto |
| `needs_more_evidence` | no reutilizar hasta nueva revision |

Los campos `reusable_as_context` y `exclude_from_context` de
`HumanReasoningReview` deben decidir si el caso entra o no en el indice.

## Criterios de seguridad

- La memoria no puede aprobar una run ni modificar metricas.
- La memoria no puede saltarse contratos, validaciones ni ejecutores.
- El contexto recuperado debe citar `run_id`, `decision_id`, veredicto humano y
  metricas principales.
- Los agentes deben distinguir ejemplos positivos, negativos y casos frontera.
- Un caso marcado como `unsafe` no debe usarse como recomendacion positiva.

## Artefactos de entrada

Ya existen en Fase 3:

```text
reasoning_postmortem.json
reasoning_postmortem.md
human_reasoning_review_request.json
human_reasoning_review_request.md
human_reasoning_review_template.json
```

La Fase 4 deberia anadir:

```text
human_reasoning_review.json
reasoning_memory_index.json
retrieved_reasoning_context.json
```

## Criterio de aceptacion futuro

- existe un indice local de memoria supervisada;
- solo entran casos revisados o autorizados por humano;
- el modelador puede recibir 1-3 ejemplos relevantes como contexto;
- la decision del agente cita que memoria ha usado;
- los tests verifican que casos `unsafe` o excluidos no se recuperan como
  ejemplos positivos.
