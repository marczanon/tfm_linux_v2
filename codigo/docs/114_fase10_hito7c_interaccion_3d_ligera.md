# Fase 10 - Hito 10.7C - Interaccion 3D ligera

Fecha: 2026-06-06.

Estado: implementado y verificado con build local.

## Objetivo

Anadir interaccion ligera a la sala 3D industrial: hover, seleccion fijada y
lectura compacta de puntos temporales o marcadores, sin convertir el 3D en el
modo principal de analisis.

El alcance queda limitado a frontend y documentacion. No se cambian backend,
contratos API, esquemas Pydantic, grafo, agentes, ejecutores, datasets ni
memoria academica.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Permitir inspeccionar barras y marcadores 3D derivados de TemporalRunSeries
mediante hover/click y mostrar una ficha compacta de la seleccion.
```

Piezas revisadas y reutilizadas:

- `codigo/frontend/src/components/visualization/IndustrialScene3D.tsx`;
- `codigo/frontend/src/lib/visualization3d.ts`;
- `codigo/frontend/src/styles.css`;
- `codigo/docs/113_fase10_hito7b_mapeo_temporal_3d.md`.

Decision:

```text
extend
```

Motivo: la escena 3D y el mapeo temporal ya existian. La mejora se limita a
hacer inspeccion interactiva de esas mismas geometrías, sin crear otra vista ni
otro flujo.

## Cambios implementados

En `visualization3d.ts`:

- se amplia `IndustrialTimelinePoint` con campos de lectura:
  - `temporalX`;
  - `timeToFailureSeconds`;
  - `timestampStart`;
  - `stateReason`;
  - `label`;
- se amplia `IndustrialTimelineMarker` con `temporalX` y lead time;
- se define `IndustrialSceneSelection` para representar seleccion de punto o
  marcador.

En `IndustrialScene3D.tsx`:

- se usa `THREE.Raycaster` para detectar barras y marcadores;
- el hover actualiza la ficha activa cuando no hay seleccion fijada;
- un click sobre una barra o marcador fija la seleccion;
- un click en vacio libera la seleccion;
- se evita fijar seleccion durante arrastres de camara usando umbral de
  movimiento;
- cada geometria interactiva guarda su lectura compacta en `userData`;
- la ficha muestra:
  - estado;
  - salud;
  - riesgo;
  - score;
  - eje temporal;
  - lead time cuando existe;
  - razon de estado para puntos.

En `styles.css`:

- se anade panel compacto de seleccion dentro del overlay 3D;
- se mantiene responsive en movil;
- se evita que el panel cambie el tamano del canvas.

## Criterios metodologicos

- La ficha solo muestra datos procedentes de `TemporalSeriesPoint` o campos de
  marcador ya persistidos.
- No se inventa RUL ni diagnostico nuevo.
- OrbitControls sigue disponible.
- La escena 3D sigue cargada bajo demanda.
- La vista 2D sigue siendo el modo por defecto.

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

Observacion de bundle:

- el bundle principal sigue alrededor de `281 kB`;
- el chunk `IndustrialScene3D` queda separado y se carga solo al activar `3D`;
- Vite mantiene el aviso de chunk grande por `three`, esperado para este hito.

Limitacion de verificacion visual:

- no hay Playwright, Chromium ni Google Chrome disponibles en el entorno local;
- la validacion visual automatizada con screenshot/canvas-pixel queda pendiente;
- la verificacion manual esperada es abrir `http://127.0.0.1:5173/`, ir a
  `Visualizacion`, activar `3D`, pasar el cursor por barras/marcadores y fijar
  una seleccion con click.

## Siguiente paso

Hito 10.7D deberia cerrar la sala 3D con una validacion visual manual guiada,
pulido de estados vacios/fallback y posible enfoque rapido de marcadores clave
si la escena resulta suficientemente estable.
