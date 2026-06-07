# Fase 10 - Hito 10.5A - Agentes como runtime investigativo

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Iniciar Hito 10.5 convirtiendo la pestaña `Agentes` en una vista de
investigacion agentica mas clara: eventos, decisiones, memoria, ejecutores y
errores deben leerse como señales trazables, no como decoracion visual.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reorganizar la vista Agentes usando los eventos runtime y memoria ya
persistidos, sin crear contratos nuevos ni simular razonamiento inexistente.
```

Pieza canonica reutilizada:

- `codigo/frontend/src/components/agents/AgentObservabilityView.tsx`
- `codigo/frontend/src/lib/agentRuntime.ts`
- `AgentRuntimeEvent`
- `AgentMemoryPanel`

Decision:

```text
adapt + extend
```

Motivo: la vista ya contenia mapa de agentes, detalle, memoria y conversacion.
La mejora necesaria era jerarquizarla y recuperar una timeline real de eventos,
no crear una visualizacion paralela.

## Cambios implementados

En `AgentObservabilityView`:

- se añade una banda superior de investigacion agentica;
- se muestran contadores reales de decisiones, memoria, ejecutores, errores,
  agentes activos y ultimo evento;
- se incorpora una timeline de eventos runtime usando `event.sequence`,
  `event.title`, `sourceLabel`, `stage` y `kindLabel`;
- la seleccion de un evento en timeline enfoca el agente propietario;
- se mantiene el mapa de agentes, detalle estructurado, memoria y conversacion.

En `styles.css`:

- se añaden estilos para la banda de investigacion;
- se marca `agent-overview-panel` como panel ancho;
- se ajusta responsive para `agent-research-grid`.

## Criterios metodologicos

La vista no inventa pensamiento:

- todo contador sale de `AgentRuntimeEvent`;
- la timeline solo muestra eventos persistidos;
- la memoria se consulta desde `AgentMemoryPanel`;
- la conversacion se deriva de eventos reales mediante `agentRuntime.ts`;
- si no hay eventos, se muestra ausencia.

## Verificacion

Comando ejecutado:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

## Siguiente paso

Hito 10.5B deberia mejorar el detalle de cada agente:

- separar decision, herramientas, memoria citada y payload;
- plegar JSON tecnico por defecto;
- destacar fallbacks o errores reales;
- conectar mejor memoria usada/rechazada con cada evento.
