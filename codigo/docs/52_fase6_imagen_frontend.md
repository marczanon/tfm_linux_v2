# Imagen frontend Fase 6

Fecha: 2026-05-31.

## Objetivo

Preparar una imagen Docker reproducible para servir el dashboard web del TFM
Pipeline sin convertir el contenedor en un servidor de desarrollo ni cambiar
los contratos TypeScript ya existentes.

## Inventario previo

Busquedas realizadas:

```text
rg -n "Hito 4|frontend|compose|nginx|Dockerfile|docker" codigo/docs codigo/docker codigo/frontend -g '!codigo/frontend/node_modules'
rg --files -g "Dockerfile*" -g "*nginx*" -g "*compose*" -g "*.template" -g ".dockerignore" codigo/docker codigo/frontend .
```

Piezas encontradas:

- `codigo/frontend/package.json` ya define `npm run build`.
- `codigo/frontend/src/api.ts` usa `VITE_API_BASE_URL`, con `/api` como valor
  por defecto.
- `codigo/frontend/vite.config.ts` mantiene proxy de desarrollo para el modo
  local.
- No existia imagen frontend ni configuracion Nginx previa.

Decision: `new`.

Motivo: no habia propietario Docker para servir el frontend compilado. La nueva
pieza se limita a empaquetar el build existente y a resolver el proxy `/api`
hacia el backend, sin duplicar contratos ni logica de aplicacion.

Impacto en compatibilidad: el desarrollo local con Vite no cambia. La imagen
usa el mismo `npm run build` y mantiene `/api` como frontera del navegador.

## Implementacion

Archivos creados:

- `codigo/docker/frontend.Dockerfile`;
- `codigo/docker/frontend.nginx.conf.template`.

La imagen usa dos etapas:

1. `node:22-alpine` instala dependencias con `npm ci` y ejecuta
   `npm run build`.
2. `nginx:1.27-alpine` sirve los artefactos generados en `dist/`.

Variables principales:

```text
VITE_API_BASE_URL=/api
TFM_FRONTEND_PORT=5173
TFM_BACKEND_URL=http://backend:8010
```

El contenedor expone `5173` y anade un healthcheck contra `/healthz`.

El proxy Nginx traduce:

```text
/api/health -> ${TFM_BACKEND_URL}/health
```

De este modo, el navegador no necesita conocer rutas internas ni puertos del
backend. En compose, `TFM_BACKEND_URL` apuntara al servicio `backend`. En una
prueba manual puede apuntar al backend local mediante
`http://host.docker.internal:8010`.

## Comandos previstos

Build:

```text
docker build -f codigo/docker/frontend.Dockerfile -t tfm-frontend:fase6-hito4 .
```

Run manual contra backend local:

```text
docker run --rm \
  --name tfm-frontend-fase6 \
  --add-host=host.docker.internal:host-gateway \
  -e TFM_BACKEND_URL=http://host.docker.internal:8010 \
  -p 5173:5173 \
  tfm-frontend:fase6-hito4
```

Si `5173` ya esta ocupado por Vite, se puede publicar el contenedor en otro
puerto del host sin cambiar la aplicacion:

```text
-p 5174:5173
```

## Verificacion realizada

Build local:

```text
npm run build
```

Resultado: correcto.

Build Docker:

```text
docker build -f codigo/docker/frontend.Dockerfile -t tfm-frontend:fase6-hito4 .
```

Resultado: imagen construida correctamente.

```text
tfm-frontend:fase6-hito4
```

Como `5173` puede estar ocupado por el servidor Vite de desarrollo, la prueba
manual se publico en `5174:5173`, apuntando al backend local ya activo en
`8010`:

```text
docker run --rm -d \
  --name tfm-frontend-fase6-hito4-test \
  --add-host=host.docker.internal:host-gateway \
  -e TFM_BACKEND_URL=http://host.docker.internal:8010 \
  -p 5174:5173 \
  tfm-frontend:fase6-hito4
```

Smoke ejecutado:

```text
curl -sS http://127.0.0.1:5174/healthz
curl -sS http://127.0.0.1:5174/
curl -sS http://127.0.0.1:5174/api/health
curl -sS http://127.0.0.1:5174/api/datasets/adapters
```

Resultados:

- `/healthz` devuelve `ok`;
- `/` devuelve el HTML compilado del dashboard;
- `/api/health` responde a traves del proxy Nginx;
- `/api/datasets/adapters` lista CWRU, NASA IMS y generic tabular;
- el healthcheck Docker marca el contenedor como `healthy`;
- el contenedor de prueba se detiene tras la validacion.

## Siguiente paso

Hito 5: crear un `docker-compose.yml` local que levante backend y frontend con
un comando reproducible, montando datos, reports, modelos y experimentos como
volumenes y manteniendo Ollama externo.
