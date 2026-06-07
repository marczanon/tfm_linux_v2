# Fase 10 - Hito 10.5B - Detalle de agente por decision, memoria y payload

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Mejorar el detalle de cada agente en la pestaña `Agentes`, separando la lectura
operativa de la decision, las señales/herramientas, la memoria citada y el
payload tecnico.

El objetivo no es hacer que la UI parezca que los agentes piensan mas de lo que
esta persistido, sino presentar mejor los eventos reales.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reordenar AgentRuntimeDetail para que un evento agentico se pueda auditar sin
leer primero un JSON completo.
```

Pieza canonica reutilizada:

- `AgentRuntimeEvent`;
- `AgentRuntimeDetail`;
- `agentEventPlainText(...)`;
- `kindLabel(...)`;
- `AgentMemoryPanel`.

Decision:

```text
adapt
```

Motivo: el detalle ya tenia toda la informacion necesaria. La mejora era de
estructura visual y auditoria, no de nuevos contratos.

## Cambios implementados

En `AgentRuntimeDetail`:

- se añade una tarjeta principal de decision;
- se separan `decision_id`, confianza, fase y siguiente nodo;
- se mantiene la lectura humana derivada del evento;
- se deja `Rationale` como bloque independiente;
- se añaden chips de herramientas y señales cuando existen en payload;
- se resaltan señales de fallback, reparacion o error solo si aparecen como
  campos reales;
- la memoria citada mantiene botones hacia el registro de memoria;
- el payload JSON queda plegado por defecto en `Payload tecnico`.

En `styles.css`:

- se añaden estilos para `agent-decision-card`;
- se añade grid compacto de facts;
- se añaden chips de señales con tonos normal, warning y danger;
- se mantiene responsive para movil.

## Criterios metodologicos

La vista no inventa herramientas ni fallbacks:

- los chips se extraen de claves reales del payload;
- si una clave no existe, no se muestra;
- el JSON completo sigue accesible;
- la memoria citada sigue basada en `event.memory_record_ids`;
- el usuario puede auditar el evento sin perder trazabilidad tecnica.

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

Hito 10.5C podria centrarse en la memoria dentro de agentes:

- conectar mejor recuerdos usados, ignorados y excluidos;
- hacer visible la calidad del retrieval sin saturar;
- destacar cuando la memoria apoya o contradice una decision;
- mantener curacion manual clara.
