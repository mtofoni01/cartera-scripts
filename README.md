# cartera-scripts

Servicio Python para el sistema de cartera de inversiones.

## Variables de entorno en Railway

| Variable | Descripción |
|----------|-------------|
| API_URL | URL del backend Node.js |
| DOLAR_TIPO | blue / bolsa / contadoconliqui / oficial |
| SCRIPT_API_KEY | Clave secreta para proteger el endpoint /run |
| PORT | Lo asigna Railway automáticamente |

## Endpoints

- GET /health — verificar que el servicio está vivo
- POST /run — ejecutar el script de cierres
  - Header: x-api-key: tu_clave_secreta
