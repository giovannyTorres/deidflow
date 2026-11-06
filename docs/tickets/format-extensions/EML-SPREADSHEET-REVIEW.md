<!-- deidflow-format:EML-SPREADSHEET-REVIEW -->
# EML: separar la revisión de adjuntos de su cobertura incompleta

**Gestor:** GitHub Issues de `giovannyTorres/deidflow`.
**Estado:** borrador no publicado; sin número ni URL de issue verificados.
**Implementación:** pendiente; preparar este cuerpo no modifica el lector.
**Origen comprobado:** `claude/opendocument`
`abb960187911d803b36a019db1775fd045f71f09`, que contiene `master` `44d04b1`.

## Problema reproducido

Una hoja ODS ficticia completa produce una candidata `REVIEW_REQUIRED`, como
corresponde. Si se conserva dentro de un correo, la relectura de EML propaga
cada incidencia del adjunto mediante `_issue`, que marca incompleta la cobertura
del mensaje. Así `ODS_REVIEW_REQUIRED` se convierte accidentalmente en
`INCOMPLETE_COVERAGE` y el correo acaba `BLOCKED`, sin salida publicada.
El mismo mecanismo merece una regresión para adjuntos XLSX de revisión obligatoria.
Es un bloqueo conservador, no evidencia de fuga ni aprobación de privacidad.

Reproducción local desde la rama indicada, usando exclusivamente su fixture
ficticio existente:

```python
import runpy
from email.message import EmailMessage
from pathlib import Path
from tempfile import TemporaryDirectory

from deidflow import DeidEngine, Policy

make_ods = runpy.run_path("tests/test_opendocument.py")["make_ods"]
with TemporaryDirectory() as directory:
    root = Path(directory)
    sheet = make_ods(root / "source.ods")
    message = EmailMessage()
    message.set_content("Adjunto.\n")
    message.add_attachment(
        sheet.read_bytes(),
        maintype="application",
        subtype="vnd.oasis.opendocument.spreadsheet",
        filename="source.ods",
    )
    source = root / "source.eml"
    source.write_bytes(message.as_bytes())
    result = DeidEngine(country="ES").deidentify(
        source,
        output=root / "safe.eml",
        policy=Policy.strict(require_ner=False),
    )
    print(result.status, result.issues)
```

Observado: `BLOCKED`, `EMAIL_REVIEW_REQUIRED`, `ODS_REVIEW_REQUIRED`,
`EMAIL_ATTACHMENT_REVIEW_REQUIRED`, `INCOMPLETE_COVERAGE`, sin archivo emitido.
No se envía ningún mensaje ni se realiza una conexión externa.

## Comportamiento esperado y aceptación

- [ ] Mantener separadas las incidencias de revisión y la señal de cobertura
  completa/incompleta del adjunto. Una incidencia obligatoria de revisión no
  demuestra por sí sola que falten canales inspeccionados.
- [ ] Un adjunto completo que necesita revisión propaga `REVIEW_REQUIRED` al
  correo y conserva sus incidencias; no pasa a `APPROVED` por esta corrección.
- [ ] Un adjunto con cobertura realmente incompleta no consigue aprobación por
  tratar sus incidencias como revisión. Mantener retirada de adjuntos bloqueados,
  bloqueo de bytes retenidos no inspeccionados y comprobación de residuos.
- [ ] Preservar presupuestos MIME, límites de recursión/tamaño, tipos canónicos,
  nombres opacos, ámbito de seudónimos y análisis del archivo adjunto real.

## Pruebas exigidas

- [ ] Correo ficticio con ODS saneado y completo: adjunto retenido, MIME canónico,
  nombre `adjunto-1.ods`, revisión obligatoria y ausencia de `INCOMPLETE_COVERAGE`
  causada únicamente por `ODS_REVIEW_REQUIRED`.
- [ ] Caso análogo con XLSX y `XLSX_REVIEW_REQUIRED`, sin omitir sus canales ocultos.
- [ ] Medio/parte realmente no inspeccionado, adjunto bloqueado y correo anidado:
  cada estado sigue propagándose sin crédito de éxito para contenido retirado.
- [ ] Candidata con residuo sensible: sigue bloqueada; la corrección no crea una
  excepción sintáctica para marcadores ni permite omitir el reescaneo.

El caso ODS depende del soporte ODT/ODS integrado y auditado. Mantener este cambio
separado de [BMX-14b](../benchmark-mx-extensions/BMX-14b.md), que evaluará los
artefactos reales mediante un inspector independiente. No se incorpora al
manifiesto congelado de los 27 tickets ni se implementa en el PR documental.

El PR de corrección debe indicar `Auditoría Claude: pendiente`. Fusionar solo con
CI 11/11 en verde, ningún hallazgo bloqueante de Claude abierto, todos los hilos
resueltos y aprobación de Giovanny. La API de GitHub está bloqueada aquí: estos
archivos son cuerpos preparados, no issues creados ni revisiones resueltas.
