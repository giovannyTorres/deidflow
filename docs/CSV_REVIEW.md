# Revisión supervisada de CSV

`review --format csv` permite preparar un plan, corregir intervalos por celda y
regenerar un CSV desde el original. Reutiliza la revisión de texto, los controles
de liberación y el asignador de marcadores de DeidFlow. No carga modelos
generativos ni envía documentos.

La primera versión acepta un archivo UTF-8 (BOM opcional), separado por comas,
con una fila de encabezados únicos y no vacíos y el mismo número de columnas en
todas las filas. Los límites son 8 MiB de entrada/salida, 1,000 filas de datos,
64 columnas, 10,000 celdas contando encabezados y registros JSON de hasta
16 MiB. Las capacidades se acotan también por los límites agregados de hallazgos
y decisiones. Los archivos y directorios de salida deben ser nuevos.
Cada campo admite como máximo 131,072 caracteres; un límite menor configurado
por otra aplicación mediante `csv.field_size_limit` también puede rechazarlo.

## Preparar el plan

```sh
deidflow keygen clave-revision.bin
deidflow review plan entrada.csv --format csv --pack financial --output plan.json
```

El plan liga los bytes exactos de entrada, dimensiones, política, configuración
del modelo y reglas. Contiene un `ReviewPlan` por celda, incluyendo encabezados
y valores vacíos, con offsets y hashes; no copia nombres de columnas ni valores.
Mantenerlo privado: las coordenadas, longitudes y hashes también revelan
información sobre el documento.

Las coordenadas son índices empezando en cero. `row: 0` identifica los
encabezados; `row: 1` es la primera fila de datos. `column: 0` es la primera
columna. Los offsets `start` y `end` cuentan caracteres Unicode de la celda
original, con fin exclusivo. No son posiciones en el CSV entrecomillado ni bytes.

El revisor debe consultar el original completo y registrar una decisión por
hallazgo. Un cambio de límites se expresa rechazando el intervalo anterior y
añadiendo el correcto. El archivo `decisiones.json` tiene esta forma:

```json
[
  {"row":1,"column":0,"decision":{"action":"confirm","reason":"confirmed","span_id":"IDENTIFICADOR_DEL_PLAN"}},
  {"row":1,"column":2,"decision":{"action":"reject","reason":"false_positive","span_id":"OTRO_IDENTIFICADOR"}},
  {"row":2,"column":2,"decision":{"action":"add","reason":"missed_identifier","start":6,"end":13,"entity_type":"CUSTOMER_ID"}}
]
```

Sustituir coordenadas, identificadores e intervalos por las decisiones del
documento concreto. No hay un comando que confirme automáticamente todos los
hallazgos ni que dé por revisadas las celdas sin detecciones.

## Generar una candidata

```sh
deidflow review apply entrada.csv --format csv --pack financial \
  --plan plan.json --decisions decisiones.json \
  --reviewer-id reviewer-0123456789abcdef \
  --signing-key-file clave-revision.bin --output candidata-001
```

Sin ambas atestaciones humanas, el estado exige revisión. El directorio privado
contiene `candidate.csv`, `receipt.json` y `audit.json`. Una salida bloqueada
puede conservarse como candidata para inspección; nunca recibe el nombre
`approved.csv`. Los errores de formato o verificación pueden impedir producir
un directorio de salida.

## Aprobar y comprobar el archivo final

Después de inspeccionar toda la fuente y las correcciones:

```sh
deidflow review apply entrada.csv --format csv --pack financial \
  --plan plan.json --decisions decisiones.json \
  --reviewer-id reviewer-0123456789abcdef \
  --signing-key-file clave-revision.bin --output aprobada-001 \
  --approve --source-complete

deidflow review verify entrada.csv --format csv --pack financial \
  --output aprobada-001/approved.csv --receipt aprobada-001/receipt.json \
  --signing-key-file clave-revision.bin
```

`--approve` declara la aprobación de esa revisión y `--source-complete` la
inspección de toda la fuente, incluso encabezados y celdas sin hallazgos. Son
atestaciones explícitas; no fuerzan a pasar un control de residuos o de modelo.
Solo un resultado aprobado publica `approved.csv`; los demás usan la ruta de
candidata y código de salida 2. Los errores de configuración/operación usan 3.

El archivo se reconstruye con `csv.writer`, se vuelve a interpretar y se
comprueban sus dimensiones y valores. Antes de publicar se releen los bytes
realmente escritos, se verifica el recibo y se comprueba que la fuente no cambió.
La publicación del directorio completo es exclusiva y atómica. El recibo HMAC
liga fuente, salida, plan, decisiones por coordenada, política, modelo y estado.
Modificar cualquiera de esos elementos invalida la verificación; cambiar
únicamente un estado JSON no autoriza el archivo. HMAC autentica al poseedor de
la clave, no acredita la identidad humana indicada por `reviewer_id`.

Se conservan los valores de las celdas no transformadas, incluidos importes,
comas, comillas y saltos de línea interiores. La serialización exterior se
normaliza a UTF-8 sin BOM y finales de registro CRLF: no se promete identidad
de bytes con el original.

## Identidad y alcance de detección

Todas las celdas comparten un asignador en memoria. Se reservan los literales
de la fuente completa antes de emitir marcadores, para impedir que un token
presente en otra celda se confunda con uno generado. Un mismo valor exacto y
contexto compatible mantiene su marcador en el archivo. No se infieren alias.

Esta revisión ejecuta detección de texto por celda. No reaplica automáticamente
los perfiles de columnas de `DeidEngine.deidentify(csv)`: un nombre o ID sin
etiqueta puede pasar inadvertido al detector. La revisión completa y las
adiciones humanas siguen siendo necesarias, especialmente en columnas que
contienen identificadores. La revisión no establece anonimato ni exactitud
universal. La conservación de contexto se evalúa junto con las fugas.

El alcance inicial es un CSV acotado, sin procesamiento por streaming ni
continuidad cifrada de identidad entre archivos. `--state` y `--key-file` de la
revisión de texto no se aceptan para CSV. Los mapas en memoria no se exportan.
La revisión Unicode no certifica un archivo Excel, PDF, HTML o correo.

## Ejemplo ficticio reproducible

```sh
python examples/csv_review.py --output ejemplo-csv-nuevo
```

El ejemplo construye sus propios datos ficticios y decisiones a partir de una
anotación explícita incluida en el código. Comprueba un intervalo añadido,
conservación de importes, marcadores repetidos, candidata, aprobación y rechazo
de un archivo manipulado. No acepta documentos privados ni constituye una
evaluación independiente de exactitud.
