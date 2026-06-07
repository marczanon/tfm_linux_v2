# Fase 10 - Hito 10.4A - Nueva run como launcher operativo

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Iniciar el Hito 10.4 simplificando el flujo `Nueva run`: pasar de un formulario
tecnico largo a un launcher operativo por pasos, sin eliminar controles
existentes ni cambiar contratos backend.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Reordenar la configuracion de una run agentica en un flujo claro, reutilizando
PipelineConfig y los handlers existentes.
```

Pieza canonica reutilizada:

- `codigo/frontend/src/components/pipeline/PipelineConfig.tsx`

Decision:

```text
adapt
```

Motivo: `PipelineConfig` ya era el propietario correcto del formulario de
ejecucion. No convenia crear un wizard paralelo ni duplicar estado. La mejora
es de jerarquia, agrupacion y lectura visual.

## Cambios implementados

`PipelineConfig` queda organizado en cuatro pasos:

1. `Dataset`: seleccion de adaptador y resumen del dataset.
2. `Ejecucion`: modo `Full` / `Diagnostic` y `Run ID`.
3. `Agentes`: activacion LLM, memoria local, estado Ollama/modelo y Human
   Review.
4. `Preflight`: estado compacto de plan, LLM y revision, mas acciones
   `Planificar` / `Ejecutar`.

Las opciones tecnicas se conservan en `Opciones avanzadas`:

- `Adapter ID`;
- `Policy ID`;
- etiquetas sinteticas;
- fases manuales.

## Criterios metodologicos

El cambio mantiene la metodologia del proyecto:

- no se cambia `ApiRunRequest`;
- no se cambian endpoints;
- no se altera `dry_run` ni ejecucion background;
- no se oculta el estado LLM;
- no se fuerza fallback silencioso;
- los agentes siguen siendo una eleccion explicita del usuario;
- las opciones avanzadas siguen disponibles para investigacion.

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

Hito 10.4B deberia revisar el preflight visual:

- hacer mas evidente por que no se puede ejecutar;
- separar bloqueo de politica, LLM no disponible y revision humana pendiente;
- evitar que una caida a modo no LLM parezca exito;
- conectar mejor el panel de preflight con el launcher.
