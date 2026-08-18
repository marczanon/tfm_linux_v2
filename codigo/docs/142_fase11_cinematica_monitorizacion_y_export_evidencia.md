# Fase 11: cinemática de monitorización y exportación de evidencia

Fecha: 2026-08-18

Estado: implementado, auditado y con captura prerregistrada antes de la campaña
oficial. La campaña `nasa-p3-agentic-window-56h-v1` permanece en estado
`planned`, revisión 0. Este incremento no ejecuta Qwen, no avanza el replay y
no modifica ninguna fuente sellada por el plan oficial.

## 1. Objetivo

El objetivo es que una persona no especialista pueda seguir y revisar después
la evolución completa de la campaña sin leer logs ni JSON:

```text
telemetría observada
  -> salida del detector
  -> estado algorítmico
  -> trigger P3
  -> revisión de siete roles
  -> hipótesis y evidencias seleccionadas
  -> propuesta consultiva no aplicada
```

La misma proyección debe servir durante la ejecución, para inspección posterior
y como fuente de una secuencia de imágenes o vídeo reproducible.

## 2. Decisión de alcance

La vista 2D es la evidencia canónica. No se crea ahora otro backend ni un gemelo
digital 3D. Un 3D posterior podrá consumir el mismo modelo visual, pero nunca
sustituirá las curvas, cursores, rótulos y controles accesibles.

La implementación reutiliza:

- los 689 `ReplayTick` y sus cuatro `MonitoringFrame`;
- `MonitoringReplayChart`, el rail de estados y el scrubber existente;
- el endpoint incremental de ticks ya disponible;
- `AgentRuntimeEvent`, los parsers de hipótesis, catálogo E## y propuesta;
- el bridge entre trigger y run hija;
- Playwright para la captura posterior.

No se modifican `routes.py`, `monitoring_replay.py`, el motor P3, el runner de
campaña ni `monitoring_evidence_campaign.py`, porque forman parte de los hashes
del prerregistro oficial.

## 3. Seis lecturas coordinadas

### 3.1 Banco de cuatro rodamientos

Un esquema sincronizado muestra RMS y pico de los cuatro canales. Solo
`bearing_1/channel_1` recibe color de estado, score, Health Index y riesgo,
porque es el único con modelo. Los otros tres permanecen neutros y se rotulan
`solo telemetría · sin diagnóstico`.

RMS y pico se presentan como amplitud en la unidad del dataset, no como
desplazamiento físico reconstruido. El esquema no es un gemelo digital.

### 3.2 Presión del detector

La serie usa `score_ratio = score / threshold` en escala logarítmica y conserva
la línea `1×` como umbral. Esta escala es necesaria porque la trayectoria
oficial abarca varios órdenes de magnitud. El score no es probabilidad de fallo.

### 3.3 Reserva de salud y riesgo

Health Index y riesgo se muestran en escala 0--100 junto al rail de estados
`nominal`, `watch`, `warning` y `critical`. Son salidas algorítmicas de la
política temporal, no daño físico, onset ni RUL.

### 3.4 Orquestación causal

Un rail separa:

1. estado del detector en tiempo NASA;
2. triggers emitidos, suprimidos o agrupados;
3. lifecycle de la run hija.

La condición persistente conserva inicio y confirmación separados. Los tiempos
`dispatched_at`, `started_at` y `completed_at` pertenecen al reloj runtime y no
se colocan falsamente sobre el calendario NASA de 2004.

### 3.5 Storyboard agentivo

La campaña se narra en cuatro actos, uno por trigger primario. Cada acto contiene
siete posiciones canónicas. A medida que llegan eventos se muestran rol,
hipótesis breve, observación esperada, criterio de refutación, acción, confianza
declarada y handles E##. Una hipótesis es una declaración contrastable, no un
diagnóstico.

### 3.6 Matriz de decisiones y grounding

La matriz `4 contextos x 7 roles` codifica acción recomendada, procedencia y
validación. Un mapa rol por E## muestra qué registros seleccionó cada agente.
Cada E## queda ligada a su catálogo y contexto: `E09` de dos revisiones no es la
misma evidencia. Pertenecer al catálogo acredita binding, no soporte semántico
ni verdad física.

Al cerrar cada acto se muestra la síntesis como `Consultiva · NO aplicada`.
Un desacuerdo no se transforma en mayoría ni consenso parcial.

## 4. Prefijo causal y polling

Durante la campaña la interfaz solo representa el prefijo confirmado. Los ticks
nuevos se solicitan con `after_sequence` y se fusionan por identidad; no se
vuelve a descargar la sesión creciente en cada heartbeat. La sesión completa
se reserva para apertura, cambio de lifecycle de una hija y cierre.

Mientras una hija está activa, la vista intenta consultar sus eventos
incrementales. En la topología oficial el driver de campaña y la API observadora
son procesos distintos y el job activo vive en memoria del primero; por ello la
lectura externa puede responder 404 y la vista conserva honestamente `revisión
en análisis`. Tras el cierre se leen de una vez los eventos persistidos de la
run. No se afirma, por tanto, una animación intrallamada de Qwen ni se inventan
pasos internos; el storyboard completo es especialmente una reconstrucción
post-hoc.

## 5. Dos relojes

La cinemática distingue siempre:

- `source_time`: reloj NASA sin zona declarada;
- tiempo runtime de la campaña y de cada run hija.

En un trigger, el reloj NASA puede quedar visualmente congelado mientras se
recorren los eventos de la revisión. Ese interludio deja claro que las decisiones
se produjeron después del cutoff y no dentro del sensor.

## 6. Exportación post-hoc

No se graba el navegador durante las dos horas. La persistencia append-only ya
conserva una evidencia más completa y exacta. Antes de ejecutar se prerregistra
un plan de captura separado, enlazado al SHA del plan de campaña.

La receta canónica contiene:

- 689 beats de tick;
- 4 beats de trigger;
- 28 beats de decisión;
- 4 beats de propuesta;
- 1 beat de veredicto final.

Son 726 escenas semánticas. Cada entrada de `cinematic_timeline.jsonl` conserva
identidad, cursores, refs, hashes y enlace al beat anterior. Los PNG y el WebM
son representaciones derivadas; el timeline encadenado es la fuente auditable.

La captura prevista usa 1920x1080, locale `es-ES`, esquema claro y movimiento
reducido. Los fotogramas clave están fijados antes de observar el resultado:
inicio, final del pre-roll, cursores 353, 496, 498, 499 y 688, más veredicto.

El prerregistro materializado antes del inicio conserva:

- `capture_id`: `nasa-p3-agentic-window-56h-v1-cinematic-2d-v1`;
- SHA-256 del plan: `cbe43602e905cb033486eba24949b4a9b0a82b520f415edb0a9c7500f707ba52`;
- SHA-256 del registro: `832ed4efb677387d8ec2ad56cffbcebe5bd2fa19e9a0cf83f574a0c262836115`;
- instante de registro: `2026-08-18T14:04:41.075727Z`;
- 16 fuentes de proyección y captura selladas.

El exportador valida la sesión sobre una copia tomada bajo lock compartido. De
este modo una posible reparación de `state.json` queda confinada al temporal y
la lectura post-hoc no muta el expediente fuente.

## 7. Criterios previos al lanzamiento

Antes de iniciar la campaña deben cumplirse conjuntamente:

- plan de captura inmutable y enlazado al plan oficial;
- polling incremental sin mutaciones ni descarga completa por heartbeat;
- gráficos 2D y storyboard legibles en escritorio y móvil;
- futuro no visible al retroceder el cursor;
- `bearing_2..4` siempre sin diagnóstico;
- hipótesis, confianza y E## rotuladas con sus límites;
- propuesta siempre consultiva y no aplicada;
- modo `prefers-reduced-motion` sin animaciones continuas;
- exportador probado ante manipulación y recuentos incorrectos;
- build, TypeScript y E2E focales correctos;
- hashes del prerregistro oficial todavía válidos.

El gate previo se cerró con 11/11 pruebas Python del exportador, build y
TypeScript correctos, y 16/16 recorridos Playwright en escritorio y móvil; las
dos variantes de captura permanecen omitidas por defecto y la captura
explícita se ejecutó 1/1. El PNG de preflight 1920x1080 tiene SHA-256
`65e749ab8f499128f4b116ac22c3fe00ab7738de2e3601c7331ac7d96de6233b`.
La auditoría independiente no dejó P0/P1 reproducible.

Solo después de este cierre se ejecutará una vez `--execute`. El resultado y el
vídeo se conservarán aunque el veredicto agentivo quede bloqueado. La captura
real de 726 PNG y el WebM siguen siendo necesariamente post-hoc.

## 8. Claims permitidos y prohibidos

Se podrá afirmar que la visualización reconstruye de forma trazable la
telemetría, las salidas del detector, la orquestación y las declaraciones de los
agentes persistidas por la campaña.

No se podrá afirmar que:

- el esquema reproduce movimiento o daño físico;
- los tres canales sin modelo estén sanos o averiados;
- score, riesgo o confianza sean probabilidades calibradas;
- una hipótesis sea un diagnóstico;
- una evidencia seleccionada confirme causalidad;
- la propuesta haya sido validada, aprobada o aplicada;
- cuatro contextos o 28 roles sean muestras físicas independientes;
- el cierre del replay sea un fallo físico;
- la campaña equivalga a tiempo real industrial.
