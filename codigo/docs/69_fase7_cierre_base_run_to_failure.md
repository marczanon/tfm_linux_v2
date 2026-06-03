# Fase 7 - Cierre de base del perfil run-to-failure

Fecha: 2026-06-03.

## Objetivo

Definir que falta para poder considerar preparada la base del nuevo perfil
principal de investigacion:

```text
run_to_failure_degradation
```

El objetivo no es cerrar toda la industrializacion SaaS, ni resolver despliegue,
autenticacion, streaming real o integraciones de planta. El objetivo de cierre
de base es que la aplicacion pueda ejecutar, visualizar, comparar, explicar y
auditar trayectorias run-to-failure con protagonismo real de agentes Qwen/LLM,
sin confundir etiquetas proxy con oficiales y sin prometer RUL industrial si el
modelo aun no lo produce.

## Estado actual

Ya esta implementado:

- declaracion de `supervision_profile`, `label_source` y `label_granularity`;
- propagacion de metadatos temporales hasta ventana y prediccion;
- familia de metricas `run_to_failure_degradation`;
- visualizacion temporal de `anomaly_score`;
- comparacion de runs por metricas temporales principales;
- capa de `health_index`, `risk_index` y `health_state`;
- agentes conscientes del perfil: `modeler`, `evaluator`, `report_writer`,
  `report_verifier` y `evidence_lookup`;
- validacion con la run `fase7-paso7-nasa-common-long-v2`.

La base aun no esta cerrada porque la experiencia principal de investigacion
sigue estando repartida: parte vive en comparacion, parte en visualizacion,
parte en agentes y parte en informes. Falta convertirlo en un flujo claro de
monitorizacion e investigacion run-to-failure.

## Principio rector

Los agentes Qwen/LLM siguen siendo el sujeto principal de investigacion. Las
metricas, visualizaciones, herramientas y ejecutores deterministas no deben
quitarles protagonismo, sino darles mas evidencia, mas contexto y una frontera
segura para decidir.

Por tanto, cada pendiente de este cierre debe cumplir al menos una de estas
funciones:

- mejorar lo que el agente puede observar;
- mejorar lo que el agente puede decidir o recomendar;
- mejorar como se audita una decision agentica;
- mejorar como el analista humano entiende la decision del agente;
- evitar afirmaciones metodologicamente incorrectas sobre etiquetas, fallo o
  RUL.

## Protocolo de reutilizacion aplicado

Capacidad buscada:

```text
Cerrar la base funcional del perfil run-to-failure como panel principal de
investigacion, reutilizando runner, API, agentes, visualizacion y comparacion
existentes.
```

Inventario revisado:

- `codigo/docs/66_fase7_perfiles_supervision_binary_run_to_failure.md`;
- `codigo/docs/67_fase7_hito8_comparativa_run_to_failure.md`;
- `codigo/docs/68_fase7_hito8_monitorizacion_estado_salud.md`;
- `codigo/app/services/pipeline_runner.py`;
- `codigo/app/services/run_visualization.py`;
- `codigo/app/services/run_registry.py`;
- `codigo/app/services/agent_tools.py`;
- `codigo/app/agents/modeler.py`;
- `codigo/app/agents/evaluator.py`;
- `codigo/app/agents/report_writer.py`;
- `codigo/app/agents/report_verifier.py`;
- `codigo/frontend/src/App.tsx`;
- `codigo/frontend/src/types.ts`;
- `codigo/frontend/src/styles.css`;
- `codigo/tests/`.

Decision:

```text
extend
```

Motivo: ya existen propietarios canonicos para ejecucion, metricas,
visualizacion, comparacion, agentes e informes. No hay que crear un
`run_to_failure_runner`, ni un frontend paralelo, ni una API NASA. El cierre
de base debe compactar y enriquecer lo existente.

## Definicion de base terminada

Se considerara que la base del perfil esta terminada cuando la aplicacion pueda:

- lanzar o inspeccionar una run `run_to_failure_degradation` con Qwen/LLM;
- mostrar el estado de salud actual del activo de forma principal, no secundaria;
- explicar la trayectoria temporal hacia fallo con score, umbral, estados,
  primer aviso, falsas alarmas y fallo historico si existe;
- comparar varias runs/modelos por metricas temporales, no por F1 como criterio
  principal;
- mostrar que agente decidio que, con que evidencia y con que limitaciones;
- producir un informe agentico que trate el perfil como degradacion temporal;
- bloquear o advertir si se intenta vender una etiqueta proxy como oficial;
- distinguir con claridad entre deteccion temprana, monitorizacion de salud y
  prediccion RUL;
- pasar tests enfocados de backend, build frontend y una validacion manual de
  UI con al menos una run real persistida.

## Pendientes obligatorios

### 1. Panel frontend run-to-failure como vista principal

La mayor carencia esta en frontend. El perfil ya existe tecnicamente, pero la
pantalla aun debe sentirse como una aplicacion industrial de monitorizacion, no
como una coleccion de graficas de laboratorio.

Pendientes:

- convertir `Visualizacion` en una experiencia perfil-aware:
  - si la run es `run_to_failure_degradation`, abrir con monitorizacion de
    salud;
  - si es `binary_fault_classification`, mantener PCA y metricas binarias como
    lectura principal;
- anadir cabecera operacional del activo:
  - estado actual;
  - salud;
  - riesgo;
  - modelo;
  - perfil de supervision;
  - fuente de etiquetas;
  - tiempo hasta fallo solo si procede de replay historico;
- mejorar la curva temporal:
  - bandas de estado `nominal`, `watch`, `warning`, `critical`;
  - suavizado visual opcional del indicador de salud;
  - marcadores de primer aviso, fallo historico y umbral;
  - tooltip con evidencia suficiente para el agente y el analista;
- anadir resumen de alertas:
  - primer punto de alerta;
  - persistencia de alerta;
  - falsas alarmas en tramo nominal;
  - puntos warning/critical;
- mejorar estados vacios y advertencias:
  - sin predicciones;
  - sin metadatos temporales;
  - etiquetas proxy;
  - RUL no soportado;
- revisar responsive/mobile para que no haya solapes ni texto fuera de botones
  o paneles.

Criterio de aceptacion:

- una run run-to-failure se entiende en menos de un minuto sin abrir JSON;
- el analista ve primero salud/riesgo/estado y despues detalles tecnicos;
- no aparece F1 como decision principal del perfil temporal;
- no se recalcula nada en frontend.

### 2. Cola de activos y estado global

Ahora la app analiza una run concreta. Para parecerse a monitorizacion
industrial, aunque sea local y de investigacion, necesita una vista de activos
o trayectorias priorizadas.

Pendientes:

- exponer en listado/detalle de runs un resumen run-to-failure:
  - `current_health_state`;
  - `current_health_index`;
  - `current_risk_index`;
  - `alert_points`;
  - `warning_points`;
  - `critical_points`;
  - `model_name`;
  - `metric_families`;
- crear una cola visual de runs/activos en `warning` o `critical`;
- ordenar por riesgo, estado y recencia;
- filtrar por `supervision_profile`;
- mantener claro que se trata de runs historicas/replay, no streaming de planta.

Criterio de aceptacion:

- desde la pantalla principal se puede identificar que activos/runs requieren
  revision antes de abrir el detalle.

### 3. Comparacion visual de modelos run-to-failure

La comparacion ya distingue metricas temporales, pero aun debe convertirse en
una herramienta de investigacion mas visual.

Pendientes:

- small multiples temporales por run/modelo;
- tabla con ranking temporal:
  - deteccion antes de fallo;
  - lead time;
  - falsas alarmas nominales;
  - tendencia;
  - persistencia;
  - fallos perdidos;
- marcar mejor run por criterio, sin declarar una ganadora unica si las
  metricas entran en conflicto;
- permitir comparar solo runs del mismo perfil/politica;
- ocultar o rebajar metricas binarias cuando sean proxy.

Criterio de aceptacion:

- se puede comparar `pca_reconstruction_error`, `isolation_forest` y
  `one_class_svm` sobre el mismo protocolo temporal sin leer artefactos.

### 4. Capa agentica de interpretacion operacional

Con el principio rector aclarado, no basta con que el backend calcule estados.
Los agentes deben usar esos estados como evidencia principal.

Pendientes:

- extender `evidence_lookup` o anadir una herramienta read-only equivalente para
  exponer:
  - estado actual;
  - timeline de alertas;
  - metricas de degradacion;
  - advertencias metodologicas;
  - comparacion de modelos;
- hacer que `evaluator` y `report_writer` generen una lectura operacional:
  - que esta pasando;
  - por que el agente cree que hay degradacion;
  - que evidencia contradice o debilita la conclusion;
  - que siguiente experimento recomienda;
- anadir en frontend una tarjeta de recomendacion agentica:
  - decision del agente;
  - evidencia citada;
  - confianza;
  - limitaciones;
  - siguiente accion experimental;
- auditar que el agente no use F1 como criterio principal en este perfil;
- auditar que el agente no afirme RUL real si solo existe replay historico.

Criterio de aceptacion:

- el panel no solo muestra "critical"; tambien muestra como lo interpreta el
  agente, con evidencias citables y limites claros.

### 5. Politica versionada de salud, riesgo y suavizado

`health_state` ya existe, pero para cerrar base conviene versionar la politica.
Asi los agentes y el informe pueden citar que regla convirtio score en estado.

Pendientes:

- anadir `health_policy_id`;
- documentar umbrales de paso entre estados;
- indicar si el score esta normalizado por umbral o por min-max;
- anadir suavizado opcional del `health_index` para visualizacion y tendencia;
- conservar la serie cruda para auditoria;
- no convertir el suavizado en feature de entrenamiento salvo decision
  explicita posterior.

Criterio de aceptacion:

- dos runs comparadas pueden explicar si usaron la misma politica de estado.

### 6. Suite canonica de experimentos del perfil

Para cerrar la base no basta con una run correcta. Hace falta un pequeno paquete
canonico de ejecuciones comparables.

Pendientes:

- ejecutar o preparar runs comparables con:
  - `pca_reconstruction_error`;
  - `isolation_forest`;
  - `one_class_svm`;
- usar el mismo dataset/politica temporal;
- conservar `use_llm=true` al menos en la run principal de investigacion;
- guardar snapshots, metricas, visualizacion, informe y debate/verificacion;
- generar una comparacion final del perfil.

Criterio de aceptacion:

- existe un conjunto reproducible de runs que demuestra el perfil, no un unico
  caso aislado.

### 7. Frontera RUL experimental

La app debe ayudar a responder "si va a fallar y cuando", pero sin vender una
prediccion que todavia no existe. La base debe dejar preparada la frontera.

Pendientes:

- mantener separadas tres capas:
  - deteccion temprana de degradacion;
  - estimacion de estado/riesgo;
  - prediccion RUL;
- anadir campos opcionales para una futura prediccion RUL:
  - `predicted_rul_seconds`;
  - `predicted_failure_time`;
  - `rul_confidence`;
  - `rul_method`;
  - `rul_warning`;
- si se implementa un primer RUL experimental, debe etiquetarse como
  experimental y puede empezar por extrapolacion de tendencia o tiempo hasta
  umbral, no como pronostico industrial validado;
- el frontend debe mostrar "RUL no soportado" o "RUL experimental" de forma
  explicita segun el caso.

Criterio de aceptacion:

- el usuario entiende si la app esta detectando degradacion, estimando riesgo o
  prediciendo tiempo restante.

### 8. Informes y auditoria especificos del perfil

El informe ya es agentico, pero el cierre de base debe asegurar que el perfil
run-to-failure queda tratado como caso principal.

Pendientes:

- seccion fija de degradacion temporal en el informe;
- lectura de estado de salud actual;
- comparacion de modelos si hay varias runs;
- explicacion de etiquetas proxy;
- limitaciones de RUL;
- recomendaciones experimentales del agente;
- verificacion especifica contra afirmaciones no soportadas:
  - etiquetas oficiales inexistentes;
  - validacion industrial final;
  - RUL real no calculado;
  - causalidad no demostrada.

Criterio de aceptacion:

- `report_verifier` aprueba informes run-to-failure sin falsos positivos por
  frases negadas, pero bloquea exageraciones reales.

### 9. Validacion frontend y regresion

Antes de declarar cerrada la base hay que comprobar que el panel funciona como
producto, no solo que compila.

Pendientes:

- tests backend enfocados:
  - visualizacion temporal;
  - comparacion run-to-failure;
  - agentes con perfil temporal;
  - evidence lookup temporal;
- build frontend;
- validacion manual con backend/frontend levantados;
- capturas o checklist visual en desktop y mobile;
- comprobar que no hay solapes de texto;
- comprobar que las advertencias de proxy/RUL se ven;
- si Docker esta disponible, rebuild y smoke backend/frontend.

Criterio de aceptacion:

- la demo local puede recorrerse de principio a fin sin explicar manualmente
  que pantalla debe mirar el usuario.

## Orden propuesto de implementacion

### Paso 9.1: retocar el panel frontend run-to-failure

Prioridad maxima. Es el siguiente paso logico porque el backend ya tiene
suficiente informacion para mostrar una experiencia mucho mas clara.

Entregable:

- visualizacion temporal perfil-aware;
- cabecera operacional de salud/riesgo;
- bandas y leyenda de estados;
- advertencias claras de proxy/RUL;
- responsive revisado.

Estado 2026-06-03:

- implementado el primer bloque en
  `codigo/docs/70_fase7_hito9_panel_control_run_to_failure.md`;
- completado: metricas temporales primarias, metricas binarias auxiliares,
  cabecera de perfil/modelo, estado del motor, tira de ventanas, bandas de
  estado sobre la curva tecnica y PCA como diagnostico secundario;
- completado despues: separacion entre `primer pico` y `aviso sostenido`,
  mostrando picos aislados, episodios, racha maxima y aclaracion de que el fallo
  procede del replay historico cuando existe;
- pendiente dentro del cierre: cola global de activos/runs e interpretacion
  agentica operacional visible como tarjeta propia.

### Paso 9.2: resumen global y cola de activos/runs

Entregable:

- listado filtrable por perfil y estado;
- priorizacion de `warning` y `critical`;
- acceso rapido al detalle temporal.

### Paso 9.3: comparacion visual de modelos

Entregable:

- small multiples temporales;
- ranking por metricas de degradacion;
- tabla comparativa perfil-aware.

### Paso 9.4: interpretacion agentica operacional

Entregable:

- herramienta o extension de `evidence_lookup` para salud temporal;
- tarjeta de recomendacion Qwen/LLM;
- auditoria de que el agente usa evidencia temporal.

### Paso 9.5: suite canonica de runs

Entregable:

- ejecuciones comparables de modelos soportados;
- comparacion persistida;
- informe/verificacion del conjunto.

### Paso 9.6: frontera RUL experimental

Entregable:

- contrato opcional de RUL;
- UI que distingue no soportado, replay historico y experimental;
- decision documentada de si se implementa un baseline RUL ahora o se difiere.

### Paso 9.7: cierre de base

Entregable:

- checklist de aceptacion;
- pruebas enfocadas;
- build frontend;
- memoria actualizada;
- documento de cierre operativo del perfil.

## Fuera de alcance de este cierre

- autenticacion multiusuario;
- despliegue cloud;
- SLURM;
- streaming industrial en tiempo real;
- integracion con SCADA, CMMS o historizadores;
- gestion multi-tenant;
- entrenamiento profundo pesado como requisito obligatorio;
- RUL industrial validado si no hay suficientes trayectorias y protocolo de
  validacion.

## Criterio final de cierre

La base del perfil `run_to_failure_degradation` quedara cerrada cuando se pueda
hacer esta demo local:

1. Seleccionar o inspeccionar un dataset temporal run-to-failure.
2. Ejecutar una run con `use_llm=true` y Qwen/Ollama.
3. Ver el activo en estado nominal/watch/warning/critical con curva temporal.
4. Entender si hubo deteccion antes de fallo y cuantas falsas alarmas hubo.
5. Comparar al menos tres modelos por metricas temporales.
6. Ver una recomendacion agentica con evidencia citada.
7. Leer un informe final agentico verificado.
8. Confirmar que la app no confunde proxy labels con etiquetas oficiales ni
   deteccion temprana con RUL real.

Cuando eso funcione, la base del perfil estara preparada. A partir de ahi,
las siguientes fases podran centrarse en SaaS industrial, despliegue,
streaming, usuarios, integraciones y validacion con datasets reales mas
amplios.

## Transicion a Fase 8

Decision 2026-06-03:

- la prioridad pasa a ser adaptar el perfil `run_to_failure_degradation` a una
  ejecucion agentica profunda;
- la hoja de ruta queda definida en
  `codigo/docs/71_fase8_hoja_ruta_agentica_run_to_failure.md`;
- histeresis avanzada, RUL experimental y autoencoders quedan diferidos hasta
  que los agentes tengan herramientas, contratos, debate y memoria suficientes
  para protagonizar el perfil.
