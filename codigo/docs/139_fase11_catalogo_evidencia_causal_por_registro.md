# Fase 11: catalogo de evidencia causal por registro

Fecha: 2026-08-12

Estado: implementado y comprobado mediante validacion focal. No se ha ejecutado
Qwen, un replay NASA completo ni un nuevo gate prospectivo. El resultado
publicado V3 permanece inmutable y bloqueado.

## 1. Objetivo

El binding singleton del hito anterior demostraba que una decision pertenecia
a la vista causal permitida, pero no que el agente hubiera seleccionado
registros concretos como soporte. Este incremento introduce un vocabulario
corto y cerrado por fila (`E01`, `E02`, ..., `E99`) sin exponer al modelo las
identidades canonicas largas ni crear otro sistema de persistencia.

La capacidad queda definida asi:

> permitir que cada agente seleccione de forma estructurada uno o varios
> registros de la evidencia visible, mientras el backend conserva la autoridad
> sobre alcance, identidad, resolucion y auditoria.

## 2. Reutilizacion y propietarios

Se han extendido las piezas canonicas existentes:

- `monitoring_replay.py` declara el catalogo congelado;
- `MonitoringReviewStore` lo deriva de la vista y los registros sellados;
- `monitoring_reviewer.py` construye el esquema generativo y resuelve handles;
- el subgrafo y `pipeline_runner.py` transportan una unica instancia validada;
- `run_persistence.py` la persiste con la run y comprueba su traza;
- el observador de fiabilidad distingue el soporte por registro del alcance de
  la vista.

No se modifica el ledger cientifico, no se crea otro store y no se reescriben
requests, decisiones, resultados ni gates anteriores.

## 3. Contrato sellado

`CausalEvidenceCatalog` queda ligado mediante SHA-256 a la vista causal y al
artefacto fuente. Cada `CausalEvidenceCatalogEntry` contiene:

- un handle contiguo `E01..EN`;
- el indice exacto del registro;
- la referencia del alcance causal al que pertenece;
- una referencia canonica de soporte;
- el `record_id` interno;
- el SHA-256 canonico del registro.

La referencia persistida tiene la forma conceptual:

```text
causal-record:<artifact_sha256>:<record_sha256>
```

La proyeccion es determinista: el primer registro sellado recibe `E01`, el
segundo `E02` y asi sucesivamente. Los indices y handles deben ser contiguos;
los IDs, hashes y referencias de soporte deben ser unicos. La primera version
admite como maximo 99 filas, suficiente para la evidencia compacta actual.

Las vistas nuevas materializan `evidence_catalog.json`. Una vista legacy puede
derivarlo en memoria desde sus registros ya sellados sin alterar `view.json` ni
su hash historico.

## 4. Frontera de autoridad

Se separan expresamente dos conceptos:

```text
causal_scope_refs
    Backend. Describe todos los artefactos disponibles en el cutoff.

handles E01..EN
    LLM. Seleccion exacta de los registros que afirma usar.

support_refs
    Backend. Resolucion canonica de los handles seleccionados.
```

El esquema JSON efectivo enumera solo los handles presentes en el catalogo y
exige al menos uno, sin duplicados. Decision e hipotesis deben devolver la
misma lista ordenada. Antes de Pydantic se exige coincidencia literal: no hay
`trim`, cambio de mayusculas, fuzzy matching, coercion ni autocompletado.

El servidor resuelve exclusivamente los handles elegidos; no añade el resto
del catalogo. Las decisiones persistidas conservan su contrato v1 y usan
`evidence_refs` para las referencias canonicas por registro. De este modo se
preserva la lectura de artefactos historicos y se evita introducir un segundo
formato de decision.

## 5. Prompt, fingerprints y contexto entre roles

El protocolo generativo se versiona como:

```text
monitoring_review_prompt_v3
monitoring_review_llm_response_v3
```

El prompt presenta el catalogo compacto con handle y datos del registro, pero
oculta `record_id`. Las decisiones previas se vuelven a expresar mediante
handles, sin tratarlas como verdad de referencia. El request queda fijado al
hash del esquema dinamico correspondiente al catalogo concreto; el dispatch API
carga primero ese catalogo y calcula despues los fingerprints efectivos.

El fallback sigue siendo determinista y seguro. Prioriza el ultimo registro
modelado situado exactamente en el cutoff; si no existe, usa el ultimo registro
del cutoff, el ultimo modelado visible o, finalmente, el ultimo disponible.
Sigue contando como fallback, su seleccion se marca como
`server_fallback` y no puede hacer superar un gate agentivo.

## 6. Auditoria y persistencia

La traza runtime declara `server_record_catalog` e incluye:

- `catalog_sha256`;
- `causal_scope_refs`;
- numero y handles disponibles;
- handles seleccionados por el agente;
- `support_refs` materializadas en la decision;
- origen de seleccion (`agent`, `server_fallback` o `server_protocol`);
- una proyeccion visual compacta cuyo hash queda ligado a la entrada del
  catalogo.

La persistencia guarda `monitoring_review_evidence_catalog.json`, lo registra
como artefacto y lo enlaza desde el estado y el evidence pack. Antes de escribir
se comprueba que:

- el catalogo conserva su hash y pertenece a la vista del request;
- todas las referencias de decision e hipotesis pertenecen a sus entradas;
- cada evento resuelve exactamente sus handles a las mismas referencias;
- el alcance declarado coincide con `causal_scope_refs`;
- la proyeccion mostrada en la web coincide con el hash sellado del registro;
- la lectura HTTP de eventos vuelve a verificar el SHA del resultado antes de
  exponer la traza;
- una repeticion idempotente no sustituye el catalogo por otro distinto.

La sala **Agentes** proyecta esta misma traza sin abrir otra superficie de
datos: muestra `N/M registros usados`, un rail `E01..EN` que distingue
disponibles y seleccionados, y tarjetas compactas solo para el soporte elegido.
Las referencias canonicas largas quedan relegadas al payload tecnico. Los
campos visuales de cada tarjeta forman parte de la proyeccion hasheada, y el
loader vuelve a verificar el sello de eventos antes de servirlos a la web.

## 7. Significado del grounding

Para runs nuevas con catalogo, el observador considera grounding contractual
solo si las referencias de decision e hipotesis son iguales y pertenecen a las
entradas de un catalogo ligado a la misma vista y alcance causal. Esta medida
prueba seleccion dentro del vocabulario permitido; no demuestra que el texto
este semanticamente sostenido por la fila, que la hipotesis sea verdadera ni
que exista un fallo fisico.

El camino legacy sin catalogo se conserva para leer y verificar V2/V3 con su
semantica historica. Sus cifras, figuras, hashes y veredicto no se recalculan.

## 8. Validacion y limites

La verificacion de este incremento se ha limitado a tests focales con datos y
clientes simulados: construccion y rechazo de catalogos alterados, esquema
dinamico, seleccion parcial, resolucion exacta, rechazo de handles hostiles,
contexto entre roles, fallback, traza, persistencia, dispatch y observacion del
gate. Son comprobaciones de software.

No se ha llamado a Qwen, no se ha ejecutado una bateria `3 x 4 x 7`, no se ha
publicado una V4 y no se ha modificado `current.json`. Por tanto, este hito no
acredita una mejora agentiva ni autoriza RAG o adaptacion de politicas.

El siguiente experimento valido sera un gate prospectivo completo, con plan e
identidad nuevos, sesiones nuevas y criterios prerregistrados. Debera evaluar
por separado primera respuesta, fallback, pertenencia al catalogo y, si se
quiere estudiar soporte semantico, incorporar una rubrica independiente. No se
debe sustituir selectivamente la hija adversa de V3.

## 9. Continuidad consultiva posterior

La hoja `140_fase11_policy_proposal_consultiva.md` reutiliza este catalogo para
atribuir a cada rol el soporte de su recomendacion dentro de una sintesis
determinista del servidor. Ese incremento posterior no constituye el gate
prospectivo pendiente: no llama a Qwen, no recorre de nuevo NASA y no modifica
V3. Tampoco convierte los handles seleccionados en prueba de correccion ni
aplica una politica.
