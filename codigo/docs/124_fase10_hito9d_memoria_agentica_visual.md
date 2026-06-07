# Fase 10 - Hito 10.9D - Memoria agentica visual

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Convertir la memoria agentica en una subpestaña propia dentro de `Agentes`,
accesible mediante un boton con icono de cerebro. La vista debe sentirse como
una seleccion de personajes industrial: se elige un agente, se ve su identidad,
sus herramientas y sus recuerdos utiles en frases humanas cortas.

La prioridad es vistazo rapido:

```text
Elegir agente -> ver personaje -> leer recuerdos concisos -> abrir detalle si hace falta
```

## Alcance

Incluido:

- boton/subpestaña `Memoria` dentro de `Agentes`;
- selector superior de agentes tipo fichas/personajes;
- avatar visual grande del agente seleccionado;
- color por tipo de agente;
- herramientas/capacidades visibles como chips breves;
- tarjetas de memoria con frases concisas y legibles;
- zona inferior de memoria tecnica ordenada y plegada;
- reutilizacion de `AgentMemoryPanel`, `AGENT_PROFILES`, eventos runtime,
  colecciones y records existentes.

No incluido:

- cambios backend;
- nuevos endpoints;
- nuevos contratos API;
- generacion de nuevas memorias;
- eliminar la vista runtime actual;
- sustituir la oficina 3D.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mostrar la memoria agentica como experiencia visual por agente reutilizando los
records, colecciones y eventos ya disponibles en frontend.
```

Piezas revisadas:

- `AgentObservabilityView`;
- `AgentMemoryPanel`;
- `AGENT_PROFILES` y helpers de `agentRuntime`;
- `memoryTargetForAgent`, `roleLabel`, `sourceTypeLabel`, `recordStateLabel`;
- tipos `MemoryCollectionSummary`, `MemoryRecordSummary`,
  `ReasoningMemoryRecord` y `AgentRuntimeEvent`;
- `styles.css`.

Decision:

```text
adapt + new component
```

Motivo: la informacion ya existe y debe reutilizarse. La nueva responsabilidad
es puramente visual y de composicion: una subpestaña de memoria que no mezcle la
vista runtime con el dossier tecnico. No se crean contratos ni endpoints.

## Diseño funcional

### 1. Entrada desde `Agentes`

La vista `Agentes` incorporara un selector interno compacto:

```text
Runtime | Memoria
```

`Memoria` se activa con un boton/icono de cerebro. `Runtime` conserva la vista
actual de oficina, decisiones, timeline y conversacion.

### 2. Selector de agentes

Fila superior tipo seleccion de personajes:

- `Supervisor`;
- `Limpiador`;
- `Estructurador`;
- `Modelador`;
- `Evaluador`;
- `Redactor`;
- `Verificador`.

Cada ficha muestra:

- inicial/icono;
- color de agente;
- rol;
- numero de memorias;
- numero de tools/capacidades detectadas;
- estado resumido: sin memoria, recuperable, citada, revisar.

### 3. Perfil visual del agente

Cuando se selecciona un agente:

Izquierda:

- avatar/monigote visual del agente;
- color del agente;
- rol;
- estado de memoria;
- chips de herramientas/capacidades.

Derecha:

- recuerdos en tarjetas cortas;
- frases humanas, no JSON;
- maximo 3-5 recuerdos visibles;
- ejemplo de estilo:

```text
Use ventanas mas permisivas para reducir falsos positivos.
PCA separo mejor degradacion temprana que metricas binarias.
Evitar thresholds agresivos en NASA IMS por picos aislados.
```

### 4. Detalle inferior

Debajo se mantiene auditabilidad:

- recuerdos reutilizables;
- recuerdos citados;
- recuerdos ignorados;
- advertencias;
- auditorias;
- payload/detalle tecnico bajo desplegable.

Esta zona puede contener mas texto, pero ordenado por agente y plegado.

## Pasos de implementacion

1. Crear componente modular para la subpestaña visual de memoria.
2. Reutilizar `AGENT_PROFILES` para construir selector y avatar.
3. Reutilizar `memoryTargetForAgent` para mapear agente -> coleccion.
4. Derivar memorias del agente desde `memoryRecords`.
5. Derivar herramientas/capacidades desde eventos runtime y perfil del agente.
6. Crear resumen humano corto de cada memoria a partir de `summary`, `tags`,
   `outcome`, `memory_role` y `source_type`.
7. Conectar boton `Memoria` en `AgentObservabilityView`.
8. Mantener `AgentMemoryPanel` como detalle plegado, no como primera lectura.
9. Verificar build.
10. Validar desktop/movil con Playwright.
11. Documentar cierre o siguiente iteracion.

## Criterio de cierre

- `Agentes` permite entrar en memoria con boton de cerebro;
- se puede seleccionar cada agente;
- la vista muestra personaje, herramientas y recuerdos concisos;
- la memoria tecnica sigue accesible;
- no hay texto largo abierto en la parte superior;
- build correcto;
- sin scroll horizontal desktop/movil;
- sin errores de consola.

## Implementacion realizada

Archivos principales:

- `codigo/frontend/src/components/agents/AgentMemoryShowcase.tsx`;
- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`;
- `codigo/frontend/src/styles.css`.

Resultado:

- se añade selector interno `Runtime | Memoria` en `Agentes`;
- `Memoria` usa boton con icono de cerebro;
- se crea un selector visual de 7 agentes reutilizando `AGENT_PROFILES`;
- cada agente muestra color, rol, estado de memoria, numero de recuerdos y
  tools;
- el agente seleccionado muestra avatar/personaje de pie, rol y capacidades;
- el supervisor queda diferenciado visualmente como jefe;
- los recuerdos se muestran como tarjetas breves con frases derivadas de
  `MemoryRecordSummary.summary`;
- el detalle profundo conserva `AgentMemoryPanel`, pero queda plegado;
- no se crean endpoints, contratos ni datos simulados.

## Verificacion

Build:

```text
cd codigo/frontend
npm run build
```

Resultado: correcto.

Playwright desktop/movil:

- desktop `1440x1100`: 7 fichas de agente, subpestaña visible, sin errores de
  consola, sin scroll horizontal;
- movil `390x920`: 7 fichas de agente, subpestaña visible, sin errores de
  consola, sin scroll horizontal.

Capturas:

```text
/tmp/tfm-frontend-109d-memory-desktop.png
/tmp/tfm-frontend-109d-memory-mobile.png
```

## Cierre

El hito `10.9D` queda cerrado como primera version funcional de memoria
agentica visual. La vista ya permite usar memoria como experiencia de vistazo
rapido dentro de `Agentes`, manteniendo trazabilidad tecnica bajo demanda.

## Siguiente iteracion prevista

Cuando la primera version este validada:

- hacer la vista mas original visualmente;
- mejorar avatares/personajes;
- representar relaciones entre tools, memoria y decisiones;
- diferenciar memoria reutilizable, citada, ignorada y excluida con carriles o
  railes visuales;
- enlazar memorias con runs y decisiones concretas.
