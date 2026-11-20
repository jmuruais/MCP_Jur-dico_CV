# Revisión funcional local · 15 de noviembre de 2026

## Alcance y restricciones

- Repositorio de desarrollo: `/home/opencode/projects/MCP_Jur-dico_CV`.
- Intérprete existente: `/srv/mcp-test/venv/bin/python` (Python 3.13.5,
  FastMCP 4.1.3, PyMuPDF 1.26.7). Sin instalaciones ni cambios del entorno.
- Pruebas con respuestas simuladas y muestras locales; sin consultas a BOE,
  DOGV ni CENDOJ. No se valida disponibilidad ni cambios actuales de sus portales.
- Sin cambios en `offline_runner/`, `runner_tests/`, servicios del sistema,
  instaladores o despliegues; sin acceso al CT 105.
- Los cambios previos ajenos a esta revisión se conservan.
- Revisión delegada al modelo GLM disponible
  `opencode/glm-5.3-flash-free`, dentro de OpenCode.

## Base reproducible

Las **140 pruebas originales pasan**, sin fallos ni omisiones, en 2,771 s.
Se bloqueó DNS y las conexiones mediante `unittest.mock` sobre
`socket.getaddrinfo`, `socket.socket.connect` y `connect_ex`.

Comando para repetir la suite desde el repositorio:

```bash
PYTHONDONTWRITEBYTECODE=1 /srv/mcp-test/venv/bin/python tests/run_unit_tests.py
```

`tests/run_unit_tests.py` es una entrada sencilla de `unittest`, sin
instalación, coordinación ni servicios. Bloquea la red durante descubrimiento
y ejecución en el proceso principal. Los subprocesos son extractores PDF
locales; el bloqueo Python no constituye un aislamiento de red del sistema.

## Ciclos de corrección y revisión

### Ciclo 1 · Contrato de respuestas

- Defecto reproducido: un JSON con `status` nulo, lista, cadena, número o
  booleano causaba `AttributeError` en vez de un diagnóstico de la fuente.
- Corrección: validar que `status` sea un objeto y devolver
  `FORMATO_INESPERADO`, con la URL de procedencia.
- Regresión: `tests/test_source_contracts.py`, cinco variantes en subpruebas.
  Antes de corregir: cinco errores. Después: **141/141 pruebas**, en 2,586 s.
- Controles adicionales: se conservan las respuestas correctas BOE con código
  numérico o textual, los errores oficiales y el ID numérico del resolutor DOGV.
  Suite con estos controles: **144/144 pruebas**, en 2,580 s.
- GLM aceptó esta corrección sin observaciones bloqueantes e identificó
  los tres defectos semánticos tratados en el siguiente ciclo.

### Ciclo 2 · BOE, DOGV y CENDOJ

| Fuente | Defecto reproducido | Corrección conservada |
| --- | --- | --- |
| BOE | `juridico_buscar` aceptaba `fecha` pero la ignoraba. | Rechazo con `PARAMETRO_NO_ADMITIDO` antes de conectar. La fecha unificada solo se aplica a DOGV/TS; `desde/hasta` de `boe_buscar` filtran actualización, no publicación. |
| DOGV | «modifica el Decreto-Ley» se clasificaba como mera mención; tampoco se reconocía «Decret-llei». | Reutilización del patrón normativo para relaciones y corrección de la variante valenciana. Se mantiene la exigencia de relación expresa en el título; no se infieren efectos jurídicos. |
| CENDOJ | Una alternativa podía aportar resoluciones mientras `total_fuente` seguía siendo cero, tomado de la primera consulta. | En agregados, total desconocido (`null`), total inicial separado y totales individuales en traza. No se suman resultados que podrían solaparse. Las continuaciones conservan consulta y posición propias. |

- Antes de corregir: las cuatro nuevas pruebas reproducían cinco fallos
  (incluidas las dos variantes DOGV).
- Después: **148/148 pruebas**, sin fallos ni omisiones, en 2,556 s.
  Se conservan las 140 originales y se añaden ocho pruebas.
- Cobertura nueva: fecha BOE rechazada sin red, relaciones DOGV en castellano
  y valenciano, exclusión del número 11 al buscar 1, exclusión de menciones
  sin relación expresa, total agregado CENDOJ y continuación de la alternativa.
- Segunda revisión GLM: **ACEPTADA, sin bloqueantes**. El revisor reprodujo
  sin red el rechazo BOE previo a conexión, las coincidencias y exclusiones
  DOGV y la continuación CENDOJ de la alternativa (`inicio=10`, total 25).
  La suite completa fue ejecutada por el agente principal, no por el revisor.

## Cierre

Se completaron **dos ciclos** (de un máximo de cinco). Se conservan únicamente
las cuatro correcciones reproducidas y verificadas, sus ocho pruebas nuevas,
la entrada unitaria con bloqueo de red y la documentación de uso.
Ejecución final tras el dictamen GLM: **148/148 pruebas en 2,601 s**, sin
fallos ni omisiones. `git diff --check` no detectó errores en los cambios
rastreados.

Limitación preexistente observada por GLM y no incluida en estas correcciones:
el localizador admite la entrada castellana `Decreto ley 1/2021` y reconoce
títulos valencianos `Decret-llei`, pero esa forma valenciana como consulta de
entrada sigue sin estar admitida por `reference()`. No se afirma que la
revisión sea exhaustiva.

## Uso y compatibilidad

- BOE: no enviar `fecha` a `juridico_buscar`; para los filtros de última
  actualización usar `boe_buscar(desde=..., hasta=...)`.
- CENDOJ: los clientes deben admitir `total_fuente=null` en una búsqueda
  agregada y consultar `traza_busqueda`/`continuaciones`. No existe un total
  global verificado de las distintas estrategias.
- Durante la revisión local no se cambió la versión publicada ni se publicó
  o desplegó el código.

## Mejora posterior · Vocabulario normativo compartido

- Implementación delegada a `deepseek-desarrollo` y auditoría independiente
  de `glm-revision`: **ACEPTADA, sin bloqueantes**, en un ciclo.
- Parser y detector de referencias múltiples comparten vocabulario. Se
  rechazan segundas referencias `decret`, `ordre`, `resolucio` y
  `decreto legislativo` que antes se absorbían como contexto.
- Cuatro pruebas nuevas conservan las once formas de entrada soportadas,
  los rechazos anteriores y el contexto sin una segunda referencia numerada.
- Verificación del orquestador: **152/152 pruebas**, sin red. Las firmas
  de las 14 herramientas MCP y las dependencias permanecen intactas.
- Se mantiene la limitación de `Decret-llei` como referencia inicial.
  No se realizaron despliegues.
