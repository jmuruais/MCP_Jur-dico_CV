# MCP Jurídico Español — versión 1.1.0

## Alcance

Entorno de referencia: Debian 13, 1 CPU y 512 MiB de RAM. Servicio existente `tunnel-client.service`, transporte stdio. No hay APIs de modelos, buscadores de pago, OCR ni navegador instalado en el LXC. Se conservan el entorno Python y los identificadores y secretos del túnel. Dependencia de sistema ya instalada: `poppler-utils`.

La versión 1.1.0 incorpora búsqueda general DOGV y búsqueda puntual en la base pública CENDOJ filtrada al Tribunal Supremo. No mantiene una colección documental ni recorre páginas o descarga PDFs automáticamente.

## Corrección del diagnóstico anterior

El HTTP 440 observado en DOGV era un error de la petición o del servidor, no una prueba de bloqueo de acceso. La integración inicial no reproducía el contrato del frontend. Se han verificado idioma `es_es`/`es_ca`, ordenación `fechaDogvDesc`, páginas de 10 y fechas `dd-MM-yyyy`. El servidor puede fallar con tamaños como 3 por un error aritmético de paginación. La herramienta solicita la página estándar de 10 y devuelve solo los resultados pedidos.

CENDOJ recibe búsquedas mediante POST de formulario, después de inicializar una sesión pública normal. El GET que devolvió 403 no era el método del buscador. La versión nueva usa el POST publicado por el propio portal, sin credenciales, suplantación de clientes ni elusión de CAPTCHA. Un control interactivo real se devuelve como tal; no se resuelve automáticamente.

## Herramientas

Se conservan los 14 nombres existentes:

| Herramienta | Uso |
| --- | --- |
| `boe_metadatos` | Metadatos oficiales de norma BOE. |
| `boe_indice` | Índice paginado; seguir `siguiente_inicio`. |
| `boe_bloque` | Texto de un bloque y catálogo de versiones; fecha selecciona por publicación, no determina vigencia jurídica. |
| `boe_analisis` | Notas y relaciones normativas. |
| `boe_buscar` | Frase literal en legislación consolidada. |
| `boe_vigencia` | Indicadores oficiales y sus límites; sin conclusión automática de aplicabilidad. |
| `dogv_sumario` | Sumario por fecha; puede haber extraordinarios. |
| `dogv_buscar` | Búsqueda global en el índice del portal DOGV, por defecto en texto completo. Modo opcional de filtro local de sumario. |
| `dogv_publicacion` | Texto de publicación por ID, código o CVE; comprobar anexos y original firmado. |
| `ts_buscar` | Búsqueda puntual en la base pública CENDOJ, filtrada al Supremo. Sin consulta ni filtros conserva los destacados de portada. |
| `ts_resolucion` | Extrae un PDF individual desde un enlace oficial `openDocument`. |
| `juridico_buscar` | Búsqueda común BOE/DOGV/TS; respeta el alcance de cada fuente. |
| `juridico_documento` | Recuperación común de metadatos, bloque o documento. |
| `juridico_estado` | Versión, UID, capacidades y límites; no hace tráfico externo. |

### DOGV

`dogv_buscar`: `texto` (1–100 caracteres), `idioma=es|va`, `inicio=0`, `limite=10`, `modo=global|sumario`, `solo_titulo=false`, `solo_vigentes=false`, `desde` y `hasta` en AAAA-MM-DD. El parámetro `fecha` restringe la publicación a un solo día y no se combina con desde/hasta.

En modo global se consulta todo el índice accesible al buscador oficial, sin limitarse al último sumario. Se devuelven total, filtros efectivos, publicaciones y siguiente posición. Una llamada solicita una sola página de 10. Si el inicio cae cerca del final de esa página puede devolver menos elementos; seguir `siguiente_inicio`. Desplazamiento máximo 1000. La cobertura y actualización son las del índice oficial; no se garantiza la presencia de cualquier documento histórico.

`modo=sumario` conserva el filtro local por título, organismo y código de inserción de un sumario. No admite filtros generales adicionales. `solo_vigentes` es un filtro descriptivo de la fuente, no una valoración jurídica. El texto de `dogv_publicacion` puede omitir anexos; comprobar el original firmado y CVE.

### Tribunal Supremo/CENDOJ

`ts_buscar`: `consulta`, `limite` (1–10), `inicio` (0–199), `sala` (civil, penal, contencioso, social, militar o especial), `desde`, `hasta`, `ecli`, `roj`, `ponente`, `recurso` y `resolucion`. Fechas AAAA-MM-DD. Si no hay consulta ni filtros se devuelven destacados, manteniendo el comportamiento anterior.

Las búsquedas usan el filtro de órgano del propio formulario. Cada resultado debe confirmar `data-db=TS`, ROJ y ECLI del Supremo en sus metadatos; si aparecen órganos ajenos o cambia el formato se devuelve error, sin mezclar resultados ni fingir cero coincidencias. Incluyen enlace oficial y extracto del resumen de CENDOJ; comprobar el PDF original para uso jurídico.

Se recupera una página por llamada, sin descargar automáticamente los PDFs de los resultados. El portal limita la recuperación a 200 aunque el total de coincidencias sea mayor. Acotar la búsqueda con filtros. Sin caché de resultados o resoluciones CENDOJ; las cookies de sesión pública permanecen solo en memoria y no se entregan al cliente.

La consulta es particular. El aviso legal de CENDOJ prohíbe la descarga masiva y exige su procedimiento para reutilización en bases de datos o con fines comerciales. Esta integración no concede derechos adicionales de reutilización.

## Aislamiento y límites

El túnel mantiene su configuración original. La entrada `/opt/mcp-juridico/server.py` carga la versión seleccionada por `/opt/mcp-juridico/current`. El proceso de consultas abandona root y se vuelve a ejecutar con un entorno limpio antes de importar FastMCP. Usuario sin acceso interactivo: `mcp-juridico`. Estado privado de FastMCP: `/var/lib/mcp-juridico`, permisos 700. No se heredan secretos del túnel. El proceso del cliente del túnel conserva su usuario original root.

El ajuste systemd está en `/etc/systemd/system/tunnel-client.service.d/50-juridico-hardening.conf`: memoria alta 256 MiB, máximo 320 MiB, CPU 80 % de un núcleo, 64 tareas y 1024 descriptores; NoNewPrivileges, PrivateTmp y protección del núcleo. Los identificadores, entorno y comando originales del túnel se conservan.

Por proceso: dos peticiones simultáneas, 4 MiB por descarga, 160 kB por salida, caché BOE/DOGV de hasta 8 MiB y 32 entradas durante 300 segundos. Intervalo mínimo por host: un segundo BOE/DOGV y cinco segundos CENDOJ. No es una cuota global entre todos los procesos. No hay caché de respuestas CENDOJ. La caché de consultas DOGV distingue también el cuerpo POST.

Solo HTTPS y rutas oficiales fijadas, TLS verificado y redirecciones limitadas al mismo host. Los únicos POST permitidos son la consulta DOGV y `action=query` de CENDOJ; no hay operaciones de cuenta. Se validan entrada, fechas, órgano y paginación. Se rechazan DTD, entidades XML y traversal. El HTTP 440 se clasifica como error de fuente, sin inferir autenticación.

El extractor PDF corre en otro proceso con límites de memoria, CPU, tiempo y salida. Temporales eliminados al terminar, sin OCR. El contenido externo se considera datos, nunca instrucciones.

## Verificación y funcionamiento

```bash
systemctl is-active tunnel-client
curl -fsS http://127.0.0.1:18989/readyz
systemctl show tunnel-client -p MemoryCurrent -p MemoryPeak -p TasksCurrent -p MemoryMax -p CPUQuotaPerSecUSec
cd /opt/mcp-juridico/current
/opt/mcp-juridico/.venv/bin/python -m unittest discover -s tests -v
```

`smoke_mcp.py` comprueba el protocolo stdio real, las 14 herramientas y casos generales de búsqueda: DOGV completo, ordenación, página siguiente y fechas; Supremo por texto y sala, página siguiente, ECLI exacto y consulta sin resultados. Las pruebas de red son manuales y puntuales; no programarlas como monitor frecuente. Los informes no contienen cookies ni secretos. El despliegue compara las huellas del código con las probadas y rechaza resultados de prueba antiguos.

Para reiniciar:

```bash
systemctl restart tunnel-client
curl --retry 5 --retry-connrefused --retry-delay 1 -fsS http://127.0.0.1:18989/readyz
```

Los registros privados del túnel pueden contener datos de conexión. No pegar `tunnel.env`, el entorno, `systemctl cat` ni registros completos en chats. Los registros propios de consultas contienen herramienta y duración, sin argumentos completos.

## Copias, despliegue y catálogo

Versiones en `/opt/mcp-juridico/releases/`, copias privadas en `/var/backups/mcp-juridico/`. Cada despliegue conserva la entrada anterior, enlace y ajuste systemd y genera un `rollback.py` completo. `deployment.json` identifica la copia y versión. Se conmuta mediante renombrado y se revierte automáticamente si el servicio no pasa readyz. Para revertir, ejecutar como root `python3 /var/backups/mcp-juridico/<marca-del-despliegue>/rollback.py`, usando la ruta `backup` del informe generado por `deploy.py`, y comprobar de nuevo el servicio y readyz.

Tras cambiar descripciones o argumentos, actualizar la conexión en ChatGPT Plugins → MCP Jurídico Español → Refresh. No cambiar el túnel ni crear otro. Los nombres y argumentos anteriores siguen admitidos; los nuevos filtros requieren que ChatGPT importe el esquema actualizado.

## Fuentes

- [Portal oficial DOGV](https://dogv.gva.es/es/): contrato observado en el código público que utiliza su buscador; no se garantiza estabilidad de una API documentada.
- [CENDOJ y aviso legal](https://www.poderjudicial.es/search/indexAN.jsp): formulario público y código cliente que envía sus consultas.
- [BOE: API consolidada](https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf).
- [OpenAI: actualizar metadatos de un MCP](https://developers.openai.com/plugins/deploy/connect-chatgpt#refresh-metadata).
