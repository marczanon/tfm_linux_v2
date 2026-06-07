# Fase 10 - Hito 10.3B - Cockpit con run foco autocargada

Fecha: 2026-06-05.

Estado: implementado y verificado.

## Objetivo

Hacer que la vista `Cockpit` funcione como consola operacional viva desde el
primer acceso, cargando automaticamente la ultima run persistida y mostrando su
estado, artefactos, salud temporal y recomendacion agentica cuando existan.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Autocargar la run foco del Cockpit reutilizando loadRunDetail(...) y los
contratos existentes de runs, artefactos, informes y visualizacion.
```

Pieza canonica reutilizada:

- `loadRunDetail(runId)` en `App.tsx`, que ya carga snapshot, artefactos,
  informe, auditoria, debate y visualizacion mediante endpoints existentes.

Decision:

```text
reuse + adapt
```

Motivo: crear otra ruta de carga habria duplicado logica y podria romper la
trazabilidad. El cockpit debe ser una fachada operativa sobre los datos ya
persistidos, no un flujo paralelo.

## Cambios implementados

En `App.tsx`:

- se añade carga automatica de la ultima run cuando la vista activa es
  `cockpit`;
- se evita un bucle de reintentos usando una marca por `run_id`;
- se considera cargada la run foco cuando existe snapshot, aunque no exista
  visualizacion;
- el refresco manual permite reintentar la carga si el usuario lo necesita.

En `CockpitView`:

- se añade estado de carga de run foco;
- la tarjeta principal incorpora artefactos y decisiones;
- se añaden acciones directas a `Visualizacion`, `Agentes` e `Informe`;
- la tarjeta temporal distingue entre carga, ausencia de serie y datos reales;
- la recomendacion agentica muestra carga o ausencia sin sugerir falsos datos.

En `styles.css`:

- se adapta la rejilla de metricas para seis señales compactas;
- se añade estado visual de carga para salud temporal;
- se conserva layout responsive.

## Criterios metodologicos

El cockpit sigue sin inventar informacion:

- si no hay visualizacion, no simula salud temporal;
- si no hay recomendacion, no genera texto sustituto;
- si la run no tiene artefactos suficientes, lo muestra como ausencia;
- las acciones navegan a vistas existentes y reutilizan la carga canonica.

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

El siguiente bloque recomendable es Hito 10.3C:

- revisar visualmente el cockpit en navegador;
- compactar o reordenar tarjetas segun lo que se vea;
- decidir si `Informe` debe abrir una vista propia en vez de usar `Pipeline`;
- añadir acceso directo a evidencia si conviene;
- preparar el paso hacia Hito 10.4, donde el flujo de nueva run se simplifica.
