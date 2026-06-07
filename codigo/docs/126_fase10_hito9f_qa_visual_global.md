# Fase 10 - Hito 10.9F - QA visual global

Fecha: 2026-06-06.

Estado: implementado y cerrado.

## Objetivo

Cerrar el bloque `10.9` de identidad visual industrial con una verificacion
global del frontend tras los cambios de shell, cockpit, reduccion textual,
memoria agentica visual y metricas como subpantalla de `Visualizacion`.

## Alcance

Incluido:

- comprobacion de backend local y registro de runs;
- captura desktop y movil de vistas principales;
- revision de overflow horizontal;
- revision de errores de consola y respuestas fallidas;
- build frontend final.

No incluido:

- cambios backend;
- cambios de contratos API;
- nuevas metricas;
- nuevas vistas funcionales;
- rebuild Docker.

## Protocolo de reutilizacion

Capacidad buscada:

```text
Validar la coherencia visual global del frontend ya implementado en 10.9A-E.
```

Piezas reutilizadas:

- `AppShell`;
- `CockpitView`;
- `PipelineConfig`;
- `AgentObservabilityView`;
- `AgentMemoryShowcase`;
- `VisualizationView`;
- estilos globales de `styles.css`;
- endpoints existentes `/health` y `/runs`.

Decision:

```text
reuse + verify
```

Motivo: no se detectaron incidencias visuales bloqueantes que justificasen crear
componentes o cambiar logica. El hito se cierra como verificacion y evidencia.

## Verificacion local

Servicios:

```text
Backend FastAPI: http://127.0.0.1:8010
Frontend Vite:  http://127.0.0.1:5173
```

Comprobaciones API:

- `GET /health`: correcto;
- `GET /runs`: correcto, con runs persistidas disponibles.

Run usada para revision visual:

```text
fase9-agentic-modeler-readiness-lite-llm-guardrail-001
```

Playwright:

- desktop `1440x1100`;
- movil `390x920`;
- vistas revisadas: `Cockpit`, `Nueva run`, `Agentes Runtime`, `Agentes
  Memoria`, `Visualizacion Estado` y `Visualizacion Metricas`;
- sin errores de consola;
- sin respuestas fallidas;
- sin overflow horizontal detectado.

Capturas:

```text
/tmp/tfm-frontend-109f-desktop-cockpit.png
/tmp/tfm-frontend-109f-desktop-new-run.png
/tmp/tfm-frontend-109f-desktop-agents-runtime.png
/tmp/tfm-frontend-109f-desktop-agents-memory.png
/tmp/tfm-frontend-109f-desktop-visual-default.png
/tmp/tfm-frontend-109f-desktop-visual-metrics.png
/tmp/tfm-frontend-109f-mobile-cockpit.png
/tmp/tfm-frontend-109f-mobile-new-run.png
/tmp/tfm-frontend-109f-mobile-agents-runtime.png
/tmp/tfm-frontend-109f-mobile-agents-memory.png
/tmp/tfm-frontend-109f-mobile-visual-default.png
/tmp/tfm-frontend-109f-mobile-visual-metrics.png
```

Build:

```text
cd codigo/frontend
npm run build
```

Resultado: correcto.

Nota: Vite avisa de un chunk mayor de `500 kB`, asociado al bloque
WebGL/Three.js ya cargado de forma diferida. No bloquea el cierre.

## Observaciones

- La app mantiene el lenguaje visual industrial: sidebar oscuro, superficies
  tecnicas, acentos por estado, botones compactos y baja carga textual.
- `Cockpit` queda como vista principal de control.
- `Agentes` mantiene profundidad bajo `Runtime` y separa la subpestana visual
  `Memoria`.
- `Visualizacion` separa `Estado`, `Metricas`, `Agente`, `Comparar`, `Serie` y
  `Mapa`, evitando la cascada de graficas en la primera lectura.
- Cuando el backend responde pero Ollama/LLM no esta activo, la UI puede mostrar
  API correcta y LLM `offline`. Es un estado real del entorno, no una rotura
  visual.

## Cierre

El Hito `10.9` queda cerrado como bloque de identidad visual industrial y
reduccion de texto visible.

Nota posterior: `10.10 - Informe, evidencia y artefactos` queda implementado en
`codigo/docs/127_fase10_hito10_informe_evidencia_artefactos.md`.

Siguiente paso recomendado: `10.11 - Pulido, QA visual y Docker`.
