# Cierre operativo Fase 6

Fecha: 2026-05-31.

## Decision

La Fase 6 queda cerrada operativamente en el Hito 5.

Motivo: ya existe el minimo necesario para reproducir la aplicacion con Docker:

- imagen backend FastAPI;
- imagen frontend estatica con Nginx;
- `docker-compose.yml` local para levantar backend y frontend;
- volumenes persistentes para datos, reports, modelos y experimentos;
- Ollama/Qwen documentado como dependencia externa;
- validacion manual de backend, frontend, proxy `/api` y estado LLM.

Los hitos de pruebas de humo automatizadas y demo final quedan diferidos hasta
que la aplicacion vuelva a evolucionar funcionalmente. Automatizarlos ahora
generaria trabajo sobre una superficie que se va a seguir puliendo.

## Resultado alcanzado

El stack dockerizado minimo se levanta con:

```text
docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml up --build
```

El compose:

- construye `tfm-backend:fase6`;
- construye `tfm-frontend:fase6`;
- monta `codigo/data`, `codigo/reports`, `codigo/models` y
  `codigo/experiments`;
- mantiene Ollama externo en `host.docker.internal:11434`;
- expone backend y frontend mediante los puertos configurados en
  `codigo/docker/.env.example`;
- permite cambiar puertos del host sin alterar los puertos internos.

## Validacion realizada

La validacion del Hito 5 se ejecuto con puertos alternativos para no interferir
con la API local:

```text
TFM_API_PORT=8016 TFM_FRONTEND_PORT=5175 docker compose --env-file codigo/docker/.env.example -f codigo/docker/docker-compose.yml -p tfm-fase6-hito5 up --build -d
```

Comprobaciones superadas:

- backend `healthy`;
- frontend `healthy`;
- `GET /health` desde backend dockerizado;
- `GET /llm/status` con Ollama externo y `qwen3.5:4b`;
- `/healthz` desde frontend dockerizado;
- `/` sirve el dashboard compilado;
- `/api/health` funciona mediante proxy Nginx;
- `/api/datasets/adapters` funciona mediante proxy Nginx.

Tras la validacion, el stack de prueba se detuvo con `docker compose down`.

## Hitos diferidos

Quedan fuera del cierre operativo actual:

- script de smoke test automatico;
- prueba automatica frontend/proxy;
- dry-run CWRU automatizado desde script;
- secuencia final de demo con evidencia cerrada.

Estos elementos se retomaran cuando la aplicacion haya recibido el siguiente
bloque de mejoras funcionales, para que las pruebas reflejen la version que se
quiera defender finalmente.

## Siguiente bloque de trabajo

El siguiente trabajo no debe ser mas infraestructura Docker salvo necesidad
concreta. La prioridad vuelve a ser la aplicacion:

- hacer la web mas funcional y completa;
- pulir flujos pendientes;
- mejorar UX/UI y estados;
- ampliar capacidades de ejecucion y consulta;
- revisar fronteras entre frontend, backend, agentes, memoria y artefactos;
- mantener contratos estrictos y ejecutores deterministas;
- trasladar cada cambio al stack Docker mediante rebuild y smoke manual.

La metodologia se mantiene:

1. identificar la capacidad que se quiere anadir;
2. buscar propietarios existentes antes de crear codigo nuevo;
3. reutilizar o extender contratos existentes siempre que sea posible;
4. actualizar documentacion y memoria en paralelo;
5. verificar primero en modo local rapido;
6. reconstruir y validar Docker cuando el cambio afecte a backend, frontend,
   dependencias, variables o artefactos.

## Referencias

- `codigo/docs/48_hoja_ruta_fase_6_dockerizacion.md`;
- `codigo/docs/49_fase6_supuestos_entorno.md`;
- `codigo/docs/50_fase6_configuracion_reproducible.md`;
- `codigo/docs/51_fase6_imagen_backend.md`;
- `codigo/docs/52_fase6_imagen_frontend.md`;
- `codigo/docs/53_fase6_compose_local.md`.
