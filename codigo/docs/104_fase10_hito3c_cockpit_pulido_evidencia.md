# Fase 10 - Hito 10.3C - Pulido del Cockpit y evidencia compacta

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Pulir la vista `Cockpit` para que funcione como panel principal operativo y no
solo como resumen visual: la run foco debe enseñar de forma clara si tiene
informe, auditoria, debate y artefactos, manteniendo el texto bajo control.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Mostrar evidencia e informe en Cockpit reutilizando los datos ya cargados por
loadRunDetail(...), sin crear una vista paralela ni nuevos endpoints.
```

Piezas canonicas reutilizadas:

- `selectedArtifacts`;
- `selectedReport`;
- `selectedAuditReport`;
- `selectedReportDebate`;
- `selectedSnapshot`;
- `loadRunDetail(...)`;
- navegacion existente a `Pipeline`, `Agentes` y `Visualizacion`.

Decision:

```text
reuse + extend
```

Motivo: el cockpit ya recibe la run foco autocargada. La mejora correcta es
mostrar estado de evidencia sobre esos datos, no volver a pedirlos por otro
camino.

## Cambios implementados

En `CockpitView`:

- se recibe informe, auditoria, debate y artefactos;
- se añade una tarjeta compacta `Evidencia`;
- se muestran estados `listo`, `sin datos` o `cargando`;
- se elimina el boton `Informe` de la fila principal de acciones para reducir
  ruido;
- la accion `Abrir evidencia` lleva al detalle existente en `Pipeline`;
- se aclara el estado LLM cuando el usuario lo tiene desactivado (`LLM off`).

En `App.tsx`:

- se pasan al cockpit los datos ya cargados por `loadRunDetail(...)`.

En `styles.css`:

- se añade una rejilla compacta para evidencia;
- se mantiene responsive;
- se evita introducir texto largo en el panel principal.

## Criterios metodologicos

La tarjeta de evidencia no interpreta ni genera contenido:

- `Informe` solo aparece listo si existe `selectedReport`;
- `Auditoria` solo aparece lista si existe `selectedAuditReport`;
- `Debate` solo aparece listo si existe `selectedReportDebate`;
- `Artefactos` usa el conteo cargado de la run foco;
- si no hay datos, se muestra ausencia, no un fallback cosmetico.

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

Con Hito 10.3 suficientemente encaminado, el siguiente bloque recomendable es
Hito 10.4: simplificar `Nueva run` para que sea un flujo operativo claro y no
un formulario tecnico largo, conservando opciones avanzadas plegadas.
