# Flujo local por línea de comandos

Los ejemplos usan archivos de texto UTF-8. Los modelos se cargan desde el paquete;
ningún comando llama a un LLM ni envía documentos. Instalar el extra `vault` para
las sesiones cifradas. Ejecutar `deidflow domains` para consultar los paquetes y
sus versiones, modelos, licencias y límites.

## Procesar y continuar una sesión

```sh
deidflow keygen clave-sesion.bin
deidflow session create --pack clinical --state sesion-000.df --key-file clave-sesion.bin
deidflow session process entrada.txt --pack clinical --state sesion-000.df \
  --key-file clave-sesion.bin --output lote-001
deidflow session process siguiente.txt --pack clinical --state lote-001/session.df \
  --key-file clave-sesion.bin --output lote-002
```

Cada directorio nuevo contiene el texto candidato, el estado cifrado actualizado,
el grafo y el resultado de verificación. Se publica el directorio completo de
forma atómica; nunca reemplaza otro. Si el procesamiento queda bloqueado, el
comando de sesión no publica una salida. Una candidata pendiente de revisión sí
se conserva de forma privada con su estado explícito.

`--ttl-seconds 3600` en `session create` fija una caducidad absoluta. Continuar
la sesión no reinicia el plazo. Al cargar se comprueban clave, esquema, política
y configuración del modelo. Usar el mismo `--pack`; no es un mecanismo para
cambiar silenciosamente de dominio. El API Python permite seleccionar perfiles,
políticas y adaptadores propios de manera explícita.

La clave contiene 32 bytes aleatorios. Mantenerla fuera del repositorio y separada
del estado. En POSIX se exigen permisos de usuario (`0600`); los archivos nuevos
también reciben permisos privados en Windows. La caducidad aplicada por la API
no borra copias antiguas ni impide descifrar manualmente con una clave conservada.

## Revisar, corregir y aprobar

```sh
deidflow keygen clave-revision.bin
deidflow review plan entrada.txt --pack clinical --output plan.json
```

`plan.json` contiene identificadores de hallazgos, tipos y offsets, sin copiar
valores originales. Un revisor debe comparar esos intervalos con el documento
completo. Crear `decisiones.json` con una decisión por hallazgo y los intervalos
omitidos que encuentre. Ejemplos de la estructura:

```json
[
  {"action":"confirm","reason":"confirmed","span_id":"IDENTIFICADOR_DEL_PLAN"},
  {"action":"reject","reason":"false_positive","span_id":"OTRO_IDENTIFICADOR_DEL_PLAN"},
  {"action":"add","reason":"missed_identifier","start":120,"end":134,"entity_type":"PERSON"}
]
```

Sustituir identificadores y offsets por decisiones reales del documento; no
copiar este ejemplo como aprobación. Los offsets cuentan caracteres Unicode
Python, no bytes. Una confirmación de un hallazgo no demuestra que no existan
otras omisiones. No hay un comando de aprobación masiva automática.

```sh
deidflow review apply entrada.txt --pack clinical --plan plan.json \
  --decisions decisiones.json --reviewer-id reviewer-0123456789abcdef \
  --signing-key-file clave-revision.bin --state lote-001/session.df \
  --key-file clave-sesion.bin --output revision-001 --approve --source-complete
```

`--approve` y `--source-complete` son dos atestaciones explícitas de la persona
revisora. Sin ambas, la salida no queda aprobada. Persisten los controles de
residuos y configuración: estas opciones no fuerzan una aprobación. El
`reviewer_id` es un identificador seudónimo (`reviewer-` seguido de 16–64 dígitos
hexadecimales), no una autenticación de la identidad de la persona.

Con `--state` y `--key-file`, las correcciones conservan el asignador y se
registran en la bóveda y el grafo. La salida contiene `candidate.txt`,
`receipt.json`, `audit.json`, `session.df` y `graph.json`. Sin ambos argumentos
de sesión se realiza una revisión independiente, sin continuidad entre archivos.
Si la revisión detecta un residuo, la candidata se guarda privadamente como
`BLOCKED` para facilitar su inspección; su recibo no autoriza liberarla.

```sh
deidflow review verify entrada.txt --pack clinical \
  --output revision-001/candidate.txt --receipt revision-001/receipt.json \
  --signing-key-file clave-revision.bin
```

La verificación liga exactamente fuente, salida, política, configuración del
modelo y recibo HMAC. No acepta cambiar un estado JSON a `APPROVED`. HMAC
autentica a quien posee la clave; no es una firma pública ni prueba de anonimato.
Una revisión de texto extraído no certifica que su PDF/Office original esté libre
de imágenes, capas, metadatos o partes sin inspeccionar.

## Revisar un CSV

Para un CSV acotado, `review plan/apply/verify --format csv` usa coordenadas de
fila/columna y offsets locales por celda, incluyendo los encabezados. Separa
`candidate.csv` de `approved.csv` y autentica los bytes del archivo regenerado.
El [flujo de revisión CSV](CSV_REVIEW.md) detalla decisiones, límites, comandos y
el ejemplo financiero ficticio. No admite estado de sesión persistente en esta
primera versión; los comandos de texto conservan su comportamiento.

## Relaciones y restauración local

```sh
deidflow session graph --pack clinical --state revision-001/session.df \
  --key-file clave-sesion.bin --output grafo.json
```

Para añadir una relación, crear una lista JSON con `source`, `relation`, `target`
y `evidence_ids`. Los extremos son marcadores emitidos por la sesión; la evidencia
debe incluir menciones de ambos extremos tomadas del grafo. Las relaciones
admitidas y su semántica están en [sesiones](SESSIONS.md).

```sh
deidflow session relate --pack clinical --state revision-001/session.df \
  --key-file clave-sesion.bin --relations relaciones.json --output sesion-relaciones.df
deidflow session restore revision-001/candidate.txt --pack clinical \
  --state sesion-relaciones.df --key-file clave-sesion.bin --output restaurado-local.txt
```

La restauración escribe los originales en un archivo privado nuevo, nunca en
stdout. Tokens desconocidos bloquean la operación. Conservar un grafo sin nombres
no convierte sus relaciones en información anónima.

## Códigos y límites

`0`: operación completada (o documento aprobado, según comando). `2`: revisión,
bloqueo de liberación o recibo inválido. `3`: error de entrada/configuración o
dependencia. Los mensajes de error no incluyen contenido, claves ni rutas.

Límites: texto de 8 MiB, JSON de operación de 4 MiB; la sesión cifrada tiene sus
propios límites de 64 MiB y número de registros. No se sobrescriben archivos.
Para CSV/JSONL/DOCX/XLSX use `deidflow deidentify --pack ...`: esos procesadores
tienen controles de formato propios y no guardan la sesión textual de esta guía.

