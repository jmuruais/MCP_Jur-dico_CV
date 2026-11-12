# Cambios

## 1.2.3 · 12 de noviembre de 2026

Las búsquedas de frases en originales DOGV incluyen argumentos para extraer la página de una coincidencia y continuar desde la siguiente página física con la misma configuración. La validación comprobó 12 coincidencias en cada uno de dos tramos consecutivos del mismo original y recuperó una de las páginas propuestas.

## Mejoras acumuladas 1.1.6–1.2.2

Localización DOGV progresiva con identificación de disposiciones y exposición de ambigüedad. Selección de páginas físicas del PDF original y localización de frases con un barrido acotado. Extracción automática de un pasaje alrededor de la frase si se confirma en el idioma solicitado, con prioridad para un único posible encabezado y opción de extraer una mención única del tramo.

## 1.1.5 — 4 de noviembre de 2026

Extracción geométrica de originales DOGV con selección es/va/ambos, orden por columna y referencias por página. Tablas de niveles I–IV verificadas por geometría y representadas en JSON/Markdown; páginas o tablas inciertas se indican expresamente.

Identidad CENDOJ de cabecera separada de citas; cotejo con búsqueda reciente en la misma sesión. HTTP 502/503/504 admite un reintento limitado, sin eludir restricciones. Diagnósticos separados para bloqueos, vacíos y conectividad, con telemetría de duración y estado HTTP.

Validación: 94 pruebas unitarias, 29 comprobaciones documentales y 25 criterios MCP. Tres búsquedas por ECLI y sus tres recuperaciones PDF verificadas tras reiniciar. Las firmas de las 14 herramientas se mantienen.

Cambio semántico: los campos heredados roj_en_documento/ecli_en_documento incluyen solo la identidad principal. Las citas se exponen en campos separados. No se afirma una verificación íntegra del documento por haber extraído texto.

## Mejoras acumuladas 1.1.1–1.1.4

Orden DOGV cotejado contra el PDF de la misma edición; sumarios históricos con recuperación limitada explícita cuando el orden no puede verificarse. Resolución de signaturas históricas. Distinción entre búsqueda de menciones y localización exacta por título. Selección explícita de originales, consolidaciones y versiones por fecha, sin dictamen automático de vigencia. Alternativa oficial web BOE ante HTTP 500 de la API sin perder filtros temporales.

## 1.1.0

Versión anterior publicada en el repositorio: 14 herramientas BOE, DOGV y Tribunal Supremo, consultas acotadas y despliegue reversible.
