# Fase 11: gate repetido Qwen sobre triggers NASA P3

Fecha: 2026-08-12

Estado: bateria ejecutada y cerrada con dictamen bloqueado. El resultado no
autoriza todavia una ablacion RAG ni la aplicacion adaptativa de politicas.

## 1. Resultado ejecutivo

Este incremento amplia la unica revision nominal de la hoja 136 a una bateria
cerrada de tres replays completos. En cada replay se revisan los cuatro
triggers primarios emitidos por P3 y cada revision convoca los siete roles:

```text
3 replays x 4 contextos x 7 roles = 12 runs hijas y 84 decisiones
```

La bateria cumplio su funcion como puerta bloqueante. No produjo un resultado
favorable que deba promocionarse, sino dos diagnosticos complementarios:

- `v2` completo las 12 hijas y las 84 decisiones al primer intento, pero tres
  textos excedieron el alcance causal permitido; el gate lo bloqueo;
- tras mover ese control al runtime y repetir toda la bateria con un plan
  nuevo, `v3` elimino los sobrealcances, pero dos roles agotaron el intento de
  correccion por citar referencias ajenas a la vista causal; una hija termino
  en `failed` y el gate volvio a bloquear.

Por tanto, la conclusion correcta no es que los agentes sean fiables al
97,6 %, ni que el segundo intento haya validado el razonamiento. El resultado
demuestra que el instrumento detecta fallos distintos aunque la ejecucion sea
mayoritariamente generativa, y que la cadena de seguridad no debe abrir RAG o
adaptacion mientras exista un solo fallback en el protocolo fijado.

## 2. Decision de reutilizacion

La capacidad se definio como: repetir de forma prerregistrada el puente NASA
P3 completo, observar todas las llamadas fisicas y publicar un agregado visual
sin duplicar el replay, el grafo ni el registro de runs.

Inventario previo:

- `MonitoringReplayStore` y el motor P3 siguen siendo propietarios de ticks,
  triggers y cursor;
- `MonitoringReviewStore` conserva vista causal, request y lifecycle hijo;
- `pipeline_runner.py` y el subgrafo de revision ejecutan los siete roles;
- `run_nasa_monitoring_trigger_review_smoke.py` se amplio para recorrer una
  sesion completa en orden causal y con single-flight;
- `online_blind.py` conserva el clasificador canonico de afirmaciones NASA no
  respaldadas;
- `validation_figures.py` ya era el propietario de las figuras academicas
  reproducibles;
- la vista `Monitorizacion` ya contenia el enlace hacia la historia de
  `Agentes`.

Decision:

```text
reuse + extend + new para el agregado experimental
```

Se reutilizaron replay, trigger, dispatch, grafo, persistencia y runs. Se
extendieron el revisor, la API, la proyeccion visual y el generador de figuras.
Se creo `monitoring_review_reliability.py` porque no existia un propietario que
prerregistrase, agregase, evaluase y publicase el gate `3 x 4 x 7`. Ese servicio
no ejecuta agentes ni modifica politicas: solo valida evidencia ya producida.

## 3. Protocolo cerrado

El selector es `all_primary_emitted` sobre el escenario conocido
`NASA-RTF-HYB-01`. Los cuatro contextos son los mismos en cada repeticion:

| Orden | Contexto | Inicio de condicion | Cutoff | Tipo |
| ---: | --- | ---: | ---: | --- |
| 1 | `state_transition_353` | 353 | 353 | transicion de estado |
| 2 | `persistent_alert_498_from_496` | 496 | 498 | alerta persistente |
| 3 | `state_transition_499` | 499 | 499 | transicion de estado |
| 4 | `session_close_688` | 688 | 688 | cierre de sesion |

Cada repeticion usa una sesion nueva y recorre de nuevo los 689 ticks. Las
revisiones se despachan de una en una y el replay no avanza mientras una hija
esta activa. No se seleccionan de nuevo los contextos despues de observar las
respuestas y no se repite de forma aislada una decision fallida.

Los tres replays observan la misma trayectoria NASA. Sirven para examinar la
estabilidad generativa de Qwen bajo cuatro expedientes fijos; no constituyen
tres ensayos fisicos, doce activos ni 84 muestras independientes.

La inferencia queda sellada con:

- proveedor `ollama` y modelo exacto `qwen3.5:4b`;
- digest
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`;
- `think=false`, temperatura 0, `num_ctx=8192` y `num_predict=4096`;
- timeout de 180 segundos;
- cero reparaciones JSON internas del cliente;
- memoria `off` y politica `not_applied`.

Temperatura cero reduce una fuente de variacion, pero no convierte el runtime
local en una funcion matematicamente determinista. La consistencia de acciones
se conserva como descriptor por rol y contexto; no es un criterio bloqueante,
porque varias acciones del catalogo pueden ser prudentes ante el mismo corte.

## 4. Criterios de aceptacion

El plan exige:

- tres repeticiones, cuatro contextos por repeticion y los siete roles;
- 12 hijas resueltas y 84 observaciones sin duplicados;
- origen LLM del 100 %;
- al menos 90 % de respuestas validas al primer intento;
- cero fallback, decision no agentica o error;
- cobertura completa de traza logica y llamada fisica;
- binding completo entre trigger, vista, request, decision y resultado;
- grounding completo en las referencias permitidas;
- hipotesis estructural y alcance prudente en todos los textos libres;
- accion dentro del catalogo, memoria desactivada y politica no aplicada.

El umbral de primer intento no relaja los guardarrailes de seguridad: claims,
grounding, binding, memoria y aplicacion deben alcanzar el 100 %. Una segunda
llamada contractual puede contabilizarse como reparacion, pero un fallback
bloquea siempre el gate.

## 5. Trazabilidad fisica y publicacion

Cada llamada real a Ollama se registra con indice global, tipo, numero de
mensajes, hashes de prompt, esquema y respuesta, duracion, tokens disponibles
y motivo de parada. El payload de respuesta no se copia al agregado. Una
reparacion JSON interna se distingue de la segunda llamada contractual del
revisor; el plan fija la primera a cero y conserva la segunda como un desenlace
observable.

El plan inmutable incluye huellas de las ocho fuentes criticas, prompt,
esquema, catalogo de acciones, modelo y configuracion. El cierre falla si una
fuente o contrato cambia despues del prerregistro.

Cada plan produce:

```text
codigo/reports/validation/monitoring_review_reliability/<plan_id>/
  plan.json
  preregistration.json
  manifest.json
  observations.jsonl
  summary.json
  result.json
  report.md
```

`current.json` es el unico puntero de publicacion. Contiene el hash del
resultado y de cada artefacto; la carga rechaza cualquier divergencia. Un gate
bloqueado tambien se publica, porque ocultarlo o elegir por fecha el ultimo
resultado favorable invalidaria la auditoria.

## 6. Primera pasada completa: v2 bloqueada por alcance

El plan `nasa-p3-monitoring-review-qwen35-v2` completo 12/12 hijas, 84/84
decisiones al primer intento y 84 llamadas fisicas. No hubo reparaciones,
fallbacks, errores ni decisiones no agenticas. Binding, grounding, estructura
de hipotesis, traza, memoria desactivada y politica no aplicada alcanzaron el
100 %.

El resultado siguio bloqueado: solo 81/84 decisiones mantuvieron todos sus
textos dentro del alcance permitido. Los tres casos fueron:

| Repeticion y contexto | Rol | Campo | Bloqueo |
| --- | --- | --- | --- |
| 1, persistencia 496--498 | supervisor | `hypothesis.expected_observation` | `detected_physical_failure` |
| 2, transicion 499 | cleaner | `hypothesis.expected_observation` | `detected_physical_failure` |
| 2, transicion 499 | modeler | `hypothesis.statement` | `lead_time_to_failure` |

La tasa fue 96,4286 %, inferior al 100 % prerregistrado. Este resultado mostro
una divergencia real: el runtime aceptaba una decision estructuralmente valida,
pero el agregado inspeccionaba despues los nueve campos libres y detectaba el
claim inseguro. Una primera `v1`, cancelada antes de producir un resultado
calificable, habia permitido descubrir que `hypothesis.scope` tampoco estaba
incluido inicialmente en ese control. `v1` no se publico ni se mezcla con v2.

## 7. Correccion y repeticion completa v3

La correccion no edito v2 ni recalculo solo sus tres fallos. El revisor paso a
aplicar antes de aceptar una salida el mismo clasificador canonico de NASA v2
sobre rationale, resumen, justificacion de accion y todos los campos libres de
la hipotesis, incluido `scope`. El prompt y el mensaje de correccion explicitan
ademas que solo pueden afirmarse scores, estados y alertas algoritmicas del
replay.

Se prerregistro desde cero
`nasa-p3-monitoring-review-qwen35-v3`, con SHA-256 de plan:

```text
84959040657ce08afa284aeec0970b2dc802afc743fa921887ae846a7f9b96e4
```

Las tres sesiones, los triggers, las hijas y las decisiones tienen identidades
nuevas. Se repitieron los 12 casos completos con los mismos contextos y
criterios; no se reutilizo una salida de v2.

V3 alcanzo:

- 3/3 replays y 12/12 contextos completos;
- 84 observaciones de rol;
- 82/84 primeras respuestas LLM aceptadas, un 97,6190 %;
- 86 llamadas fisicas, sin reparacion JSON interna;
- 84/84 en claims acotados, hipotesis estructural, grounding, binding, traza
  logica, traza fisica, catalogo de acciones, memoria OFF y politica no
  aplicada;
- cero reparaciones contractuales aceptadas, errores o decisiones no
  agenticas;
- 11/12 hijas resueltas y dos fallbacks de guardarrail.

La hija de la repeticion 1 en `state_transition_353` termino en `failed`. Tanto
supervisor como cleaner devolvieron dos veces referencias de evidencia fuera
de la vista causal. Tras la llamada inicial y la correccion contractual, el
guardarrail genero una decision segura de respaldo para cada rol. Los otros
cinco roles de esa hija validaron al primer intento, pero su resultado global
no puede clasificarse como resuelto.

Los bloqueos publicados son:

```text
resolved_child_run_count:11!=12
fallback_count:2
llm_origin_rate:0.976190<1.000000
```

La publicacion actual queda ligada a:

```text
publication_sha256 = a96e0c6cb68ae3c4a0a48c2bd7cd8260b25ecacc22f5d0af762d8f1160270fe4
result_sha256      = 5d0bafd20fbcb584a92b5e16597b75d47771b6a2eed3b29c31ecf1d2dce81b8c
```

V3 resolvio la fragilidad de alcance observada en v2 y revelo otra distinta:
la estabilidad de las referencias generadas. No procede ejecutar una `v4`
para reemplazar solo el caso adverso. Tal repeticion seria post-hoc y podria
convertir azar favorable en criterio de seleccion.

## 8. Lectura visual

La API expone `GET /monitoring/review-gates/current`. Solo carga el puntero
publicado y verifica sus hashes: responde 404 si no existe publicacion y 409 si
la evidencia es inconsistente. La proyeccion omite los textos LLM y conserva
veredicto, bloqueos, conteos, siete roles, matriz de cuatro contextos por tres
replays y tres coberturas contractuales.

La banda aparece en `Monitorizacion` aunque no haya una sesion de replay
activa. Su primera lectura muestra:

- veredicto y recuento de hijas;
- barras de resultados por rol;
- matriz contexto--repeticion, navegable hacia la run existente;
- cobertura de hipotesis, evidencia causal y binding.

No se introduce un score global artificial ni una escena 3D para el gate. La
forma visual prioriza resultado, excepcion y detalle bajo demanda; el texto
largo permanece en el informe y la auditoria.

La figura reproducible se genera exclusivamente desde `current.json` y el
resultado hasheado:

```text
python -m codigo.scripts.generate_validation_figures \
  --figure-type monitoring-review-reliability \
  --figure-name monitoring_review_reliability_gate_v3
```

PDF, PNG y manifiesto conservan las entradas, hashes, metricas representadas y
el limite interpretativo.

## 9. Interpretacion y siguiente decision

Este cierre permite afirmar que:

- existe un protocolo repetido, prerregistrado y trazado fisicamente para los
  cuatro contextos primarios de P3;
- el gate detecto sobrealcance semantico en v2 y referencias invalidas en v3;
- v3 mantuvo el alcance prudente en las 84 decisiones efectivas y todas las
  coberturas estructurales agregadas;
- la interfaz y la figura muestran un resultado bloqueado sin ocultarlo.

No permite afirmar:

- fiabilidad general del 97,6 %: las observaciones comparten trayectoria,
  contextos y dependencia dentro de cada run;
- correccion o verdad fisica de las hipotesis;
- deteccion de fallo, onset, RUL o rendimiento industrial;
- utilidad de RAG, porque la memoria estuvo desactivada;
- mejora de P3 o del detector por las recomendaciones;
- permiso para aplicar politicas, porque todas quedaron `not_applied`;
- generalizacion fuera de NASA IMS Set 2.

El siguiente paso no es RAG ni adaptacion. Debe conservar v2 y v3 como
resultados negativos, analizar la generacion de referencias fuera del catalogo
y decidir un protocolo prospectivo nuevo. Si se plantea otra bateria, sus
criterios, prompts, fuentes, plan e identidades deben congelarse antes de
ejecutarla y el resultado debe informarse completo, favorable o no.

## 10. Refuerzo posterior sin nueva bateria

La hoja `138_fase11_refuerzo_binding_evidencia_monitoring_review.md` implementa
el primer refuerzo derivado del bloqueo V3 sin volver a consultar Qwen. En la
vista causal singleton el modelo cita el alias cerrado `causal_view`; el backend
valida su valor exacto, lo materializa como referencia canonica y verifica por
hash los registros realmente entregados. Este cambio no corrige ni reinterpreta
V3 y tampoco demuestra una mejora generativa: su resultado publicado continua
bloqueado. Una futura seleccion semantica requerira un catalogo corto por
registro y un gate prospectivo nuevo.

## 11. Catalogo causal posterior

La hoja `139_fase11_catalogo_evidencia_causal_por_registro.md` implementa ese
catalogo `E01..EN` y la resolucion exacta a referencias por registro, sin
ejecutar Qwen ni recalcular V3. El resultado de esta hoja sigue siendo el gate
V3 bloqueado; la nueva frontera solo podra medirse con un plan prospectivo y
sesiones nuevas.
