# OpenDocument: preparación de revisión y correcciones de privacidad

Auditoría Claude: pendiente

## Preparación documental inicial (`662585a`)

Código heredado: `claude/opendocument`
`abb960187911d803b36a019db1775fd045f71f09`.
Base `master`: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
La comprobación `git merge-base --is-ancestor origin/master HEAD` pasa: la rama
ya contiene ese master. No se reescribió su historia ni se añadió otro merge.
Este incremento modifica documentación y cuerpos de tickets; no modifica código,
pruebas, dependencias, modelos o versiones de paquete.

Ese párrafo describe el commit documental inicial `662585a`. Una revisión
posterior encontró residuos aprobados y motivó la corrección separada de código
que se registra abajo; el código original de Claude y su historia se conservan.

## Evidencia local

Desde la raíz de este worktree:

```sh
PYTHONPATH=src /workspace/deidflow/.venv/bin/python -m pytest -q \
  tests/test_opendocument.py \
  --basetemp=$(mktemp -d /var/tmp/deidflow-odf-docs.XXXXXX)
```

Resultado real: **11 pasan, 0 omitidas, 65.87 s**. Hay diez funciones de prueba;
la apertura con LibreOffice está parametrizada para ODT y ODS. Por tanto, no se
reproduce el conteo previo de doce casos en este commit. Ambas aperturas reales
pasaron con LibreOfficeDev `26.8.0.0.alpha0`, build
`2c87e51eeaa2b413ff4ae097b2705eea1995d8e5`, ya disponible en el host; no se instaló
un activo ni una dependencia para esta comprobación.

Son regresiones ficticias de desarrollo: extracción, retiradas/copia del paquete,
contexto de columnas, valores ocultos, repeticiones, fallos de admisión, adjunto
ODT y apertura en el renderer local. No son validación pública independiente,
calidad profesional, anonimato ni evidencia de CI remota.

El recorrido adicional de un correo con un ODS ficticio confirmó **BLOCKED**, sin
archivo emitido y con cero intentos de red bajo la guarda local. Las incidencias
son `EMAIL_REVIEW_REQUIRED`, `ODS_REVIEW_REQUIRED`,
`EMAIL_ATTACHMENT_REVIEW_REQUIRED` e `INCOMPLETE_COVERAGE`. La relectura convierte
una incidencia de revisión del adjunto en cobertura incompleta. Se documenta
esta limitación y se prepara un [ticket separado](../tickets/format-extensions/EML-SPREADSHEET-REVIEW.md);
no se presenta la inscripción MIME como éxito de salida retenida.

Logs y recibos locales: `/tmp/deidflow-opendocument-evidence/pytest.log`,
`source-size.json` y `ods-attachment-blocker.json`. El cuerpo del PR identifica
por separado el SHA del código heredado y el del commit documental.

## Tamaño revisable

La diferencia heredada respecto a master añade 1.327 líneas de producción en
cinco módulos y elimina nueve; añade también 453 líneas de pruebas. De estas,
197 líneas iniciales contienen imports, helpers y datos ficticios antes de la
primera prueba. Contar conservadoramente las 256 líneas restantes completas como
lógica de pruebas da **1.583 líneas añadidas más nueve eliminadas**, excluyendo
solo ese prefijo. No se excluye todo el archivo de pruebas ni se presenta una
cifra artificial inferior a 1.500.

Es un exceso pequeño respecto a la guía aproximada. El corte reúne lectura,
escritura y verificación del mismo recorrido XML, cuyo vínculo debe auditarse
junto. La conveniencia de ese alcance permanece para la revisión; no se editó
el código heredado solo para reducir el contador.

## Publicación y condiciones

[BMX-14b](../tickets/benchmark-mx-extensions/BMX-14b.md) queda preparado fuera del
manifiesto congelado de 27 tickets, con dependencias, aceptación y pruebas por
formato. Ambos documentos son borradores: **0 issues creados**. La API de GitHub
está bloqueada por la política de red; no se inventan PRs, números, aprobaciones
ni hilos resueltos.

La suite completa, cobertura, microbenchmark, wheel y CI 11/11 no se atribuyen a
este paso focalizado. El coordinador incorporará los resultados que efectivamente
ejecute. La fusión exige CI 11/11 verde, ningún hallazgo bloqueante de Claude
abierto, todos los hilos resueltos y aprobación de Giovanny. P1 debe cerrarse y
auditarse antes de release o uso con datos reales. No hubo publicación de versión.

## Correcciones posteriores de privacidad y robustez

La revisión interna posterior encontró residuos aprobados en la documentación
preparada: `style:display-name`, un enlace relativo sin miembro real y un MIME
sintácticamente válido que contenía un identificador. Se corrigieron como una
clase de metadatos retenidos: las etiquetas humanas se transforman; los valores
estructurales se inspeccionan y bloquean si no es seguro reescribirlos; el
manifiesto reconstruido usa tipos XML canónicos. Las referencias de paquete se
resuelven contra miembros reales y directorios implícitos con límites explícitos,
sin alterar la escritura de URI válidas sin cambios.

El siguiente control detectó nombres XML/prefijos sensibles, colisiones de
nombres neutrales y una excepción de recursión no contenida. El inventario ahora
incluye nombres de elementos/atributos y alias de namespace, también atributos
vacíos y XML de metadatos auxiliares. Las sustituciones de nombres reservan los
valores existentes antes de asignar identificadores nuevos. La frontera DOM ODF
limita la profundidad a 128 elementos y convierte agotamiento recursivo en error
sanitizado, sin modificar los helpers OOXML compartidos.

Commits de código de Codex, sin reescribir la rama original de Claude:

- `bfa5aba4831f4bca019fcd2a39ac6f16050e0672`: metadatos, manifiesto y referencias.
- `e9ad1b50547e9978f56dcdf893372570bd7952a7`: formato/imports; AST de producción
  idéntico al anterior, comprobado antes/después.
- `d642c120cb3f94ffd7cc867babbceae9a1297e65`: nombres XML, referencias sin
  colisiones, cobertura de metadatos auxiliares y límite de profundidad.

Evidencia TDD real en `/tmp/deidflow-opendocument-evidence/`:

- `metadata-red.log`/`metadata-green.log`: `APPROVED` con correo en etiqueta de
  estilo pasa a retirada, preservando la definición y su referencia `P1`.
- `href-red.log`/`href-green.log`: un destino sensible sin miembro de paquete se
  desenlaza y el lector declara la referencia sin resolver.
- `variants-red.log`/`variants-green.log`: se preservan espacios URI codificados,
  directorios implícitos y referencias relativas al XML propietario; se rechazan
  separadores codificados ambiguos.
- `manifest-red.log` y el verde focalizado posterior: el identificador en un tipo
  MIME válido sintácticamente ya no se conserva en el manifiesto emitido.
- `qname-red.log`/`qname-green.log`: tres casos aprobados con DNI en alias/nombre XML
  pasan a bloqueo; incluye un atributo de valor vacío.
- `collision-red.log`/`collision-green.log`: dos marcadores distintos conservan
  destinos distintos, en vez de convertirse ambos en `nombre-1`.
- `depth-red.log`/`depth-green.log`: 1.100 spans anidados dejan de exponer
  `RecursionError`; 32 spans siguen funcionando. No hay archivo parcial.
- `metadata-qname-red.log` y el verde final: la verificación independiente del
  archivo tampoco omite el alias sensible de `settings.xml`.

Estos rojos corresponden a estados intermedios reales de trabajo antes de cada
corrección; no se les asigna retrospectivamente el SHA final. El primer bloque
pasó **36 pruebas focalizadas en 57.06 s**, incluidas las once heredadas y las
aperturas LibreOffice, antes de la segunda revisión. Tras las correcciones de
nombres/profundidad, **32 pruebas de privacidad pasan en 2.71 s**. Son corridas
separadas y no se suman como una suite final. No se repitió la suite completa ni
LibreOffice después de esa última revisión; la integración corresponde al
coordinador. Ruff global, formato y mypy Python 3.12 pasan; mypy revisa 65 módulos.

El SHA de cierre de la segunda revisión fue
`d642c120cb3f94ffd7cc867babbceae9a1297e65`. El formato posterior de los tests no
modificó la fuente de producción comprobada. Los logs de estáticos son
`review-ruff-final.log`, `review-format-final.log` y `review-mypy-final.log`.

El tamaño al cerrar `d642c12` frente a master era de **1.474 líneas de producción añadidas y
nueve eliminadas**, más 788 líneas de pruebas. Excluir solo los prefijos de
fixtures/helpers/imports (197 y 61 líneas) deja 530 líneas conservadoras de
lógica/casos de prueba: **2.004 añadidas más nueve eliminadas**, sin contar la
documentación. Supera la guía aproximada; el corte mantiene junto un único
backend lector/escritor y sus correcciones de privacidad. No se minificó código
ni se excluyeron todas las pruebas para aparentar un PR menor. La conveniencia
del alcance queda explícita para la auditoría y la aprobación del solicitante.

Siguen pendientes la auditoría externa de Claude, sus hilos, CI 11/11 y aprobación
de Giovanny. La limitación EML/ODS permanece reproducida y documentada en su ticket
separado. La ampliación del inventario y estos fixtures no prueban anonimato,
compatibilidad semántica universal ni calidad en documentos personales reales.

## Referencia combinada congelada y división de revisión

Fuente autoritativa final: `8cb3c5fc3a3568102620f69931c5990b2a64dba5`. Este
conjunto queda como referencia de preparación; no se presenta como un PR
combinado contra master. Las entregas revisables se prepararán por separado:

1. Lector y verificación independiente ODT/ODS, con salida ODF todavía no admitida.
2. Escritor y MIME existentes, como preparación dependiente de integrar/auditar
   el primer incremento. Se conserva el recorrido XML compartido y la totalidad
   de las aserciones y casos finales, sin rebajar pruebas para reducir tamaño.

La última corrección conserva incertidumbre de los canales originales que el
parser o el escritor retiraban antes de verificar: comentarios/PIs XML, archivos
opacos de configuración/layout, payloads de entradas directorio y metadatos ZIP.
El preflight usa eventos XML antes de retirar nodos, respeta las codificaciones
admitidas y distingue CDATA. No se decodifican payloads opacos. Los comentarios
ZIP y campos extra centrales/locales, nombres locales discrepantes y bytes de
prefijo/sufijo o layouts no acreditados impiden una verificación favorable del
original. Las cabeceras se leen solo para comprobar presencia/coherencia. El
escritor reconstruye un contenedor limpio, que puede verificar completo.

Una última corrección comprueba el consumo de cada flujo comprimido antes de
leer el manifiesto. DEFLATE usa la API pública de zlib con expansión limitada al
tamaño declarado más un byte; comprueba tamaño exacto, CRC y fin de flujo. STORED
exige tamaños iguales y CRC correcto. Un sufijo posterior al bloque DEFLATE
terminal deja incompleta la fuente aunque `zipfile.read` lo omita; el escritor
puede retirarlo al recomprimir un flujo válido. Compresión no admitida, flujo
malformado o expansión discordante no se analizan ni se reescriben como válidos.

TDD adicional: `hidden-xml-{red,green}.log`, `opaque-package-{red,green}.log`,
`zip-metadata-{red,green}.log`, `local-name-red.log` y `deflate-red.log`, seguidos por el verde
focalizado final. Cubre comentarios y PIs en UTF-8/UTF-16, control CDATA, directorio
vacío benigno, extras locales ausentes del catálogo central y controles
`deidentify` → `verify` para cada fuente opaca retirada. También cubre sufijos en
content/manifest y una expansión de 8 MiB declarada como cero, con pico de memoria
inferior a 2 MiB en la lectura pública. Resultado final de esta
referencia: **51 pruebas de privacidad pasan en 1.51 s**. Ruff y formato global
pasan (190 archivos), y mypy Python 3.12 pasa (65 módulos). No se atribuye una
suite completa a esta referencia: el coordinador verificará las ramas extraídas
reales. Logs `deflate-final-focused.log`, `deflate-ruff.log`,
`deflate-format.log` y `deflate-mypy.log`.

Conteo conservador final respecto a `master` `44d04b1`: **1.620 líneas de
producción añadidas y nueve eliminadas**, más 952 líneas de pruebas. Se excluyen
solo los prefijos de fixtures/helpers/imports de 197 y 61 líneas; las 694 líneas
restantes de los tests se cuentan completas, incluidos datos auxiliares dentro
de las pruebas. Total conservador: **2.314 añadidas más nueve eliminadas**, sin
documentación. `privacy-final-size.json` conserva el desglose. Este tamaño motiva
la división en dos incrementos, manteniendo el conjunto como referencia congelada.

El cuerpo de PR combinado previo queda histórico/no presentable; la preparación
de cada PR debe identificar sus propios SHAs, comandos, evidencia y auditoría
pendiente. No hubo acciones remotas, merges ni publicación de versiones en este
trabajo. La auditoría externa de Claude y las cuatro condiciones de fusión siguen
pendientes en cada candidato real.
