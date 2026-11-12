# MCP Jurídico Español · Comunitat Valenciana

Servidor MCP de consulta de fuentes jurídicas oficiales españolas: **BOE**, **DOGV** y jurisprudencia del **Tribunal Supremo en CENDOJ**. Versión **1.2.3**, transporte **stdio**, 14 herramientas. No realiza llamadas a APIs de modelos ni utiliza buscadores de pago.

## Capacidades

| Fuente | Consultas |
| --- | --- |
| BOE | Metadatos, índice, articulado, versiones históricas por publicación, análisis, búsqueda en legislación consolidada e indicadores de vigencia. |
| DOGV | Sumarios, búsqueda global en texto o título, filtros de fechas e idioma, recuperación de publicaciones por ID o CVE. |
| Tribunal Supremo | Búsqueda puntual en CENDOJ por texto, sala, fechas, ECLI, ROJ, ponente, recurso y resolución; extracción de un PDF oficial individual. |
| Comunes | Búsqueda, recuperación de documentos y estado del servicio. |

Las respuestas incluyen estado `ok`, enlaces oficiales, fecha de consulta, alcance, advertencias y paginación cuando corresponda. El contenido recuperado se trata como datos externos.

## Mejoras desde la versión 1.1.5

- DOGV localiza disposiciones por número y título, contrasta candidatas y declara si queda búsqueda pendiente.
- La extracción del original admite páginas físicas seleccionadas y conserva los enlaces oficiales y el idioma de cada fragmento.
- El localizador de frases devuelve páginas candidatas y parámetros para extraer una página o continuar el barrido. La extracción automática puede devolver un pasaje si se confirma la frase en el idioma solicitado.

Ejemplo para localizar y extraer un pasaje en una llamada.

```json
{"herramienta":"dogv_publicacion","argumentos":{"identificador":"2021/4855","tipo_texto":"original","buscar_pdf":"racionalización de los recursos","extraer_pdf":true,"max_caracteres":500}}
```

En clientes con un catálogo anterior se puede usar `original:2021/4855#buscar=racionalización de los recursos#extraer=1` como identificador. El localizador busca en el texto disponible del PDF y carece de OCR. Véase [CHANGELOG.md](CHANGELOG.md).

## Requisitos e instalación

Entorno de referencia: **Debian 13, Python 3.13, FastMCP 4.1.3**, un núcleo y 512 MiB de RAM. La extracción PDF requiere `poppler-utils` y **PyMuPDF 1.26.7**; no incluye OCR.

En una máquina Debian dedicada, como administrador:

```bash
apt-get update
apt-get install -y --no-install-recommends python3 python3-venv poppler-utils git
id mcp-juridico >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /var/lib/mcp-juridico --shell /usr/sbin/nologin mcp-juridico
install -d -m 700 -o mcp-juridico -g mcp-juridico /var/lib/mcp-juridico
git clone https://github.com/jmuruais/MCP_Jur-dico_CV.git /opt/mcp-juridico
python3 -m venv /opt/mcp-juridico/.venv
/opt/mcp-juridico/.venv/bin/python -m pip install -r /opt/mcp-juridico/requirements.txt
```

El destino del clon debe estar vacío. Para una instalación existente, revisar el procedimiento de actualización del manual. `requirements.lock` conserva las versiones del entorno validado; `requirements.txt` declara las dependencias directas.

Configurar el cliente MCP para ejecutar:

```text
/opt/mcp-juridico/.venv/bin/python /opt/mcp-juridico/server.py
```

El proceso iniciado como root abandona sus privilegios y usa el usuario `mcp-juridico`. El servidor vuelve a ejecutarse con un entorno limpio y necesita acceso de escritura a `/var/lib/mcp-juridico`. El código debe permanecer legible y no modificable por ese usuario.

La conexión remota mediante un túnel se configura por separado con el proveedor elegido. Este repositorio no contiene credenciales ni configura un túnel nuevo. El archivo `tunnel-client-hardening.conf` es un ajuste para el servicio existente descrito en el manual.

## Herramientas

- BOE: `boe_metadatos`, `boe_indice`, `boe_bloque`, `boe_analisis`, `boe_buscar`, `boe_vigencia`.
- DOGV: `dogv_sumario`, `dogv_buscar`, `dogv_publicacion`.
- Supremo: `ts_buscar`, `ts_resolucion`.
- Comunes: `juridico_buscar`, `juridico_documento`, `juridico_estado`.

Ejemplos de argumentos para un cliente MCP:

```json
{"herramienta":"dogv_buscar","argumentos":{"texto":"procedimiento administrativo","solo_titulo":true,"desde":"2020-01-01","hasta":"2026-10-26","limite":2}}
```

```json
{"herramienta":"ts_buscar","argumentos":{"consulta":"despido","sala":"social","desde":"2025-01-01","hasta":"2026-10-26","limite":2}}
```

Los objetos anteriores ilustran las llamadas; no son una API HTTP del servidor. Para comprobarlo desde ChatGPT, pedir primero `juridico_estado` y confirmar versión 1.2.3; después ejecutar ambos ejemplos y buscar por el ECLI de un resultado. Revisar `ok` e `isError`, argumentos disponibles, enlaces y fecha de consulta.

## Pruebas y actualización

Pruebas unitarias sin acceso a red (requieren PyMuPDF para las muestras sintéticas):

```bash
python3 -m unittest discover -s tests -v
```

Pruebas de integración manuales, desde el directorio del proyecto y con los requisitos de ejecución preparados:

```bash
/opt/mcp-juridico/.venv/bin/python smoke_mcp.py
```

La versión 1.2.3 superó **140 pruebas unitarias** y **41 comprobaciones MCP de BOE y DOGV** con `smoke_mcp.py --sin-cendoj`, incluido el orden oficial de las 53 publicaciones del DOGV 10483. La validación del 12 de noviembre de 2026 también ejecutó la continuación del barrido y la extracción de una página desde Work. La disponibilidad futura depende de las fuentes. Ejecutar las consultas en vivo de forma puntual.

Los documentos de referencia no están incluidos en este repositorio ni alimentan el servicio. Para validar muestras oficiales ya descargadas, ejecutar `python tests/reference_documents.py DIRECTORIO_MUESTRAS`; el manual describe los archivos requeridos.

`deploy.py` está pensado exclusivamente para actualizar una instalación ya existente con `/opt/mcp-juridico/.venv`, `tunnel-client.service`, su configuración privada y el usuario de servicio preparados. Se ejecuta desde un directorio de preparación con el código y un `smoke-results.json` satisfactorio. Crea una copia privada, comprueba las huellas del código probado, cambia de versión y revierte si falla la comprobación de disponibilidad. No es un instalador inicial.

Consultar [OPERACIONES.md](OPERACIONES.md) para argumentos, límites, servicio systemd, copias, despliegue y reversión.

## Límites y condiciones de las fuentes

Solo se admiten hosts y rutas oficiales por HTTPS, con validación TLS, límites de descarga, salida, concurrencia y tiempo. El extractor PDF tiene límites propios. La caché BOE/DOGV es acotada; CENDOJ no se almacena en caché. Los límites de peticiones son por proceso.

DOGV devuelve como máximo una página oficial de 10 por llamada; CENDOJ permite recuperar hasta 200 resultados de una búsqueda. Seguir `siguiente_inicio` únicamente cuando sea necesario para una consulta concreta. No hay recopilación automática de páginas o PDFs, elusión de controles interactivos ni descarga masiva.

CENDOJ se usa para consulta particular conforme a las condiciones de su portal. La integración no concede derechos adicionales de reutilización de resoluciones. Las versiones BOE se seleccionan por fecha de publicación; los indicadores de vigencia y los filtros de documentos vigentes no determinan por sí solos la aplicabilidad jurídica. Comprobar los documentos originales y los anexos DOGV.

- [BOE · API de legislación consolidada](https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf)
- [DOGV · portal oficial](https://dogv.gva.es/es/)
- [CENDOJ · buscador y aviso legal](https://www.poderjudicial.es/search/indexAN.jsp)
