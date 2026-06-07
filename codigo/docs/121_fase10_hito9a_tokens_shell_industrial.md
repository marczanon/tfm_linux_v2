# Fase 10 - Hito 10.9A - Tokens y shell industrial

Fecha: 2026-06-06.

Estado: implementado y verificado.

## Objetivo

Iniciar el cambio de identidad visual de la aplicacion, pasando de un dashboard
generico de fondo claro a un cockpit industrial con marca propia, sin tocar
backend, datos, contratos ni flujos funcionales.

## Alcance

Incluido:

- tokens CSS de identidad industrial;
- sidebar oscuro con marca `Agentic Control`;
- navegacion compacta;
- cabecera operacional con acento industrial;
- paneles, botones y tarjetas de estado con bordes/acento tecnico;
- primera validacion responsive desktop/movil.

No incluido:

- rediseño profundo de cada pestaña;
- reduccion textual completa por vistas;
- cambios de backend;
- eliminacion de informacion o evidencia.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Dar identidad industrial al shell y a los componentes base reutilizando la app
existente.
```

Piezas reutilizadas:

- `AppShell`;
- `StatusHeader`;
- `ViewTabs`;
- `styles.css`;
- componentes comunes existentes (`StatusPill`, `StatusItem`, botones,
  paneles).

Decision:

```text
adapt + extend
```

Motivo: el shell ya estaba modularizado. Bastaba cambiar lenguaje visual,
tokens y composicion base sin crear otro frontend.

## Cambios implementados

En `AppShell.tsx`:

- la marca pasa de `TFM Pipeline` a `Agentic Control`;
- se anade un bloque compacto de identidad `PHM / Deteccion industrial`;
- el bloque de estado de sidebar se etiqueta como `Sistema`.

En `StatusHeader.tsx`:

- la cabecera pasa a `Industrial Agentic Cockpit`;
- titulo principal compacto: `Control de anomalias`.

En `ViewTabs.tsx`:

- `Pipeline` pasa a `Nueva run`;
- `Visualizacion` pasa a `Visual`;
- se mantiene la misma navegacion y estado de vista.

En `styles.css`:

- se definen tokens industriales:
  - fondo tecnico;
  - sidebar oscuro;
  - verde petroleo;
  - azul electrico;
  - ambar;
  - rojo tecnico;
  - violeta modelado;
- se rediseña sidebar con contraste y acento;
- se rediseñan tabs con estado activo tipo consola;
- se rediseñan header, paneles, botones y status cards;
- se corrige responsive movil para evitar scroll horizontal en `Cockpit`.

## Verificacion

Comandos:

```text
cd codigo/frontend
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Playwright desktop:

- viewport `1440x1100`;
- `Cockpit` visible;
- marca: `Industrial AI / Agentic Control`;
- navegacion: `Cockpit`, `Nueva run`, `Agentes`, `Visual`;
- scroll horizontal: no;
- errores de consola: `[]`.

Playwright movil:

- viewport `390x920`;
- `Cockpit` visible;
- scroll horizontal corregido:

```text
innerWidth: 390
docScrollWidth: 390
bodyScrollWidth: 390
```

- errores de consola: `[]`.

Capturas:

```text
/tmp/tfm-frontend-industrial-shell-desktop-v2.png
/tmp/tfm-frontend-industrial-shell-mobile-v2.png
```

## Limitacion

Este subhito cambia la identidad visual del shell y de componentes base. La
reduccion profunda de texto por pestaña queda para `10.9B` y `10.9C`.

## Siguiente paso

Hito 10.9B:

- rediseñar `CockpitView` como cockpit funcional de baja lectura;
- reducir texto visible;
- reforzar estados, metricas y acciones;
- mover evidencia a bloques compactos o plegables;
- mantener acceso a informe, auditoria, debate y artefactos.
