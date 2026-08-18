# Fase 10: sala de control agéntica como historia visual

## Capacidad incorporada

Reorganizar la traza persistida para que una persona pueda reconocer, sin leer
el informe completo, qué planteó cada agente, qué eligió, qué memoria recibió y
qué ocurrió después.

## Reutilización obligatoria

Antes del cambio se revisaron los propietarios existentes de esta capacidad en
la aplicación, los servicios y la documentación. La decisión fue:

```text
adaptar + extender + extraer una proyección pura
```

- `AgentObservabilityView` continúa siendo el propietario de la sección;
- `agentRuntime` conserva la atribución canónica de agentes, decisiones e
  hipótesis;
- la oficina 3D, el panel técnico de memoria y los contratos API se reutilizan;
- no se añaden endpoints, esquemas de backend ni una segunda interpretación de
  los eventos;
- `AgentStoryModel` se incorpora como proyección de lectura, no como nueva
  fuente de verdad.

## Criterio de diseño

La interfaz aplica el patrón *overview, selección y detalle bajo demanda*. La
vista bidimensional es la representación canónica y la escena tridimensional
permanece como una capa narrativa opcional. El diseño se inspira en:

- el mantra de búsqueda visual de Shneiderman;
- la divulgación progresiva para reservar el detalle a quien lo solicita;
- las vistas agregada y expandida de herramientas de trazas agénticas;
- los requisitos de accesibilidad para animación y movimiento no esencial.

La vista por defecto no intenta competir con el informe técnico. Su objetivo es
responder en pocos segundos:

1. ¿participaron los siete agentes?;
2. ¿hubo fallbacks o errores?;
3. ¿qué hipótesis y decisión corresponden a cada rol?;
4. ¿la memoria se recuperó, se usó o no estuvo disponible?;
5. ¿existe un resultado enlazado de forma verificable?

## Jerarquía de lectura implementada

### Nivel 0: resumen de la run

La cabecera se reduce a seis señales: estado, agentes participantes, decisiones
LLM validadas al primer intento, excepciones, memoria recuperada/utilizada y
veredicto final.

### Nivel 1: mapa de los siete agentes

Los siete roles permanecen visibles en tarjetas compactas. Cada tarjeta limita
su primera lectura a:

- identidad y función;
- estado de procedencia agéntica;
- hipótesis en una frase;
- decisión efectiva;
- señal RAG;
- resultado o estado pendiente.

Los estados normales tienen poco peso visual. Las reparaciones, fallbacks,
errores, procedencia incompleta y enlaces ausentes conservan señales explícitas.

### Nivel 2: ficha del agente seleccionado

La ficha lateral utiliza cuatro bloques estables:

- **Cree**: hipótesis declarada y estado de contraste;
- **Elige**: acción o configuración efectiva;
- **Recuerda**: consulta, recuperación, uso y descarte;
- **Ocurre**: resultado enlazado por identificador exacto.

La observación esperada y el criterio de refutación quedan en un desplegable.
El rationale completo, riesgos, referencias, payloads y cronología exhaustiva
se mantienen en `Auditoría` e `Informe`.

### Recorrido temporal

El control inferior recorre la secuencia registrada. Al seleccionar un evento,
el mapa, la ficha y la oficina 3D se vuelven a proyectar usando únicamente el
prefijo de eventos observado hasta ese punto. De esta forma una decisión antigua
no aparece acompañada por memoria o resultados que todavía no existían.

## Semántica de memoria preservada

La interfaz no deduce uso a partir del corpus ni de proximidad temporal:

- `retrieval_returned` acredita recuperación, no uso;
- `retrieval_used` y las citas de la decisión acreditan uso declarado;
- los recuerdos ignorados se muestran como no usados;
- los descartes del control de calidad se separan del rechazo del agente;
- una consulta sin candidatos no se presenta como rechazo de recuerdos;
- un registro del corpus solo aporta título y procedencia; nunca prueba que
  influyera en una decisión.

El resultado de un ejecutor se asocia únicamente mediante el identificador de
la decisión. Su éxito demuestra que la acción se materializó, pero no confirma
por sí mismo la hipótesis.

## Implementación

Los cambios se concentran en frontend:

- proyección pura `AgentStoryModel` sobre eventos existentes;
- nueva composición narrativa en la vista de observabilidad;
- memoria visual compacta con detalle científico plegado;
- estilos responsive y soporte de `prefers-reduced-motion`;
- reutilización de la escena Three.js mediante carga diferida.

La vista `Auditoría` conserva el dashboard científico, el inspector completo,
la memoria técnica, la línea temporal vertical y la conversación. No se ha
eliminado evidencia: se ha cambiado su profundidad inicial.

## Verificación

### Compilación

```text
npm run build: correcto
TypeScript: correcto
Vite producción: correcto
```

Permanece el aviso ya conocido del chunk WebGL de fallback superior a 500 kB;
no es un error del hito y la escena se carga de forma diferida.

### Escritorio

Validación Playwright sobre `1800 x 1000`:

- los siete agentes quedan dentro del primer viewport;
- altura total de la historia: `1140 px`;
- ancho del documento igual al viewport, sin overflow horizontal;
- cero bloques JSON o payload técnico en la vista narrativa;
- selección de agente, ficha, memoria, informe y auditoría operativos;
- oficina 3D con canvas WebGL y sin errores de consola.

### Móvil

Validación Playwright sobre `390 x 920`:

- ancho del documento: `390 px`;
- siete agentes disponibles;
- tarjetas no seleccionadas colapsadas;
- ficha y recorrido temporal legibles;
- sin overflow horizontal ni errores de consola.

### Casos semánticos

Las comprobaciones usan ejecuciones distintas y se identifican por separado:

- `agent-hypothesis-cwru-live-20260810`: traza runtime exacta, siete agentes,
  18 de 18 decisiones LLM validadas al primer intento, sin fallback ni errores;
  la memoria estaba desactivada;
- `nasa_set2_qwen35_memory_on_v2_pilot_001_isolation_forest`: NASA IMS oficial,
  traza histórica reconstruida y protocolo restringido; el modelador recibió un
  recuerdo y no declaró uso;
- `m4-5-qwen-qdrant-nasa-smoke-001`: piloto NASA sintético e histórico; el
  modelador recuperó y citó tres recuerdos, pero la run no fue aprobada y su
  procedencia generativa es incompleta.

No se combinan estas runs para presentar una ejecución ideal inexistente. Aún
no hay una única run que reúna NASA oficial, protocolo *run-to-failure*, runtime
exacto, hipótesis modernas, memoria útil citada y ausencia de fallbacks.

## Limitaciones y siguiente incremento

- la escena 3D ya respeta selección y corte temporal, pero todavía no incorpora
  reproducción automática ni una cinemática por actos;
- el frontend no dispone aún de suites unitarias o E2E versionadas; las pruebas
  visuales se han realizado con Playwright headless;
- conviene congelar fixtures independientes para memoria usada, no usada,
  filtrada y no disponible antes de automatizar regresiones visuales;
- no se ha ejecutado una nueva validación con Qwen en este hito.

La siguiente mejora segura sería versionar esas fixtures y dos pruebas E2E
pequeñas antes de ampliar la cinemática 3D.

## Estado posterior

Ese incremento quedó completado en
`132_fase10_qa_e2e_playwright_agent_story.md`: cuatro escenarios sintéticos,
dos especificaciones y un mock integral de la API protegen ya la historia, el
corte temporal, la accesibilidad y los estados RAG en Chromium desktop y móvil.
No fue necesaria una nueva ejecución con Qwen.
