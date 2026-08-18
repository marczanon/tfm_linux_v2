# Fase 11: refuerzo del binding de evidencia en monitoring review

Fecha: 2026-08-12

Estado: implementado y validado con pruebas focales. No se ha ejecutado una
nueva bateria Qwen ni se ha modificado el resultado publicado de V3.

## 1. Motivo

El gate V3 quedo correctamente bloqueado porque dos respuestas no citaron la
referencia canonica de su vista causal. La frontera evitó una decision no
trazable, pero exigia al modelo copiar dos veces un identificador opaco de 123
caracteres. Ademas, el esquema JSON solo exigia cadenas no vacias: el catalogo
estaba en el prompt, pero no en el contrato generativo.

Este incremento refuerza esa frontera sin repetir el gate y sin alterar sus
resultados historicos.

## 2. Decision de reutilizacion

La capacidad añadida se define asi:

> ligar de forma verificable la vista causal, los registros mostrados y las
> referencias persistidas, manteniendo la identidad canonica bajo control del
> backend.

Se extienden los propietarios existentes:

- `MonitoringReviewStore` sigue construyendo y leyendo la vista causal;
- `pipeline_runner.py` mantiene el handoff hacia el subgrafo;
- `monitoring_reviewer.py` conserva prompt, reparacion, fallback y decision;
- `MonitoringReviewDecision` continua siendo el contrato persistido;
- el ledger y el gate publicados no se reescriben.

No se crea otro store, otro grafo ni otro formato de decision.

## 3. Frontera v2

La vista actual contiene un unico artefacto causal. Por tanto, no existe una
seleccion epistemica real entre varias evidencias. El contrato queda separado
en dos identidades:

```text
LLM:      evidence_refs = ["causal_view"]
backend:  evidence_refs = ["evidence:<session>:<trigger>"]
```

El esquema efectivo fija `const="causal_view"`, `minItems=1`, `maxItems=1` y
`uniqueItems=true` tanto en la decision como en la hipotesis. El backend exige
coincidencia exacta entre ambas, sin trim, case folding, prefijos, similitud ni
sustitucion difusa. Solo despues de validar el alias lo resuelve a la referencia
canonica antes de calcular el hash y persistir la decision.

La traza runtime declara explicitamente:

```text
mode = server_singleton
llm_handle = causal_view
canonical_refs = referencias materializadas por el backend
```

Por ello este mecanismo se describe como *binding causal determinista*, no
como seleccion agentiva de evidencia ni como prueba de grounding semantico.

## 4. Handoff sellado

La lista de registros que recibe el subgrafo se valida contra el artefacto de
la vista antes de invocar al cliente de lenguaje:

- existe exactamente un artefacto causal;
- el numero de registros coincide con `record_count`;
- la serializacion determinista coincide con su SHA-256;
- los campos coinciden exactamente con la whitelist declarada;
- los `record_id` son no vacios y unicos;
- cada `source_time` es valido y no supera el cutoff ni el maximo del artefacto.

Una lista mutada con la misma vista ya no puede llegar al prompt. Las decisiones
previas incluidas como contexto tambien deben pertenecer a la misma hija,
trigger, cutoff y vista, y conservar las mismas referencias canonicas.

## 5. Versionado y compatibilidad

Se versionan el prompt y el esquema como `monitoring_review_prompt_v2` y
`monitoring_review_llm_response_v2`. La huella del prompt incluye el texto del
sistema, las reglas estables y los nombres de sus secciones; la del esquema
incluye el alias cerrado.

Las decisiones finales siguen usando `MonitoringReviewDecision` y referencias
canonicas, de modo que persistencia, API, sala de agentes y gate no necesitan
un formato paralelo. Los artefactos V2/V3 permanecen inmutables y su dictamen
continua bloqueado.

## 6. Verificacion proporcional

No se ejecutaron Ollama, Qwen, el replay NASA completo ni Playwright. Se usaron
clientes simulados y pruebas focales para comprobar:

- esquema cerrado y fingerprint versionado;
- resolucion del alias a la referencia canonica;
- ausencia del identificador largo en el prompt;
- reparacion ante alias externo y fallback ante dos respuestas invalidas;
- rechazo controlado de tipos no string, espacios, cambios de mayusculas y
  `record_id` usados como cita;
- rechazo de decisiones previas procedentes de otra vista;
- rechazo de registros causales mutados antes de llamar al LLM;
- persistencia del modo `server_singleton` en la traza runtime.

El gate focal de integracion termina con 36 pruebas correctas y una advertencia
externa de LangGraph. Este recuento no es la suite total del repositorio ni una
validacion de comportamiento real de Qwen.

## 7. Limites y siguiente incremento

El cambio elimina una fragilidad contractual conocida, pero no demuestra que
una nueva bateria vaya a superar el gate. Tampoco mide que una afirmacion este
semanticamente sostenida por un registro concreto: con un unico artefacto, el
alias solo prueba pertenencia al alcance causal.

Antes de otro gate completo, el siguiente refuerzo razonable es introducir un
catalogo de registros corto y sellado (`E01`, `E02`, ...), separar
`causal_scope_refs` de `support_refs` y resolver los handles de forma exacta a
sus registros canonicos. Solo entonces tendra sentido medir seleccion agentiva
de soporte; despues se decidirá si procede una bateria prospectiva nueva.

Ese incremento queda implementado, sin nueva bateria, en
`139_fase11_catalogo_evidencia_causal_por_registro.md`. El binding singleton se
conserva exclusivamente como semantica historica de las runs anteriores.
