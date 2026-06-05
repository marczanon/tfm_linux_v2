# Investigación de referencia: perfil run-to-failure para anomalía, degradación y RUL

Fecha de revisión: 2026-06-04

Este documento recopila información útil para un perfil de proyecto centrado en datos run-to-failure, detección de anomalías, inicio de degradación, construcción de indicadores de salud, predicción de vida útil restante y visualización humana. No contiene propuestas de implementación ni instrucciones de desarrollo. Su objetivo es servir como documento de lectura y contexto técnico-producto.

---

## 1. Resumen ejecutivo

Los datasets run-to-failure son una de las bases más importantes para sistemas de mantenimiento predictivo porque contienen trayectorias completas desde una fase nominal o aparentemente sana hasta un evento de fallo. La idea central no es solo predecir un número de vida útil restante, sino reconstruir una historia comprensible del activo: cuándo funcionaba normal, cuándo empezó a separarse de su comportamiento sano, cuándo la degradación se volvió sostenida, cuánto tiempo puede quedar y qué nivel de confianza tiene esa estimación.

La literatura reciente converge en una arquitectura conceptual de tres capas: preparación de datos, generación de indicadores de salud y predicción de RUL. Una revisión de 2024 sobre RUL con deep learning describe precisamente esa estructura general: preprocesamiento, health indicator generation y RUL prediction. También señala que los health indicators son uno de los factores más críticos para la fiabilidad del pronóstico, que los modelos profundos siguen teniendo problemas de interpretabilidad y que los benchmarks comparables siguen siendo necesarios para juzgar correctamente los avances.

En rodamientos, los datasets más relevantes para este perfil son NASA IMS, PRONOSTIA/FEMTO-ST/IEEE PHM 2012 y XJTU-SY. En turbofanes, los benchmarks clave son NASA C-MAPSS y N-CMAPSS. Cada uno aporta algo distinto: IMS es muy útil para detección y análisis de señales, PRONOSTIA para RUL en condiciones aceleradas con scoring asimétrico, XJTU-SY para aprendizaje entre condiciones y comparación de múltiples trayectorias, C-MAPSS para series multivariantes de motores y N-CMAPSS para escenarios más realistas con condiciones de vuelo reales, clases de salud/fallo y datos en HDF5.

El state of the art de 2024-2025 no se limita a LSTM o CNN. Destacan enfoques con división adaptativa de etapas de degradación, TCN y Transformer, atención temporal, autoencoders y VAE entrenados con datos sanos, indicadores de salud aprendidos de forma no supervisada y modelos probabilísticos con incertidumbre. La tendencia práctica más importante es separar tres problemas que a menudo se mezclan: detección de anomalía, detección del inicio de degradación y predicción de RUL. Una anomalía aislada no implica degradación confirmada, y una degradación confirmada no implica necesariamente una predicción de RUL estable si la evolución aún no muestra una tendencia clara.

Para visualización humana, la salida más útil no es una gráfica de vibración cruda. La representación más clara es una línea de vida del activo con estados como sano, vigilar, degradación confirmada, crítico y fallo. Debajo de esa línea de vida pueden aparecer evidencias traducidas a lenguaje normal: la vibración tiene más energía de lo habitual, aparecen golpes repetitivos, el cambio se mantiene durante varias mediciones o la salud baja más rápido que antes. La predicción de RUL conviene expresarla como una previsión con incertidumbre, parecida a una previsión meteorológica: escenario conservador, escenario probable y escenario optimista.

---

## 2. Conceptos base

### Run-to-failure

Un dataset run-to-failure contiene una trayectoria temporal hasta el final de vida de un activo o componente. La trayectoria puede venir de laboratorio, de simulación o de operación real/sintética. Su valor está en que permite estudiar la evolución completa de la degradación, no solo snapshots de fallo o no fallo.

La NASA Prognostics Data Repository se define como una colección de datasets destinados al desarrollo de algoritmos de prognostics. NASA indica que muchos de estos datos son series temporales desde un estado nominal previo hasta un estado fallado.

### RUL

RUL significa Remaining Useful Life, o vida útil restante. Es el tiempo, número de ciclos, número de vuelos o número de muestras que se estima que quedan hasta un evento de fallo o fin de vida. En la práctica, el RUL no debería entenderse como un único número exacto, sino como una distribución o rango razonable.

### Health Index

Un Health Index es una variable sintética que intenta resumir el estado de salud del activo. Puede presentarse como salud 100 a 0, donde 100 representa un estado sano y 0 representa el fallo o fin de vida. En la investigación se suele hablar de indicadores con propiedades como monotonicidad, robustez, correlación con la degradación, trendability y prognosability.

Un buen Health Index no es necesariamente el que mejor detecta el fallo final, sino el que permite observar de forma estable y temprana la evolución desde sano hasta degradado.

### Detección de anomalía

La detección de anomalía responde a la pregunta: “¿esto se parece a lo que el sistema hacía cuando estaba sano?”. Puede estar basada en umbrales robustos, distancia respecto a una línea base, cambios estadísticos, modelos HMM o errores de reconstrucción de autoencoders.

La detección de anomalía no debe confundirse con diagnóstico ni con RUL. Una anomalía puede ser ruido, un cambio de condición operativa, una medición defectuosa o una degradación incipiente.

### Inicio de degradación

El inicio de degradación es el punto temporal a partir del cual los cambios dejan de parecer ruido aislado y se convierten en una tendencia sostenida. Este punto es especialmente difícil en rodamientos porque la degradación puede ser lenta, abrupta, ruidosa o no monótona.

Algunos trabajos recientes tratan explícitamente este problema. AD-LTAN, por ejemplo, introduce división adaptativa de etapas para detectar el punto de inicio de degradación y después predecir RUL con atención temporal larga.

### Prognostics frente a diagnostics

Diagnostics intenta identificar qué está fallando o qué componente está afectado. Prognostics intenta estimar cuánto queda antes del fallo. NASA N-CMAPSS es interesante porque no solo incluye RUL, sino también información de clase de salud/fallo, lo que lo hace útil para formular problemas de prognostics y diagnostics.

---

## 3. Datasets de referencia

### 3.1 NASA IMS Bearings

NASA IMS Bearings es un dataset de rodamientos publicado en NASA Open Data y enlazado desde el repositorio de prognostics de NASA. NASA indica que los datos fueron proporcionados por el Center for Intelligent Maintenance Systems de la University of Cincinnati.

Descripción técnica frecuente en la literatura: cuatro rodamientos de doble fila montados en un mismo eje, velocidad constante de 2000 RPM, carga radial de 6000 lb, lubricación forzada y adquisición de vibración mediante acelerómetros. Los datos se registran como snapshots de un segundo, con 20.480 puntos por muestra y una frecuencia de muestreo de 20 kHz o 20,48 kHz según la interpretación usada por diferentes estudios. Un trabajo de PHM Society resume tres experimentos test-to-failure: T1 con 2156 muestras y fallos en B3 y B4, T2 con 984 muestras y fallo en B1, y T3 con 6324 muestras en su tabla, aunque advierte que el número de muestras de T3 puede diferir de otros benchmarks y del README original.

Fortalezas para un perfil run-to-failure:

- Muy útil para detección de anomalías y construcción de indicadores de salud.
- Contiene señales de vibración reales con ruido, acoplamiento entre rodamientos y fallos que no siempre son triviales de aislar.
- Es un dataset clásico para comparar técnicas de señal: RMS, kurtosis, STFT, PSD, squared envelope spectrum, cyclic spectral coherence, wavelets, cepstrum pre-whitening y métodos HMM.

Limitaciones:

- Pocas trayectorias completas para modelos profundos grandes.
- Diferencias entre experimentos: número de canales, duración, fallos y continuidad temporal.
- Riesgo de overfitting si se usan ventanas aleatorias en lugar de separar por run/activo.
- No siempre es ideal para RUL supervisado de alta capacidad porque el número de fallos completos es bajo.

Uso conceptual más adecuado:

- Detección temprana de anomalías.
- Evaluación de indicadores de salud interpretables.
- Explicación de evidencias vibracionales.
- Comparación entre métodos clásicos de señal y métodos data-driven.

### 3.2 PRONOSTIA / FEMTO-ST / IEEE PHM 2012

PRONOSTIA es una plataforma experimental de FEMTO-ST para degradación acelerada de rodamientos. El artículo original de Nectoux et al. describe que la plataforma permite probar y validar métodos de health assessment, diagnóstico y pronóstico. Usa sensores de velocidad, fuerza, temperatura y vibración; la vibración se adquiere en dos direcciones mediante acelerómetros horizontal y vertical. El paper indica una frecuencia de muestreo de aceleración de 25,6 kHz y temperatura a 10 Hz.

El IEEE PHM 2012 Prognostic Challenge se construyó sobre esta plataforma. Incluyó tres condiciones operativas: 1800 RPM y 4000 N, 1650 RPM y 4200 N, y 1500 RPM y 5000 N. El reto proporcionó seis trayectorias run-to-failure para entrenamiento y once rodamientos truncados para estimar RUL. El paper señala que la vida de los rodamientos era muy variable, de una a siete horas, y que no se daba ninguna hipótesis previa sobre el tipo de fallo.

Un rasgo clave del challenge es su scoring asimétrico: las predicciones tardías, es decir, aquellas que sobreestiman el RUL real, reciben una penalización más severa que las predicciones tempranas. Esto representa bien una lógica de mantenimiento: parar demasiado pronto puede tener coste, pero llegar tarde puede ser peligroso o muy caro.

Fortalezas para un perfil run-to-failure:

- Benchmark clásico para RUL de rodamientos.
- Incluye condiciones operativas distintas.
- Permite estudiar predicción sobre trayectorias truncadas, no solo sobre trayectorias completas conocidas.
- Su scoring asimétrico es útil para traducir predicción en decisión de mantenimiento.

Limitaciones:

- Dataset pequeño: seis runs completos de entrenamiento y once test truncados en el challenge original.
- La degradación puede ser abrupta o muy ruidosa.
- El propio paper advierte que los modelos teóricos de vida o las frecuencias características de fallo no encajan siempre bien, porque la degradación puede afectar simultáneamente a varios componentes del rodamiento.
- Las vidas tienen gran dispersión, por lo que una métrica de error simple puede ocultar comportamientos malos en ciertos casos.

Uso conceptual más adecuado:

- RUL bajo incertidumbre.
- Evaluación de scoring asimétrico.
- Análisis de inicio de degradación.
- Visualización de trayectorias truncadas y evolución de confianza.

### 3.3 XJTU-SY Bearing Dataset

XJTU-SY es un dataset de rodamientos proporcionado por el Institute of Design Science and Basic Component de Xi’an Jiaotong University y Changxing Sumyoung Technology. La página oficial del dataset indica que contiene datos completos run-to-failure de 15 rodamientos obtenidos mediante experimentos de degradación acelerada.

Los experimentos se organizan en tres condiciones operativas, con cinco rodamientos por condición: 2100 RPM y 12 kN, 2250 RPM y 11 kN, y 2400 RPM y 10 kN. La señal se adquiere con dos acelerómetros PCB 352C33 colocados a 90 grados en la carcasa del rodamiento, uno en eje horizontal y otro en eje vertical. La frecuencia de muestreo es 25,6 kHz, con 32.768 puntos por muestra, 1,28 segundos por adquisición y un intervalo de muestreo de un minuto. Cada adquisición se guarda en CSV con la primera columna para vibración horizontal y la segunda para vibración vertical. La página también indica fallos de distintos tipos, como desgaste de pista interior, fractura de jaula, desgaste de pista exterior y fractura de pista exterior.

Fortalezas para un perfil run-to-failure:

- Más trayectorias completas que PRONOSTIA.
- Buen candidato para comparar generalización entre condiciones.
- Alta frecuencia de muestreo y dos direcciones de vibración.
- Etiquetas o descripción de elementos fallados útiles para diagnóstico posterior.

Limitaciones:

- Sigue siendo un entorno de laboratorio con degradación acelerada.
- Las condiciones son fijas por experimento, no condiciones altamente variables dentro de un mismo run.
- La cantidad de trayectorias es mayor que en PRONOSTIA, pero aún limitada para modelos profundos grandes si se quiere validar generalización estricta.

Uso conceptual más adecuado:

- Entrenamiento y validación de modelos de RUL en rodamientos.
- Cross-condition learning.
- Transfer learning y adaptación de dominio.
- Comparación entre indicadores de salud transparentes y aprendidos.

### 3.4 NASA C-MAPSS Turbofan

NASA C-MAPSS es el benchmark clásico de turbofan degradation. NASA Open Data lo describe como datasets de múltiples series temporales multivariantes, divididos en training y test. Cada serie temporal representa un motor de una flota. Los motores empiezan con variación inicial normal no considerada fallo. Hay tres operational settings que afectan al rendimiento y los datos contienen ruido de sensores. En el train, la serie llega hasta fallo; en el test, la serie se corta antes del fallo y el objetivo es predecir el número de ciclos operativos restantes.

Fortalezas para un perfil run-to-failure:

- Benchmark de RUL multivariante muy usado.
- Útil para separar el sistema de rodamientos del sistema general de prognostics.
- Permite probar visualización de flota y RUL por ciclo.
- Permite estudiar normalización por condiciones operativas.

Limitaciones:

- Es simulado.
- El C-MAPSS original tiene una representación más simplificada de condiciones de vuelo que N-CMAPSS.
- Muchos resultados publicados dependen de detalles de preprocesamiento, clipping de RUL y splits, por lo que la comparación no siempre es directa.

Uso conceptual más adecuado:

- Validación de arquitectura general para RUL multivariante.
- Diseño de vistas de flota.
- Evaluación de métricas de RUL por ciclo.
- Comparación entre modelos clásicos y profundos.

### 3.5 NASA N-CMAPSS

N-CMAPSS amplía el enfoque de C-MAPSS con mayor fidelidad. El artículo de Arias Chao et al., enlazado desde NASA NTRS y publicado en Data, indica que el dataset se generó con el modelo C-MAPSS de NASA, incorporando dos mejoras principales: condiciones reales de vuelo registradas a bordo de un avión comercial y degradación relacionada con el historial operativo. Además, proporciona clase de salud y clase de fallo, lo que permite estudiar tanto prognostics como diagnostics.

El paper describe N-CMAPSS como trayectorias sintéticas run-to-failure de una flota de motores con estados iniciales desconocidos y condiciones reales de vuelo. Contiene ocho conjuntos de datos, 128 unidades y siete modos de fallo que afectan flujo o eficiencia de subcomponentes rotativos. Los datos están en archivos HDF5. Cada archivo contiene conjuntos development y test, con variables de condiciones operativas, señales medidas, sensores virtuales, parámetros de salud del motor, etiqueta de RUL y datos auxiliares como número de unidad, ciclo de vuelo, clase de vuelo y estado de salud. El RUL se expresa en ciclos.

Fortalezas para un perfil run-to-failure:

- Más realista que C-MAPSS para estudiar condiciones operativas variables.
- Permite combinar diagnóstico, estado de salud y RUL.
- Útil para modelos condition-aware, physics-informed y probabilísticos.
- Más adecuado para agentes avanzados que necesitan contexto operacional y variables auxiliares.

Limitaciones:

- Sintético, aunque con condiciones de vuelo reales.
- Mayor tamaño y complejidad de almacenamiento.
- Requiere cuidado especial en eficiencia, preparación de datos y visualización.

Uso conceptual más adecuado:

- Perfil avanzado de prognostics y diagnostics.
- Modelos con condiciones operativas reales.
- Curvas de supervivencia o probabilidad de fallo por horizonte.
- Comparación entre estado de salud, clase de fallo y RUL.

---

## 4. Comparativa de datasets

| Dataset | Dominio | Tipo de dato principal | Trayectorias completas | Mejor uso conceptual | Riesgo principal |
|---|---|---:|---:|---|---|
| NASA IMS Bearings | Rodamientos | Vibración | Sí, pocas | Anomalía, HI, señal interpretable | Pocas trayectorias y cambios entre experimentos |
| PRONOSTIA / FEMTO-ST | Rodamientos | Vibración y temperatura | Sí, más test truncado | RUL, scoring asimétrico, onset | Dataset pequeño y degradaciones abruptas |
| XJTU-SY | Rodamientos | Vibración horizontal y vertical | 15 | RUL, generalización entre condiciones | Laboratorio acelerado y tamaño aún limitado |
| NASA C-MAPSS | Turbofan | Sensores multivariantes simulados | Train completo, test truncado | RUL multivariante y flota | Simulación simplificada |
| NASA N-CMAPSS | Turbofan | Multivariante HDF5, condiciones reales de vuelo simuladas | Sí | Prognostics + diagnostics, modelos condition-aware | Complejidad y coste de procesamiento |

---

## 5. State of the art 2024-2025

### 5.1 Tendencias generales

La revisión de 2024 sobre deep-learning-based RUL prediction identifica un marco común formado por preprocesamiento, generación de health indicators y predicción de RUL. También subraya retos que encajan directamente con un perfil run-to-failure: dificultad de comparar modelos en benchmarks homogéneos, dependencia del tamaño de los datasets, necesidad de mejores health indicators, problemas de caja negra, incertidumbre en RUL y coste computacional.

La dirección práctica que se repite en la literatura reciente es híbrida. Los modelos más útiles no abandonan por completo la ingeniería de señal ni se basan únicamente en redes profundas. Suelen combinar transformaciones de vibración o health indicators con modelos temporales capaces de capturar dependencias largas.

Los enfoques actuales se agrupan en varias familias:

- Modelos basados en features e HI: extraen indicadores de tiempo, frecuencia y tiempo-frecuencia, y después predicen RUL con modelos estadísticos o de machine learning.
- Modelos end-to-end: usan señal cruda o representaciones espectrales como entrada y aprenden directamente RUL.
- Modelos stage-aware: separan fases de vida y detectan el punto de inicio de degradación antes de estimar RUL.
- Modelos no supervisados: aprenden el estado sano y usan desviación o error de reconstrucción como score de anomalía o Health Index.
- Modelos probabilísticos: devuelven intervalos, cuantiles, distribución de fallo o probabilidad de supervivencia.
- Modelos híbridos: combinan conocimiento físico, señal clásica, aprendizaje profundo y reglas de decisión.

### 5.2 División adaptativa de etapas

AD-LTAN, publicado en 2024, es relevante porque ataca dos problemas muy frecuentes en rodamientos: la variabilidad del punto de inicio de degradación y la pérdida de memoria de los modelos ante ciclos de vida largos. El enfoque divide la vida del rodamiento en etapas de salud y utiliza una red de atención temporal larga para retener características de degradación a largo plazo. El trabajo se evalúa en PHM2012 y XJTU-SY.

La lectura conceptual es clara: no conviene tratar toda la vida del activo como una única regresión homogénea. La fase sana, la fase de transición y la fase degradada tienen distribuciones distintas y pueden necesitar modelos o criterios distintos.

### 5.3 TCN y Transformer

Un trabajo de 2025 propone TCN–Transformer para RUL de rodamientos. El razonamiento del modelo es interesante: la TCN captura rasgos locales y el Transformer captura relaciones globales en secuencias largas. La combinación se presenta como una respuesta a la dificultad de predecir RUL en series temporales largas de vibración.

Esta línea es coherente con la evolución general del campo: convoluciones para patrones locales, atención para contexto temporal amplio y fusión de escalas para evitar perder señales incipientes.

### 5.4 Convoluciones multi-escala, atención y señal cruda

MDSCT, publicado en 2024, representa la familia end-to-end. Usa señales de vibración crudas, convoluciones separables en profundidad, mecanismos de atención y un Transformer encoder para capturar rasgos locales sutiles y dependencias globales. Se valida en PHM2012 y XJTU-SY.

Su valor como referencia está en mostrar hacia dónde se mueven los modelos de alta capacidad. Su riesgo para producto está en la interpretabilidad: una predicción precisa no es suficiente si el sistema no explica qué cambió y por qué la alerta es creíble.

### 5.5 Autoencoders y aprendizaje no supervisado del estado sano

Una línea muy útil para anomalía temprana es entrenar modelos solo con datos sanos. El trabajo de 2025 sobre log-envelope spectrum y VAE propone usar el espectro de envolvente logarítmico como entrada, entrenar un VAE con datos sanos y usar el error de reconstrucción como Health Index. El paper destaca que busca simultáneamente detección temprana de fallos incipientes y una tendencia de degradación clara, monótona y robusta.

Esta familia es especialmente útil cuando no hay suficientes fallos etiquetados, que es exactamente la situación habitual fuera de laboratorio.

### 5.6 HMM e interpretabilidad

Aunque los modelos profundos dominan muchos benchmarks, los Hidden Markov Models siguen siendo relevantes por simplicidad, robustez e interpretabilidad. Un trabajo de PLOS One de 2024 sobre HMMs para health assessment y fault diagnosis de rodamientos destaca estas propiedades y combina HMM con procesamiento de señal, EEMD, espectros de envolvente de Hilbert y features multidominio.

La lectura para el perfil es que un HMM o modelo de estados puede ser útil como capa de explicación: sano, transición, degradado, crítico. Incluso si el RUL lo produce otro modelo, un modelo de estados ayuda a convertir señales técnicas en una narrativa humana.

### 5.7 Survival analysis y RUL probabilístico

La supervivencia estadística ofrece una forma natural de expresar incertidumbre: probabilidad de sobrevivir más allá de cierto horizonte, probabilidad de fallo dentro de una ventana, mediana de vida restante y bandas de confianza. Algunos trabajos recientes aplican survival analysis a RUL con datos censurados y detección de deterioro mediante divergencia KL entre distribuciones de lectura actual y una distribución de referencia sana.

La ventaja conceptual es que se adapta bien a comunicación humana: “probabilidad de aguantar los próximos N ciclos” suele ser más accionable que un número único de RUL.

---

## 6. Detección de anomalías y modelado de degradación

### 6.1 Separación de problemas

Un perfil sólido distingue entre:

| Pregunta humana | Problema técnico | Salida útil |
|---|---|---|
| ¿Está normal? | Detección de anomalía | Score de anomalía y estado sano/vigilar |
| ¿El cambio se mantiene? | Confirmación de degradación | Inicio de degradación y cambio de etapa |
| ¿Qué componente parece afectado? | Diagnóstico | Evidencias y posible modo de fallo |
| ¿Cuánto queda? | Prognostics/RUL | Rango de RUL con incertidumbre |
| ¿Qué decisión tomar? | Soporte a mantenimiento | Acción recomendada y nivel de riesgo |

El error habitual es saltar de “anomalía” a “fallo inminente”. La anomalía debe pasar por confirmación temporal y análisis de contexto.

### 6.2 Línea base sana

Muchos métodos asumen que el primer tramo de vida corresponde a operación sana o nominal. Esta suposición aparece a menudo en IMS, PRONOSTIA, XJTU-SY y C-MAPSS, aunque no siempre es perfecta. En aplicaciones reales, la línea base puede estar contaminada por rodaje inicial, variación de montaje, cambios de carga o sensores mal calibrados.

Una línea base útil no debería ser solo una media. Debe representar variabilidad normal por condición operativa. En turbofanes, esto implica normalizar por operating settings. En rodamientos, implica distinguir vibración normal, cambios por régimen y cambios por daño.

### 6.3 Métodos clásicos de anomalía

Los métodos clásicos siguen siendo valiosos porque son explicables:

- Umbrales robustos sobre RMS, kurtosis, crest factor, energía espectral o impulsividad.
- CUSUM, Page-Hinkley y detectores de cambio sostenido.
- Distancias estadísticas respecto a la distribución sana.
- Divergencia KL entre distribución actual y referencia sana.
- Modelos de estados como HMM.
- PCA o autoencoder para detectar desviaciones multivariantes.

La revisión aplicada al dataset IMS muestra que RMS, kurtosis y detectivity pueden detectar aparición de fallos, pero también que técnicas de señal como STFT, PSD, squared envelope spectrum, cyclic spectral coherence, cepstrum pre-whitening e improved envelope spectrum siguen aportando información esencial.

### 6.4 Métodos no supervisados

Autoencoders, variational autoencoders y modelos contrastivos son útiles cuando solo hay datos sanos. La idea es aprender cómo se ve lo normal y usar la dificultad de reconstrucción o la distancia en embedding como anomalía.

Ventajas:

- No requieren muchos fallos etiquetados.
- Pueden detectar cambios incipientes.
- Permiten convertir anomalía en Health Index.

Riesgos:

- Pueden confundir cambio de condición operativa con fallo.
- Pueden aprender anomalías si el tramo de entrenamiento sano está contaminado.
- Necesitan calibración para que el score sea comprensible.

### 6.5 Confirmación temporal

Una alerta aislada no es suficiente. En visualización humana, la confirmación debe depender de persistencia, tendencia y coherencia entre señales. Un estado “vigilar” puede representar una anomalía inicial; “degradación confirmada” debería requerir que el cambio se mantenga durante varias mediciones o que el Health Index muestre pendiente sostenida.

Esta idea encaja con los modelos stage-aware y con la necesidad de evitar alarmas falsas.

---

## 7. Health Indicators

### 7.1 Propiedades deseables

Un Health Index útil para prognostics debe cumplir varias propiedades:

| Propiedad | Significado práctico |
|---|---|
| Monotonicidad | La salud empeora de forma mayormente consistente cuando avanza la degradación |
| Robustez | El indicador no salta demasiado por ruido o mediciones aisladas |
| Trendability | Activos similares muestran tendencias comparables |
| Prognosability | El indicador permite estimar el tiempo hasta fallo con margen útil |
| Interpretabilidad | Una persona puede entender qué señales explican el cambio |
| Sensibilidad temprana | Detecta cambios incipientes antes de la fase crítica |

El estudio de IMS en Applied Sciences menciona correlación, monotonicidad y robustez como métricas habituales para evaluar parámetros estadísticos como health indexes, y define monotonicidad como continuidad de la tendencia creciente o decreciente en el tiempo y robustez como relación con el ruido que afecta a la señal.

### 7.2 Indicadores transparentes

Los indicadores transparentes combinan features de señal conocidas: energía, impulsividad, dispersión espectral y tendencia temporal. Son menos potentes que algunos modelos profundos, pero muy útiles para construir confianza.

Features frecuentes:

- Dominio temporal: RMS, desviación estándar, varianza, peak-to-peak, skewness, kurtosis, crest factor, impulse factor, clearance factor y shape factor.
- Dominio frecuencial: energía por bandas, frecuencia dominante, centroide espectral, entropía espectral y bandas alrededor de frecuencias características.
- Envolvente: envelope spectrum y squared envelope spectrum.
- Tiempo-frecuencia: STFT, wavelets, wavelet packet decomposition y scalograms.
- Técnicas avanzadas: spectral kurtosis, kurtogram, cyclic spectral coherence, cepstrum pre-whitening e improved envelope spectrum.

### 7.3 Indicadores aprendidos

Los indicadores aprendidos salen de autoencoders, VAEs, CNNs, contrastive learning o embeddings temporales. Son útiles cuando las relaciones son complejas o cuando hay demasiadas features para combinarlas manualmente.

La clave de producto es que el indicador aprendido debe ir acompañado de evidencias legibles. Un score abstracto de anomalía no basta. La interfaz debe poder explicar qué rasgos técnicos se movieron: más energía, más golpes, más periodicidad, mayor dispersión espectral, cambio de temperatura o aceleración de la tendencia.

### 7.4 Indicadores híbridos

Una opción equilibrada es un Health Index híbrido: una parte transparente basada en features físicas y una parte aprendida basada en reconstrucción o embedding. Esto permite combinar trazabilidad con sensibilidad.

---

## 8. Predicción de RUL

### 8.1 Familias de modelos

Los modelos de RUL pueden organizarse en cuatro grupos:

| Familia | Ejemplos | Ventaja | Riesgo |
|---|---|---|---|
| Estadísticos/model-based | Weibull, Gamma process, Wiener process, modelos exponenciales | Interpretables y probabilísticos | Pueden ser rígidos ante degradación no monótona |
| Machine learning clásico | SVR, Random Forest, Gradient Boosting, RVM | Buen rendimiento con pocos datos tabulares | Dependen mucho de features e ingeniería |
| Deep learning temporal | CNN, LSTM, GRU, TCN, Transformer, attention | Capturan patrones complejos | Riesgo de caja negra y sobreajuste |
| Híbridos/probabilísticos | Ensembles, survival, physics-informed, quantiles | Mejor incertidumbre y decisión | Más complejos de calibrar |

### 8.2 RUL como distribución

En mantenimiento, un RUL único puede ser engañoso. Es más útil una distribución:

- Escenario conservador: fallo antes de lo probable.
- Escenario probable: estimación central.
- Escenario optimista: fallo más tardío.
- Probabilidad de fallo dentro de una ventana concreta.
- Confianza de la predicción.

Este enfoque reduce falsas certezas y permite conectar el modelo con decisiones. En PHM 2012 y en el scoring NASA de C-MAPSS/N-CMAPSS, las predicciones que llegan tarde suelen penalizarse más que las tempranas porque el coste operativo no es simétrico.

### 8.3 RUL stage-aware

Una predicción de RUL durante fase sana puede ser poco informativa si aún no hay degradación clara. Por eso muchos sistemas prácticos separan:

- Fase sana: vigilancia y detección de anomalía.
- Fase de transición: confirmación y aumento de incertidumbre.
- Fase degradada: estimación de RUL más estable.
- Fase crítica: decisión de intervención.

AD-LTAN y otros modelos stage-aware refuerzan esta idea: detectar el inicio de degradación no es un detalle secundario, sino una parte central del pronóstico.

---

## 9. Métricas de evaluación

### 9.1 Métricas de detección de anomalía

Las métricas de anomalía deben valorar tanto la anticipación como la estabilidad:

- Lead time antes del fallo.
- Tasa de falsas alarmas.
- Tasa de detección antes de fallo.
- Tiempo hasta confirmar degradación.
- Número de cambios de estado espurios.
- Persistencia de la alerta.

Una detección extremadamente temprana pero inestable puede ser mala para operación. Una detección tardía con bajo ruido puede ser insuficiente para mantenimiento.

### 9.2 Métricas de Health Index

Las métricas relevantes son:

- Monotonicidad.
- Robustez frente a ruido.
- Correlación con tiempo, ciclo o degradación.
- Trendability entre activos comparables.
- Prognosability respecto al fallo.
- Separación entre sano, transición, degradado y crítico.

### 9.3 Métricas de RUL

Las métricas básicas son MAE y RMSE, pero no capturan por sí solas el valor operacional. NASA y la literatura PHM proponen métricas específicas como Prognostic Horizon, alpha-lambda performance, Relative Accuracy y Convergence. La NASA PrognosticsMetricsLibrary describe alpha-lambda como una métrica binaria de si la predicción cae dentro de un cono de precisión, Relative Accuracy como el error relativo frente al RUL real y Convergence como la velocidad con la que mejora una métrica conforme acumula información.

En C-MAPSS/N-CMAPSS también se usa la NASA scoring function, que penaliza de forma asimétrica la sobreestimación y la subestimación de RUL. En PHM 2012, la función de scoring también penaliza más las estimaciones tardías que las tempranas.

### 9.4 Métricas de incertidumbre

Cuando el RUL se expresa como distribución, aparecen métricas adicionales:

- Cobertura de intervalos: porcentaje de veces que el fallo real cae dentro del intervalo previsto.
- Anchura media del intervalo: indica si la predicción es informativa o demasiado amplia.
- Calibración: coherencia entre confianza declarada y frecuencia real de acierto.
- Error por cuantiles: útil para escenarios conservador, probable y optimista.

---

## 10. Visualización humana

### 10.1 Principio de diseño

La persona usuaria no debería tener que interpretar FFTs, espectrogramas o señales crudas para saber si debe actuar. La interfaz principal debe contestar en lenguaje claro:

- Estado actual.
- Salud estimada.
- Evolución desde la última lectura.
- Tiempo restante probable y rango de incertidumbre.
- Motivos principales.
- Acción sugerida.

La información técnica debe estar disponible en una capa experta, pero no ser el primer nivel de lectura.

### 10.2 Línea de vida del activo

Una línea de vida con estados discretos es más comprensible que una gráfica técnica:

Sano → Vigilar → Degradación confirmada → Crítico → Fallo

Marcadores útiles:

- Primera anomalía.
- Anomalía persistente.
- Inicio de degradación confirmado.
- Predicción de fallo más probable.
- Ventana recomendada de mantenimiento.
- Fallo real, si está disponible.

### 10.3 Tarjeta de salud

Una tarjeta humana puede resumir:

| Campo | Contenido |
|---|---|
| Estado | Sano, vigilar, degradación confirmada, crítico o fallo |
| Salud | Escala 100 a 0 |
| RUL probable | Estimación central |
| Rango razonable | Intervalo conservador-optimista |
| Confianza | Alta, media o baja |
| Cambio reciente | Estable, empeorando lentamente, empeorando rápido |
| Acción | Continuar, observar, inspeccionar, planificar o parar |

### 10.4 RUL como previsión meteorológica

La metáfora de meteorología ayuda a evitar falsa precisión:

| Escenario | Lectura humana |
|---|---|
| Conservador | Podría fallar pronto; decisión prudente |
| Probable | Punto central de la predicción |
| Optimista | Aguantaría más si la degradación no acelera |

Esta presentación hace más comprensible la incertidumbre que una única cifra decimal.

### 10.5 Traducción de evidencias técnicas

| Evidencia técnica | Traducción humana |
|---|---|
| Aumento de RMS | La vibración general tiene más energía de lo habitual |
| Aumento de kurtosis o crest factor | Aparecen golpes repentinos más marcados |
| Energía en bandas de envolvente | Hay un patrón repetitivo compatible con daño localizado |
| Pendiente negativa del Health Index | La salud está bajando de forma sostenida |
| Cambio persistente durante varias muestras | No parece una medición aislada |
| Intervalo de RUL muy ancho | La predicción todavía tiene incertidumbre alta |
| Temperatura sin cambio | No hay evidencia térmica relevante por ahora |

### 10.6 Vista de flota

Una vista de flota debe priorizar decisión:

| Activo | Estado | Salud | RUL probable | Riesgo | Acción |
|---|---:|---:|---:|---:|---|
| Rodamiento A | Sano | Alta | No aplica | Bajo | Continuar |
| Rodamiento B | Vigilar | Media-alta | No estable | Medio | Revisar tendencia |
| Rodamiento C | Degradación confirmada | Media-baja | Moderado | Alto | Planificar intervención |
| Rodamiento D | Crítico | Baja | Corto | Muy alto | Intervenir |

### 10.7 Capa experta

La capa experta puede incluir:

- Señal cruda.
- FFT.
- Espectro de envolvente.
- STFT o scalogram.
- Evolución de features.
- Health Index bruto y suavizado.
- Probabilidad de fallo por horizonte.
- Comparación contra línea base sana.

El orden de lectura importa: primero decisión, luego explicación, después evidencia técnica.

---

## 11. Agentes de IA como responsabilidades conceptuales

El perfil run-to-failure puede entenderse como un conjunto de responsabilidades especializadas. Esta sección no define implementación; solo organiza el conocimiento que un sistema de agentes podría manejar.

### Agente de dataset

Responsabilidad conceptual: conocer el origen, formato, sensores, unidades, condiciones operativas y estructura temporal de cada dataset. Debe diferenciar rodamientos y turbofanes, datos reales y simulados, train completo y test truncado, ciclos y tiempo real.

Información relevante:

- Dataset de origen.
- Activo o unidad.
- Run o trayectoria.
- Condición operativa.
- Frecuencia de muestreo.
- Canales disponibles.
- Unidad de tiempo o ciclos.
- Existencia de RUL verdadero.
- Punto de fallo o fin de vida.

### Agente de señal

Responsabilidad conceptual: transformar señales crudas en evidencias técnicas. Su conocimiento se centra en features de tiempo, frecuencia, envolvente, tiempo-frecuencia y estadísticas robustas.

Información relevante:

- Energía vibracional.
- Impulsividad.
- Bandas de frecuencia.
- Patrones repetitivos.
- Ruido y outliers.
- Diferencias entre canales horizontal y vertical.
- Cambios térmicos si hay temperatura.

### Agente de salud

Responsabilidad conceptual: convertir evidencias en un Health Index comprensible. Debe distinguir entre indicador bruto y tendencia suavizada, y mantener trazabilidad de qué señales explican el estado.

Información relevante:

- Salud actual.
- Tendencia.
- Monotonicidad.
- Robustez.
- Distancia respecto a baseline sano.
- Evidencias dominantes.

### Agente de detección de degradación

Responsabilidad conceptual: distinguir anomalía aislada, anomalía persistente e inicio de degradación. Este agente da sentido temporal a los cambios.

Información relevante:

- Primera anomalía.
- Persistencia del cambio.
- Cambio de pendiente del Health Index.
- Coherencia entre features.
- Posible cambio de condición operativa.

### Agente de RUL

Responsabilidad conceptual: estimar vida útil restante con incertidumbre. Su salida natural no es un punto exacto, sino una distribución o rango.

Información relevante:

- Escenario conservador.
- Escenario probable.
- Escenario optimista.
- Probabilidad de fallo en horizontes concretos.
- Confianza de la estimación.
- Evolución de la confianza conforme entran nuevas muestras.

### Agente de explicación

Responsabilidad conceptual: traducir técnica a lenguaje humano. Debe evitar jerga cuando la persona usuaria no la necesita.

Información relevante:

- Qué cambió.
- Desde cuándo cambió.
- Si el cambio es sostenido.
- Qué señales apoyan la conclusión.
- Qué señales no muestran cambios.
- Por qué la confianza es alta, media o baja.

### Agente de decisión

Responsabilidad conceptual: conectar estado, riesgo, RUL e incertidumbre con una decisión de mantenimiento. La lógica debe reconocer que llegar tarde suele ser más caro que planificar con margen.

Información relevante:

- Estado del activo.
- Severidad.
- Riesgo de fallo en ventana operativa.
- Coste de intervención temprana frente a fallo.
- Ventana recomendada.
- Prioridad frente a otros activos.

### Agente de evaluación

Responsabilidad conceptual: medir si el sistema funciona bien desde el punto de vista técnico y operativo.

Información relevante:

- Métricas de anomalía.
- Métricas de Health Index.
- Métricas de RUL.
- Métricas de incertidumbre.
- Métricas de decisión.
- Comparación por dataset y condición operativa.

---

## 12. Riesgos metodológicos

### Leakage temporal

El riesgo más grave en run-to-failure es mezclar ventanas del mismo activo entre train y test. Esto puede producir resultados artificialmente buenos porque el modelo ve partes de la misma trayectoria durante entrenamiento y evaluación. La evaluación fiable separa por activo, run o unidad.

### Normalización con futuro

Ajustar escaladores, PCA o umbrales usando toda la vida del activo contamina el pasado con información futura. La línea base y los normalizadores deben interpretarse como conocimiento disponible en el momento de la predicción.

### Overfitting a un benchmark

Muchos modelos funcionan bien en un dataset concreto y fallan al cambiar de condición operativa, sensor, carga o máquina. XJTU-SY ayuda a estudiar cross-condition, pero sigue siendo laboratorio. N-CMAPSS permite más complejidad operativa, pero sigue siendo sintético.

### Confundir ruido con degradación

Los datos de vibración pueden contener outliers, acoplamientos, resonancias, discontinuidades e interferencias. Una alerta útil debe separar pico aislado y cambio sostenido.

### Falta de incertidumbre

Un RUL sin incertidumbre puede inducir decisiones peligrosas. Un sistema que dice “quedan 73 minutos” sin rango ni confianza está comunicando más certeza de la que probablemente tiene.

### Interpretabilidad insuficiente

Los modelos end-to-end pueden tener buen RMSE y aun así ser difíciles de usar en mantenimiento si no explican las causas de la alerta. La evidencia humana es parte del producto, no un añadido secundario.

### Métrica equivocada

MAE o RMSE pueden ocultar errores operativamente graves. En mantenimiento predictivo, una predicción tardía puede ser mucho peor que una temprana. Por eso son importantes el scoring asimétrico, Prognostic Horizon, alpha-lambda, Relative Accuracy, Convergence y métricas de incertidumbre.

---

## 13. Lecturas clave por tema

### Datasets oficiales y documentación base

- NASA Prognostics Center of Excellence Data Set Repository: repositorio de datasets de prognostics, incluyendo bearings y turbofan.
- NASA Open Data IMS Bearings: ficha oficial del dataset IMS Bearings.
- PRONOSTIA: An Experimental Platform for Bearings Accelerated Degradation Tests: paper base de FEMTO-ST y del IEEE PHM 2012 Prognostic Challenge.
- XJTU-SY Bearing Datasets: página del autor Biao Wang con condiciones, muestreo y descarga.
- NASA Open Data C-MAPSS Jet Engine Simulated Data: ficha oficial del benchmark C-MAPSS.
- Aircraft Engine Run-to-Failure Dataset under Real Flight Conditions for Prognostics and Diagnostics: paper de N-CMAPSS.

### State of the art y modelos recientes

- Remaining Useful Life Prediction Based on Deep Learning: A Survey, 2024.
- Long-term temporal attention neural network with adaptive stage division for RUL prediction of rolling bearings, 2024.
- Remaining Useful Life Prediction for Rolling Bearings Based on TCN–Transformer Networks Using Vibration Signals, 2025.
- Remaining useful life prognostics of bearings based on convolution attention networks and enhanced transformer, 2024.
- An unsupervised approach to early fault detection and performance degradation assessment in bearings, 2025.
- Hidden Markov Models based intelligent health assessment and fault diagnosis of rolling element bearings, 2024.

### Señal, Health Index y evaluación

- A Comparison of Signal Analysis Techniques for the Diagnostics of the IMS Rolling Element Bearing Dataset, 2023.
- NASA PrognosticsMetricsLibrary.
- On Applying the Prognostic Performance Metrics, NASA NTRS.
- IEEE PHM 2012 scoring descrito en el paper de PRONOSTIA.

---

## 14. Conclusión conceptual

El perfil run-to-failure debería entenderse como una historia temporal del activo, no como una tarea aislada de regresión. El sistema más útil combina detección de anomalía, confirmación de degradación, Health Index interpretable, RUL con incertidumbre y explicación humana.

La dirección más sólida para este dominio no es elegir entre señal clásica o deep learning, sino combinar ambas. Las técnicas de señal aportan explicabilidad y robustez física; los modelos temporales modernos aportan capacidad para aprender patrones largos y no lineales; los modelos probabilísticos aportan incertidumbre; y una visualización centrada en estados convierte todo ello en decisión comprensible.

---

## 15. Fuentes

1. [NASA Prognostics Center of Excellence Data Set Repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/)
2. [NASA Open Data: IMS Bearings](https://data.nasa.gov/dataset/ims-bearings)
3. [Bearings Fault Detection Using Hidden Markov Models, PHM Society 2021](https://papers.phmsociety.org/index.php/phme/article/download/2947/1761)
4. [PRONOSTIA: An Experimental Platform for Bearings Accelerated Degradation Tests, FEMTO-ST](https://publiweb.femto-st.fr/tntnet/entries/1528/documents/author/data)
5. [XJTU-SY Bearing Datasets, Biao Wang](https://biaowang.tech/xjtu-sy-bearing-datasets/)
6. [A Hybrid Prognostics Approach for Estimating Remaining Useful Life of Rolling Element Bearings, IEEE Transactions on Reliability](https://scholar.xjtu.edu.cn/en/publications/a-hybrid-prognostics-approach-for-estimating-remaining-useful-lif/)
7. [NASA Open Data: C-MAPSS Jet Engine Simulated Data](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data)
8. [NASA NTRS: Aircraft Engine Run-to-Failure Dataset Under Real Flight Conditions for Prognostics and Diagnostics](https://ntrs.nasa.gov/citations/20210020068)
9. [N-CMAPSS paper in Data/MDPI](https://www.mdpi.com/2306-5729/6/1/5)
10. [NASA NTRS: On Applying the Prognostic Performance Metrics](https://ntrs.nasa.gov/citations/20100023445)
11. [NASA PrognosticsMetricsLibrary](https://github.com/nasa/PrognosticsMetricsLibrary)
12. [A Comparison of Signal Analysis Techniques for the Diagnostics of the IMS Rolling Element Bearing Dataset](https://www.mdpi.com/2076-3417/13/10/5977)
13. [Remaining Useful Life Prediction Based on Deep Learning: A Survey](https://www.mdpi.com/1424-8220/24/11/3454)
14. [Long-term temporal attention neural network with adaptive stage division for remaining useful life prediction of rolling bearings](https://www.sciencedirect.com/science/article/abs/pii/S0951832024002916)
15. [Remaining Useful Life Prediction for Rolling Bearings Based on TCN–Transformer Networks Using Vibration Signals](https://www.mdpi.com/1424-8220/25/11/3571)
16. [Remaining useful life prognostics of bearings based on convolution attention networks and enhanced transformer](https://www.sciencedirect.com/science/article/pii/S2405844024143484)
17. [An unsupervised approach to early fault detection and performance degradation assessment in bearings](https://www.sciencedirect.com/science/article/pii/S1474034625005130)
18. [Hidden Markov Models based intelligent health assessment and fault diagnosis of rolling element bearings](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0297513)
19. [A probabilistic estimation of remaining useful life from survival analysis](https://arxiv.org/html/2405.01614v1)
