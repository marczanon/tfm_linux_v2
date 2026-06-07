# Fase 10 - Hito 10.7D - Cierre sala 3D industrial

Fecha: 2026-06-06.

Estado: implementado y verificado con build local y Playwright headless.

## Objetivo

Cerrar el Hito 10.7 con un pulido operativo de la sala 3D industrial: enfoque
rapido de marcadores, fallback de serie temporal vacia y trazabilidad de la
verificacion.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Cerrar la sala 3D industrial como capa opcional de inspeccion, reutilizando la
escena, el mapeo temporal y la interaccion ligera existentes.
```

Piezas revisadas y reutilizadas:

- `codigo/frontend/src/components/visualization/IndustrialScene3D.tsx`;
- `codigo/frontend/src/lib/visualization3d.ts`;
- `codigo/frontend/src/styles.css`;
- `codigo/docs/112_fase10_hito7a_sala_3d_base_threejs.md`;
- `codigo/docs/113_fase10_hito7b_mapeo_temporal_3d.md`;
- `codigo/docs/114_fase10_hito7c_interaccion_3d_ligera.md`.

Decision:

```text
extend
```

Motivo: el hito ya tenia escena, datos temporales e interaccion. El cierre
debia pulir controles y estados, no crear otra escena ni otro flujo.

## Cambios implementados

En `IndustrialScene3D.tsx`:

- se anaden acciones compactas para enfocar marcadores reales:
  - primer pico;
  - aviso sostenido;
  - fallo historico.
- cada accion:
  - recentra `OrbitControls` sobre el marcador;
  - mueve la camara a una vista cercana;
  - fija la ficha del marcador seleccionado.
- el boton de recentrado vuelve a la camara inicial y libera la seleccion.
- se anade estado vacio cuando `TemporalRunSeries` no trae puntos visibles para
  construir la escena.

En `styles.css`:

- se anaden estilos para acciones de marcador;
- se anade fallback de serie temporal vacia;
- se ajustan acciones y ficha en movil.

Ajuste posterior de usabilidad:

- se reutiliza `VisualModeToggle` tambien en el panel superior de run analizada;
- al activar `3D`, la interfaz hace scroll automatico hasta la sala industrial;
- el cambio evita que la escena quede oculta bajo metricas, estado operacional,
  recomendacion agentica y comparacion visual.

## Resultado del Hito 10.7

La sala 3D queda compuesta por:

- `10.7A`: escena Three.js aislada, fallback WebGL y carga diferida.
- `10.7B`: mapeo temporal 3D con barras por ventana, color por estado y altura
  por riesgo.
- `10.7C`: hover/click con ficha compacta de barras y marcadores.
- `10.7D`: enfoque rapido de marcadores y cierre de estados/fallback.

La sala 2D sigue siendo el modo por defecto y la fuente principal de lectura.
La sala 3D queda como capa opcional de inspeccion industrial.

## Criterios metodologicos

- Los marcadores salen de campos persistidos (`first_alert_x`,
  `first_persistent_alert_x`, `failure_x`).
- No se inventa RUL ni diagnostico nuevo.
- No se crea ningun endpoint ni contrato nuevo.
- `three` sigue cargado bajo demanda mediante `React.lazy`.
- El modo 2D no depende de WebGL.

## Verificacion

Comandos ejecutados:

```text
cd codigo/frontend
npm install --save-dev @playwright/test
npx playwright install chromium
npm run build
```

Resultado:

```text
tsc --noEmit && vite build
OK
```

Observacion de bundle:

- el bundle principal sigue alrededor de `281 kB`;
- el chunk `IndustrialScene3D` queda separado y se carga solo al activar `3D`;
- Vite mantiene el aviso de chunk grande por `three`, esperado para este hito.

Validacion visual automatizada:

- se ejecuta Chromium con Playwright sobre `http://127.0.0.1:5173/`;
- se abre `Visualizacion`, se activa `3D` y se valida la escena en desktop
  `1440x1000` y movil `390x844`;
- la run validada es
  `fase9-hito4b-ae-readiness-lite-001_autoencoder_dense`;
- se confirma interaccion con marcador de fallo mediante boton de enfoque y
  ficha seleccionada;
- se capturan screenshots de pagina y escena en `/tmp/tfm-frontend-3d-validation/`;
- se analiza la imagen de la escena con Pillow para comprobar dimensiones,
  variedad cromatica y muestras no equivalentes al fondo.
- tras el ajuste de usabilidad, se valida que activar `3D` desde el selector
  superior desplaza la pagina hasta la sala industrial y deja el canvas visible
  en el viewport.

Resultado del analisis de pixeles sobre screenshots:

```text
desktop scene: 1096x391, 97 buckets de color, OK
mobile scene: 636x882, 96 buckets de color, OK
top toggle: canvas visible a 73 px del viewport, OK
```

Nota tecnica: la lectura directa del framebuffer WebGL con `gl.readPixels`
devuelve ceros en Chromium headless con el buffer de dibujo no preservado, por
lo que la validacion de pixeles se realiza sobre la captura compositada real de
la escena. No se modifica la configuracion de Three solo para facilitar el test.

## Siguiente paso

Tras cerrar Hito 10.7, el siguiente bloque natural de Fase 10 queda fijado como
Hito 10.8:

- oficina 3D de agentes dentro de `Agentes`;
- separada de la sala industrial de `Visualizacion`;
- basada en eventos reales de `AgentRuntimeEvent`;
- sin backend ni contratos nuevos en el primer subhito;
- documentada como plan operativo en
  `codigo/docs/116_fase10_hito8_oficina_3d_agentes_plan.md`.

El primer subhito recomendado para manana es `10.8A`: base estatica de oficina
3D, lazy loading, fallback WebGL y validacion visual minima.
