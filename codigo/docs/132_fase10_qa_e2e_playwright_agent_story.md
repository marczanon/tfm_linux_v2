# Fase 10: QA E2E versionado de la historia agentica

Fecha: 2026-08-10.

Estado: gate E2E versionado y cerrado en Chromium desktop y movil.

## Capacidad

Convertir las comprobaciones manuales de la sala de control agentica en una
suite reproducible de navegador. El objetivo del gate es detectar regresiones
en la historia de los siete agentes, la divulgacion progresiva y la semantica
visual de memoria RAG tanto en escritorio como en movil.

Esta suite comprueba la representacion de evidencia ya persistida. No ejecuta
el pipeline, no genera recuerdos y no pretende demostrar la calidad cientifica
de un modelo o de una ejecucion.

## Reutilizacion obligatoria

Capacidad buscada:

```text
Versionar el QA de navegador de la historia agentica sin depender del runtime industrial.
```

La revision previa encontro propietarios claros que se pueden ampliar:

- `@playwright/test` ya estaba declarado en `package.json` y fijado en
  `package-lock.json`;
- Vite ya proporcionaba `build` y `preview` para servir el frontend;
- `api.ts` concentra las llamadas HTTP bajo una unica base `/api`;
- la navegacion, las tarjetas de agente, los selectores de profundidad y el
  recorrido temporal ya exponen nombres accesibles reutilizables;
- las vistas desktop y movil comparten los mismos componentes y contratos.

Decision:

```text
extender la infraestructura existente + congelar fixtures de contrato
```

No se crea un segundo frontend, un backend de pruebas ni una variante de los
contratos de produccion. Las fixtures E2E deben satisfacer los tipos existentes
y actuar exclusivamente como respuestas HTTP deterministas.

## Infraestructura

La configuracion vive en `codigo/frontend/playwright.config.ts` y establece:

- comprobacion estricta de tipos E2E y bundle de produccion generados antes del
  test mediante `pretest:e2e`;
- base HTTP fijada a `/api` durante la compilacion para que ninguna variable de
  entorno local permita escapar del mock;
- servidor `vite preview` en `http://127.0.0.1:4173`;
- puerto estricto y prohibicion de reutilizar un servidor ya existente;
- un unico worker, sin reintentos, para que una carrera no quede ocultada;
- Chromium desktop con viewport `1440 x 1000`;
- Chromium movil con viewport `390 x 920` y emulacion de `Pixel 7`;
- esquema claro y locale español en el contexto de navegador;
- captura y traza solo cuando una prueba falla;
- informe de consola y reporte HTML local.

El puerto dedicado evita confundir el gate con una instancia de desarrollo que
pueda estar abierta en `5173`. `reuseExistingServer=false` convierte una
colision en un fallo explicito en lugar de probar un bundle antiguo.

## Aislamiento de backend y modelos

La suite instala el enrutador de Playwright antes de navegar a la aplicacion e
intercepta todas las solicitudes `**/api/**`. El mock responde, como minimo, a:

- salud, estado LLM, catalogo de runs y adaptadores;
- snapshot, artefactos, eventos, informes y visualizacion de la run enfocada;
- estado, colecciones y registros de memoria al abrir `Agentes`.

Cualquier ruta API no declarada hace fallar la prueba. No se permite que
una omision caiga silenciosamente sobre el proxy de desarrollo.

Como consecuencia, el gate no necesita:

- FastAPI en `8010`;
- Ollama en `11434`;
- Qdrant o PostgreSQL;
- una ejecucion nueva con Qwen3.5 o Qwen3;
- datos NASA IMS disponibles en disco.

El estado LLM es una respuesta estatica del mock: la historia inspeccionada ya
esta persistida y no requiere inferencia durante la prueba. Este aislamiento no
sustituye las validaciones end-to-end reales del pipeline; evita que su coste o
disponibilidad contaminen una regresion puramente visual.

## Escenarios congelados

Las fixtures son sinteticas, pequenas y se declaran como datos de
contrato. No deben copiar fragmentos de varias runs para fabricar una
ejecucion historica ideal que nunca existio.

### Historia agentica base

La run autocontenida conserva identificadores, secuencias y timestamps
estaticos y representa:

- los siete roles visibles;
- hipotesis y decisiones estructuradas;
- decisiones enlazadas a resultados por `decision_id` exacto;
- ausencia de fallbacks y errores en el camino nominal;
- divulgacion desde `Historia` hacia `Auditoria`;
- recorrido temporal sobre un orden de eventos inequívoco.

El exito de un ejecutor solo acredita que la accion se materializo; la fixture
no debe presentarlo como confirmacion automatica de la hipotesis.

### Estados RAG independientes

Se congelan cuatro escenarios pequeños y declarados, cada uno con una unica
run sintetica:

1. **Traza exacta sin actividad RAG (`0/0`)**: los siete agentes participan,
   pero no consta consulta ni contexto de memoria.
2. **Utilizada (`1/1`)**: recuperacion y decision comparten contexto e
   identificadores, y el uso queda acreditado mediante cita explicita.
3. **Filtrada y no utilizada (`1/0`)**: el control de calidad excluye un
   candidato antes del agente; el unico recuerdo efectivo llega al modelador,
   que declara no utilizarlo.
4. **No disponible (`0/0`)**: existe un evento `retrieval_unavailable` fiel al
   contrato de produccion, sin inventarle un `decision_id` ni un contexto.

Estas variantes congelan la regla central del frontend: recuperar no equivale
a usar. Los titulos del corpus aportan contexto legible, pero no demuestran
influencia por si solos.

En las cuatro variantes las respuestas de `/memory/status`, colecciones y
registros son identicas. La condicion RAG solo se codifica en los eventos; el
indice y el snapshot se limitan a reflejar el identificador y los recuentos de
cada traza. El corpus describe lo que podria recuperarse, mientras que los
eventos acreditan lo ocurrido en la run.

## Comprobaciones incorporadas

El gate se mantiene pequeño y orientado a comportamiento:

- cargar automaticamente una run sin carreras;
- reconocer las siete tarjetas y seleccionar un agente por su nombre;
- leer la ficha `Cree-Elige-Recuerda-Ocurre`;
- recorrer eventos mediante el control temporal;
- abrir `Auditoria` y `Memoria` bajo demanda;
- distinguir los cuatro estados RAG congelados;
- comprobar que el documento no tiene overflow horizontal;
- fallar ante errores de pagina, errores de consola o llamadas API no
  interceptadas.

No utiliza esperas temporales fijas. Las pruebas esperan estados
observables mediante roles, nombres y contenido visible.

## Accesibilidad como contrato de prueba

Los selectores priorizan la semantica accesible de la interfaz:

- navegacion `Vistas principales` y boton `Agentes`;
- grupos `Profundidad de lectura`, `Vista agentica` y
  `Modo de oficina agentica`;
- estados con `aria-pressed` para seleccion y profundidad;
- rango `Seleccionar evento de la historia`;
- botones de agente con nombre y decision;
- desplegables nativos para el contraste de hipotesis.

Esto reduce el acoplamiento a clases CSS y convierte una perdida de nombre,
rol o navegacion por teclado en una regresion relevante. Antes de navegar, el
harness aplica `reducedMotion="reduce"`; la prueba 3D instrumenta ademas
`requestAnimationFrame` para verificar que la escena no inicia su bucle.

## Comandos

Instalacion inicial del navegador en una maquina nueva:

```bash
cd codigo/frontend
npx playwright install chromium
```

Ejecucion normal:

```bash
npm run test:e2e
```

`npm` ejecuta antes `pretest:e2e`: valida los tipos de configuracion, fixtures,
mocks y especificaciones, fija `VITE_API_BASE_URL=/api` y compila el bundle de
produccion.

Depuracion con navegador visible:

```bash
npm run test:e2e:headed
```

Abrir el ultimo informe HTML:

```bash
npm run test:e2e:report
```

Los directorios `playwright-report`, `test-results` y `blob-report` quedan
excluidos del control de versiones.

## Verificacion realizada

El gate final contiene dos especificaciones y ocho comportamientos. Playwright
los proyecta sobre ambos dispositivos:

```text
npx playwright test --list: 16 casos descubiertos
npm run test:e2e: 16 correctos
build TypeScript + Vite: correcto
typecheck versionado de fixtures/specs: correcto
```

La ejecucion valida:

- siete tarjetas, ficha `Cree-Elige-Recuerda-Ocurre` y detalle tecnico plegado;
- corte temporal sin memoria, decisiones ni resultados futuros;
- escena Three.js, fallback forzado, paridad movil y ausencia de RAF con
  movimiento reducido;
- memoria usada `1/1`, filtrada y no usada `1/0`, no observada y no disponible;
- rechazo de citas nunca recuperadas y de solapamientos entre filtrados y
  recuperados;
- corpus constante entre escenarios y uso acreditado solo por eventos;
- transferencia de foco al abrir la auditoria mediante teclado;
- cero rutas API no manejadas, errores de pagina o consola;
- ausencia de overflow horizontal en `1440 x 1000` y `390 x 920`.

La primera pasada del gate detecto ademas que una consulta podia contarse dos
veces cuando conservaba simultaneamente `memory_context_id` y `query_id`. La
proyeccion se corrigio para usar un unico identificador de ciclo, y la suite
fija desde entonces una consulta para los escenarios RAG `1/1` y `1/0`.

No fue necesario ejecutar `npm install` ni modificar `package-lock.json`.

## Limites

- El proyecto de tipos E2E omite la comprobacion interna de declaraciones de
  dependencias, pero valida con modo estricto las fixtures, mocks, helpers,
  configuracion y especificaciones propias.
- Las fixtures satisfacen los contratos de transporte del frontend; no
  sustituyen los tests Pydantic del backend ni pretenden revalidar en el
  navegador cada configuracion cientifica completa.
- La prueba normal acepta canvas o fallback porque WebGL y SwiftShader varian
  entre entornos; una segunda prueba fuerza el fallback de forma determinista.
- No se introducen snapshots pixel a pixel en la primera version; son fragiles
  ante fuentes, GPU y sistema operativo. Las capturas de fallo si se conservan
  como diagnostico local.
- No existe aun un workflow de integracion continua. Versionar la suite permite
  ejecutarla localmente; automatizarla en CI es un incremento independiente.
- La suite prueba el contrato de presentacion de una traza, no la validez
  experimental de la memoria ni la generalizacion entre datasets.

## Siguiente incremento

Con la semantica visual protegida, el siguiente incremento puede ampliar la
cinematica 3D o incorporar este gate a integracion continua. Ninguno de los dos
es necesario para volver a validar la vista 2D, el recorrido y los estados RAG.
