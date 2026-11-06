# OpenDocument: documentación y preparación de revisión

Auditoría Claude: pendiente

Código heredado: `claude/opendocument`
`abb960187911d803b36a019db1775fd045f71f09`.
Base `master`: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
La comprobación `git merge-base --is-ancestor origin/master HEAD` pasa: la rama
ya contiene ese master. No se reescribió su historia ni se añadió otro merge.
Este incremento modifica documentación y cuerpos de tickets; no modifica código,
pruebas, dependencias, modelos o versiones de paquete.

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
