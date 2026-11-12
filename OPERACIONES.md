# MCP Jurídico Español — versión 1.1.0

## Alcance

CT 105, Debian 13, 1 CPU, 512 MiB de RAM. Servicio existente `tunnel-client.service`, transporte stdio. No hay APIs de modelos, buscadores de pago, OCR ni navegador instalado en el LXC. Se conservan el entorno Python y los identificadores y secretos del túnel. Dependencia de sistema ya instalada: `poppler-utils`.

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

Versiones en `/opt/mcp-juridico/releases/`, copias privadas en `/var/backups/mcp-juridico/`. Cada despliegue conserva la entrada anterior, enlace y ajuste systemd y genera un `rollback.py` completo. `deployment.json` identifica la copia y versión. Se conmuta mediante renombrado y se revierte automáticamente si el servicio no pasa readyz. El informe de entrega indica el comando exacto de reversión de esta versión.

Tras cambiar descripciones o argumentos, actualizar la conexión en ChatGPT Plugins → MCP Jurídico Español → Refresh. No cambiar el túnel ni crear otro. Los nombres y argumentos anteriores siguen admitidos; los nuevos filtros requieren que ChatGPT importe el esquema actualizado.

## Fuentes

- [Portal oficial DOGV](https://dogv.gva.es/es/): contrato observado en el código público que utiliza su buscador; no se garantiza estabilidad de una API documentada.
- [CENDOJ y aviso legal](https://www.poderjudicial.es/search/indexAN.jsp): formulario público y código cliente que envía sus consultas.
- [BOE: API consolidada](https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf).
- [OpenAI: actualizar metadatos de un MCP](https://developers.openai.com/plugins/deploy/connect-chatgpt#refresh-metadata).

## Correcciones 1.1.1 (1 de noviembre de 2026)

- Sumario DOGV: el array JSON puede intercalar secciones. Se ordena por la secuencia de CVE extraída del PDF oficial de la misma edición, verificando número, fecha y correspondencia única de todos los códigos antes de paginar. Incluye procedencia y huella del PDF. Si el PDF no está disponible, cambia de formato o no coincide, se devuelve error; no se inventan posiciones. Una descarga adicional acotada por edición, con caché en memoria de cinco minutos. No todos los extraordinarios/formatos históricos se han validado.
- Búsqueda DOGV: solo ante HTTP 440 con diagnóstico exacto `error.bbdd.query`, la consulta de texto completo puede ofrecer la alternativa pública por título. Declara recuperación parcial, error original y filtros solicitados/aplicados. Mantener `solo_titulo=true` al seguir sus posiciones. Una búsqueda parcial vacía no prueba ausencia. No se aplica alternativa ante 403 ni errores sin diagnóstico. No se ha reparado la base de datos de la fuente.
- Publicación DOGV: `AAAA/número` es una signatura; se resuelve con `/dogv/obtenerIdDogv/AAAA-número`, utilizado por el frontend oficial. No se fabrica un CVE para publicaciones antiguas. Se verifica el ID y la signatura de la ficha recuperada.
- CENDOJ: ROJ y ECLI se envían en campos específicos, distintos de TEXT. Se rechazan respuestas con referencias exactas discordantes. Sin reintentos ni rutas alternativas ante 403/CAPTCHA; el estado HTTP no acredita por sí solo la causa del rechazo.
- Pruebas: `python -m unittest discover -s tests -v` (sin red); `python smoke_mcp.py` realiza casos puntuales de protocolo con mediciones y respuestas en `smoke-results.json`. Dos páginas DOGV solo de una edición; tres búsquedas CENDOJ sobre una sola resolución y un PDF. No ejecutar repetidamente ni usar como recolector.
- `passed` del informe real exige todos los casos críticos y secuencia completa del sumario. Los casos externos no críticos (búsqueda BOE y CENDOJ) conservan su resultado individual; no se presentan como éxitos si fallan. El informe no acredita calidad jurídica de modelos ni disponibilidad estadística.

## Candidato 1.1.2 (3 de noviembre de 2026)

Esta versión debe verificarse en CT105 antes de desplegar. No deducir despliegue de las pruebas HTTP locales.

- BOE: `modo=auto` consulta primero la API. Solo ante HTTP 500 sin filtros de última actualización ofrece el buscador web oficial, solicitando únicamente normas con texto consolidado y frase literal. `solo_titulo=true` restringe a títulos. `modo=api` conserva la vía original; `modo=web` fija la alternativa al paginar.
- La alternativa web declara cobertura distinta (`recuperacion_completa=false`) porque puede localizar versiones cronológicas y referencias autonómicas fuera de los IDs admitidos por la API. Cada referencia indica `recuperable_api`. No declara equivalencia ni ausencia exhaustiva.
- Una sola página oficial de hasta 50 referencias; devuelve fragmentos de hasta 25. `siguiente_inicio` termina al agotar esos 50 aunque la fuente indique más resultados; `truncado=true` y el límite quedan visibles. Acotar consulta o usar API para otros resultados. El límite se aplica antes de contactar con la fuente para inicio>=50.
- Los filtros desde/hasta de la API son de última actualización. No se trasladan a fechas de publicación ni se descartan. `modo=web` los rechaza; `auto` con fechas conserva el error de API sin activar alternativa. Se rechazan comillas internas y barras inversas cuando no se garantiza una frase literal equivalente en la web.
- Se verifica rango de página, número de filas, identidades únicas y coincidencia de referencias del documento original y consolidado. Un cambio de HTML o un aviso de servicio no se convierte en cero resultados. No hay alternativa ante 403/429.
- Registro de consultas: nombre de herramienta, estado ok/parcial/error, código de error, HTTP y duración. No incluye consulta, documento, mensaje externo ni credenciales.
- La prueba real DOGV distingue recuperación general de localización exacta por título. No exige que una norma antigua sea el primer resultado de una búsqueda en texto completo ordenada por fecha. El 3/11 la consulta de texto completo volvió a funcionar en el caso ensayado (277 coincidencias).

## Correcciones DOGV 1.1.3 (3 de noviembre de 2026)

- `dogv_publicacion`: `tipo_texto=portal` identifica la naturaleza del HTML y consulta el catálogo oficial si la ficha indica consolidación. Distingue fecha de publicación original, publicación de la versión e intervalo declarado por la fuente. `fecha=AAAA-MM-DD` selecciona un único intervalo publicado antes del corte; no extrapola ni resuelve aplicabilidad jurídica. Si no existe un catálogo fiable, se declara la limitación o se rechaza la selección histórica.
- `tipo_texto=original` recupera el PDF de la versión inicial a través del enlace que ofrece el frontend oficial. Valida la ruta, fecha, número de diario y signatura/CVE. No sustituye el original por una consolidación. No valida criptográficamente la firma; desde 1.1.5 el original bilingüe se segmenta conservadoramente por idioma y geometría (véase abajo).
- Los indicadores `estado.descripcion`, `consolidacionVigente` y `contieneAnexo` se conservan como datos de la fuente. No determinan por sí solos vigencia ni ausencia de anexos. Se detectan referencias y encabezados en la extracción, se informa su posición y se declara la cobertura del fragmento. No se aplica OCR ni se garantiza extracción de tablas o imágenes.
- `dogv_sumario`: el PDF sigue siendo la referencia para un orden cotejado. Si falta o no puede cotejarse, se recuperan las referencias con `orden_verificado=false` y `recuperacion_completa=false`; se muestran por página inicial solo cuando todos esos números son distintos y válidos, sin atribuir posiciones editoriales. `exigir_orden=true` devuelve error. Una colección de otra fecha o con identidades duplicadas se rechaza.
- `dogv_buscar modo=disposicion`: requiere tipo y número/año, consulta una página oficial por título y separa coincidencias al inicio del título. Conserva candidatos y posiciones de la fuente; total desconocido y recuperación parcial si no se agotó la búsqueda. `modo=global` mantiene menciones y orden oficial por fecha; no se aplica reordenación encubierta.
- La consulta unificada DOGV admite fecha con el mismo criterio declarado. Los nuevos parámetros requieren recargar las definiciones de herramientas si el cliente conserva el esquema antiguo.
- Regresiones: `python -m unittest discover -s tests -v`; batería real `python smoke_mcp.py` centrada en DOGV con guardia BOE. No incluye llamadas nuevas a CENDOJ. Las muestras de pruebas no constituyen un índice de consulta y el servidor no las utiliza para recuperar documentación. No usa VIVES ni una base documental paralela.

## Compatibilidad 1.1.4

Se observó que el cliente de herramientas conservaba el esquema antiguo y descartaba `tipo_texto`, aunque el servidor 1.1.3 lo admitía por MCP directo. El texto devuelto seguía etiquetado como consolidado, pero no satisfacía la petición de original.

Para usar los campos existentes de ese cliente sin ambigüedad:

- Original: `dogv_publicacion(identificador="original:2018/7822")`. `original:` es un selector de extracción, no parte de la signatura o CVE. La respuesta conserva el identificador oficial y declara el selector.
- Fecha: `juridico_documento(fuente="DOGV", identificador="2018/7822", fecha="2021-07-01")`.
- Disposición exacta: `dogv_buscar(texto="Decreto 104/2018", modo="disposicion")`.

Los parámetros nuevos (`tipo_texto`, `fecha` en dogv_publicacion y `exigir_orden`) requieren un cliente con la definición de herramientas actualizada. No confiar en que un campo desconocido llegue al servidor: comprobar siempre naturaleza, fecha solicitada, versión y estado del orden en la respuesta.

## Versión 1.1.5 — extracción documental y CENDOJ

- Dependencia adicional fijada: `PyMuPDF==1.26.7` (rueda binaria 24,1 MB, sin OCR, modelos ni servicios externos). Antes de instalar se guardó el inventario de dependencias. CT105: 512 MB RAM, 465 MB disponibles en preflight y 6 GB de disco libre.
- `dogv_publicacion(identificador="original:2018/7822", idioma="es")`, `idioma="va"` o `idioma="ambos"`. Se mantiene el selector de original compatible con clientes antiguos. `ambos` solo se admite para originales. Los textos HTML conservan es/va.
- `pdf_geometry.py` identifica corredores vacíos entre columnas y determina el idioma con evidencia léxica, sin deducirlo por izquierda/derecha. Ordena por coordenadas dentro de cada columna. Para dos columnas exige evidencia de ambos idiomas. Páginas sin geometría/idioma identificables se omiten con lista explícita. No se sustituye un error geométrico por el texto mezclado.
- `paginas_fragmento` enlaza índices físicos del PDF (base 1), rangos de caracteres y coordenadas; `paginas_estado` y `paginas_omitidas` describen cobertura. Los desplazamientos pertenecen al idioma, versión y extractor concretos; no reutilizar offsets de 1.1.4.
- Tablas: detecta cuadrículas, normaliza páginas giradas y valida de manera específica matrices de seis columnas con cabecera explícita y filas I–IV, sin celdas vacías ni palabras asignadas a varias celdas. Conserva contexto y celdas en JSON y Markdown. Otras tablas detectadas se marcan `tabla_estructura_verificada=false` y no se aplanan como contenido fiable. Las tablas sin bordes o con maquetaciones nuevas pueden no detectarse; `extraccion_verificada=false` sigue siendo global.
- `tablas` contiene solo las tablas que intersectan las páginas del fragmento pedido; `tablas_paginas_documento` permite localizar las otras sin devolver sus datos completos.
- Tres estados separados: `documento_recuperado`, `texto_extraido`, `extraccion_verificada`. La última bandera permanece false: geometría comprobada no equivale a cotejo íntegro visual/semántico. `extraccion_documental_parcial` recoge omisiones estructurales; `fragmento` y `extraccion_parcial` incluyen el recorte solicitado. HTML no garantiza integridad de anexos y queda como recuperación parcial.
- Extracción en proceso separado: 320 MiB de espacio virtual, 18 s CPU, 24 s reloj, 5 MB JSON y 120 páginas. El extractor de texto plano previo mantiene su salida máxima de 2 MB. La descarga conserva 4 MiB y la respuesta MCP 160 kB. No OCR ni ejecución de contenido PDF.
- CENDOJ: `roj_resolucion`/`ecli_resolucion` proceden exclusivamente de la línea Roj/ECLI de cabecera de la primera página antes de Id Cendoj. `roj_resoluciones_citadas`/`ecli_resoluciones_citadas` se extraen aparte. Los campos heredados `roj_en_documento`/`ecli_en_documento` contienen únicamente la identidad principal; cambio deliberado para impedir atribuciones falsas.
- El cotejo con la búsqueda usa solo URL/ROJ/ECLI, máximo 200 referencias y 300 segundos en memoria, misma sesión MCP. No guarda documentos ni resultados CENDOJ. Sin búsqueda reciente `coincidencia_busqueda_verificada=null`; discrepancia genera advertencia e `identificacion_verificada=false`. ROJ/ECLI ausentes/ambiguos en cabecera producen error.
- CENDOJ conserva sus rutas, cookies públicas, parámetros y filtro Supremo. Solo HTTP 502/503/504 permite un reintento, respetando Retry-After corto; no reintenta 401/403/429, CAPTCHA, vacíos ni conectividad/timeout. Se registran host, estado HTTP, intento y duración, sin consultas, cookies o contenido. El resultado vacío se distingue de cero coincidencias.
- CENDOJ sigue usando texto plano: tablas/anexos sin estructura cotejada, advertencias explícitas y páginas físicas. Su fecha es de resolución, no de publicación; publicación null cuando no consta.

Pruebas: `python -m unittest discover -s tests -v` (sin red; requiere PyMuPDF para PDFs sintéticos). `python tests/reference_documents.py DIRECTORIO_MUESTRAS` valida documentos ya descargados: decreto.pdf, orden.pdf, tres PDFs `ATS-11323-2025.pdf`, `STS-5562-2025.pdf`, `STS-5603-2025.pdf` y baseline-ts.json de resultados oficiales. No descarga ni crea un corpus de servicio. `python smoke_mcp.py` comprueba las 14 herramientas, regresión BOE/DOGV, versiones, sumarios y es/va/ambos. La comprobación posterior al reinicio se ejecuta puntualmente aparte; detenerse ante restricciones y conservar el error estructurado.

## Versión 1.1.6 — localización y selección acotadas

`dogv_buscar(modo="disposicion")` admite tipo/número/año con materia u organismo. Conserva argumentos anteriores; añade límites opcionales: `max_paginas=5` (1..5), `max_alternativas=2` (0..3), `max_segundos=35` (1..60), `max_candidatos=50` (1..50). Máximo cuatro fichas verificadas. Son límites **totales**, no por cada estrategia. `global` y el alias `cronologico` conservan la página y el orden oficial; no hacen clasificación progresiva.

Primero consulta la referencia por título sin inferir fechas; después puede explorar el año de numeración, explícitamente como vía auxiliar. Nunca considera agotada toda la búsqueda por haber agotado el filtro anual. Si el índice no devuelve la norma, puede utilizar el buscador web **oficial del BOE**, leer exclusivamente la identificación y metadatos de publicación, descubrir fecha/edición DOGV y cotejar el sumario de esa edición y la ficha DOGV. No hay signaturas, ROJ o ECLI objetivo prefijados en el algoritmo. No utiliza buscadores generales ni repositorios alternativos. La vía BOE solo se intenta si quedan tres páginas/fuentes de presupuesto; los filtros temporales del usuario se comprueban sobre la publicación DOGV, no se sustituyen por fechas de actualización BOE.

La ficha final verifica ID, título, tipo/número/año, signatura, fecha y edición. No se deduce la identidad solo por similitud. El contexto prioriza coincidencias completas de términos; si hay empate o contexto insuficiente, se conservan opciones y ambigüedad. Las relaciones normativas solo se clasifican cuando el título expresa la relación con la referencia: no determina efectos jurídicos. Las apariciones conservan posiciones y estrategia de origen.

Estados: `localizada`, `ambigua`, `candidata_pendiente`, `no_confirmada`, `no_encontrada_en_alcance` o `error_fuente`. Un error anterior a la primera página produce el error MCP estructurado habitual. Si ya había resultados, se conservan con `error_fuente` y recuperación parcial. `busqueda_agotada` y `recuperacion_completa` no equivalen a que una referencia haya sido localizada: una ficha puede estar verificada sin haber agotado el índice. `total=null` cuando no puede afirmarse un total completo. Seguir la continuación de la consulta/estrategia indicada; los desplazamientos no son posiciones del ranking agregado.

`publicaciones` conserva la selección de disposiciones exactas; `otras_coincidencias_exactas`, `disposiciones_relacionadas`, `candidatos_fuente` y `resultados_clasificados` permiten revisar las demás. `candidatos_encontrados` es un índice compacto. Una norma no localizada en el presupuesto no se declara inexistente. Las huellas de páginas y fichas figuran en la traza; un agregado no tiene una única huella documental y devuelve `sha256_fuente=null`.

`ts_buscar` añade `orden="relevancia"` (por defecto) o `cronologico`, `max_consultas=2` (1..2) y `max_segundos=30` (1..60). Reconoce un ROJ/ECLI dado como consulta completa y lo envía como filtro exacto. Para temas, consulta una página oficial y, si hay cero o más de diez resultados, puede probar una sola expresión entrecomillada derivada determinísticamente de la consulta. No amplía páginas ni descarga PDF. Máximo veinte candidatos devueltos por las páginas examinadas; duplicados identificados por ECLI.

La prioridad usa términos y expresiones en el resumen oficial con normalización conservadora de plurales, conservando evidencias. Se identifica tipo por prefijo ROJ (sentencia/auto) y se advierte que la cabecera se verifica al recuperar el PDF. No se infiere la sala competente ni se presenta el resumen como doctrina aplicable. `resoluciones_candidatas` incluye vistas compactas de hasta 900 caracteres de resumen, marcando el truncamiento; `resoluciones` conserva los campos anteriores de los seleccionados. Las continuaciones son de páginas de la fuente, no del ranking; el resto de la página recibida sigue disponible en las candidatas. En cronológico no reordena ni amplía. ROJ/ECLI exactos no activan alternativas. CENDOJ sigue sin caché documental y mantiene sus controles y reintentos limitados.

Métricas por búsqueda: peticiones HTTP iniciadas, aciertos de caché HTTP, estados/duración de respuesta, páginas/fuentes y candidatos comparados. Los duplicados cuentan si se comparan de nuevo; una ficha es verificación aparte, no una página de resultados. Las redirecciones internas del cliente HTTP no se desglosan como peticiones adicionales (no se observaron en los casos de aceptación). Caché BOE/DOGV: memoria existente, 8 MiB, TTL 300 s; no se crea corpus o caché persistente.

El presupuesto de tiempo se propaga por ContextVar a las esperas, adquisición de turno, apertura, lectura y reintentos HTTP. No se empieza otra operación cuando se ha agotado. Las lecturas se acotan al tiempo restante. El límite no garantiza interrupción instantánea de resolución DNS o de llamadas del sistema; no es un SLA de tiempo real. Se devuelve la limitación, sin completar resultados por inferencia.

Sin dependencias adicionales. No cambian las funciones BOE de articulado/versión/análisis ni la recuperación original/consolidada/histórica, la geometría, tablas o identidad de cabecera 1.1.5. `search_logic.py` debe incluirse en despliegue, paquete y huellas probadas. Tras validar, congelar y preparar casos nuevos para benchmark; las referencias de aceptación de esta versión son depuración y no serán el conjunto de evaluación.

Con `solo_vigentes=true` no se usa la referencia cruzada BOE/sumario, porque no puede reproducir ese filtro del índice con suficiente garantía. Se conserva el filtro y se devuelve el alcance limitado, sin inferir vigencia desde la ficha.

## Versión 1.1.8 — páginas físicas del original DOGV

Ejemplo: `dogv_publicacion(identificador="original:2019/2067", idioma="ambos", paginas=[4])`.
`paginas` acepta de uno a seis números de página física distintos (base 1), devueltos en orden del PDF. Requiere un original y es incompatible con la selección histórica por fecha. `inicio` y `max_caracteres` paginan el texto de esa misma selección, por lo que deben repetirse las páginas al seguir `siguiente_inicio`.

La consulta coteja la fecha, el número del diario y la signatura en la primera página. Descarga el original a un archivo temporal y calcula SHA-256 de todos los bytes recibidos. Solo carga para extracción la cabecera y las páginas indicadas. No usa peticiones Range ni una copia consolidada. En esta ruta se permite un máximo de 50 MiB, una selección simultánea por proceso MCP y 22 s de lectura desde el inicio de la petición, sujetos a resolución y llamadas del sistema. El archivo temporal se elimina al terminar. No se incluye en la caché HTTP. La descarga normal conserva 4 MiB. El extractor mantiene 320 MiB de espacio virtual, 18 s de CPU, 24 s de reloj y 5 MB de salida. El límite de 120 páginas sigue aplicándose al modo de extracción de documento completo.

`paginas_estado` conserva la numeración física y enlaza también las páginas omitidas. `seleccion_completa` indica que la respuesta cubre la selección sin truncamiento, sin confundirlo con `recuperacion_completa` del documento ni con cotejo visual o semántico íntegro. Un error local o una composición incierta deja esa página sin texto y conserva los fragmentos aprovechables de la selección. Un fallo general del proceso, una cabecera discordante o una página fuera de rango produce un error estructurado. Las referencias a anexos solo describen el alcance de las páginas solicitadas.

En clientes que no importen el argumento `paginas`, usar `identificador="original:2019/2067#paginas=4"`, o una lista separada por comas como `#paginas=69,122`. El sufijo es un selector local y nunca se envía a DOGV. No se combina con el argumento `paginas`. Tras instalar, actualizar el catálogo del complemento y verificar la ruta disponible en un chat nuevo.

## Versión 1.1.9 · Localización de frases en originales DOGV

Para buscar un pasaje antes de conocer su página, usar `tipo_texto="original", buscar_pdf="Anexo III. Situaciones de aprendizaje", pagina_desde=1`. En clientes con catálogo anterior, usar `identificador="original:2022/7571#buscar=Anexo III. Situaciones de aprendizaje#desde=1"`. La búsqueda distingue palabras completas e ignora mayúsculas, tildes y saltos de línea dentro de un bloque. Busca en todos los idiomas presentes en el PDF. No admite expresiones regulares, traducciones, frases que crucen bloques o páginas ni OCR.

Devuelve una candidata como máximo por página, con enlace físico e indicio normalizado. `posible_indice`, `posible_encabezado` y `mencion` son señales de presentación. Confirmar la página y el pasaje con `paginas` o `#paginas=`. El barrido se detiene tras 160 páginas, 12 candidatas u 8 s entre páginas. `siguiente_pagina` indica cómo continuar con la misma frase. Si el proceso se bloquea dentro de una página, se mantiene el límite duro existente del extractor. Se declaran páginas sin texto o no legibles y el alcance comprobado. Un resultado vacío no acredita inexistencia.

Se reutiliza la descarga temporal del original de hasta 50 MiB, el cotejo de primera página y el límite de una operación por proceso. Cada continuación vuelve a descargar un único original. El indicio normalizado no sirve como cita literal ni acredita vigencia.

## Versión 1.2.0 · Localización y extracción con una descarga

En el localizador DOGV, `extraer_pdf=true` o el sufijo `#extraer=1` activa una segunda operación sobre el mismo archivo temporal. Se intenta cuando hay una sola página marcada como posible encabezado **en el tramo examinado** o cuando la única candidata del tramo es una mención. En el segundo caso, `estado_pasaje` devuelve `extraido_en_mencion_unica_del_tramo` si se confirma la frase. La frase debe aparecer en un fragmento del idioma solicitado. `pasaje` contiene texto paginado, procedencia y la huella del mismo original. `consulta_en_fragmento` indica si la frase está en el recorte entregado, que puede truncarse con `max_caracteres`. La lista de candidatas, las limitaciones y la continuación se conservan también si falla la extracción o hay varias páginas candidatas.

Ejemplo compatible: `original:2021/4855#buscar=Jornada lectiva#extraer=1`. No se aplica OCR. La unicidad en un tramo no acredita que la frase sea única en el documento.

## Versión 1.2.3 · Continuación y selección desde el localizador

Cuando el barrido puede avanzar, `parametros_continuacion` contiene argumentos para volver a llamar a `dogv_publicacion` desde `siguiente_pagina` con la misma frase, idioma, tamaño y opción de extracción. Cada candidata admite `parametros_extraccion` para pedir su página física por el mismo identificador de ficha. Esta llamada devuelve el texto de la página desde el inicio, sujeto a paginación. Usar el enlace oficial de la candidata para cotejar el texto. En clientes con esquema anterior, siguen disponibles los selectores `#desde=` y `#paginas=`.
