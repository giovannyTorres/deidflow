# Pista de validez local (BMX-04)

La pista compara **por separado patrón, estructura y checksum** con referencia
independiente. No llama al detector ni transforma documentos; un checksum malo
no decide la sensibilidad. Los estados son `valid`, `invalid`, `unknown` y
`not_applicable`. Los últimos dos no cuentan como checksum fallido: se declaran
sus soportes y discrepancias aparte. Sin referencia conocida aplicable,
`accuracy=null` y razón explícita.

```python
from deidflow.benchmarks.validation_runner import run_validation_benchmark

report = run_validation_benchmark(
    "examples/benchmark-mx-validation",
    manifest_sha256="22d591766e2659784145aeac953131dd3cb6bd83a93a2fbdbce3d94c641bd67a",
    candidate="rules.mx",
    profile="validation-descriptive-v1",
    output="/tmp/deidflow-validation-001",  # Nuevo.
)
```

`rules.mx` invoca las APIs `validate_rfc`, `validate_curp`, `validate_clabe` y
`validate_card` existentes. Para PHONE/EMAIL no se implementa un validador nuevo:
patrón y estructura quedan desconocidos y checksum no aplicable. El perfil debe
estar declarado en el paquete, sin ratificación de calidad.

El recurso opcional JSONL `validation_vectors` extiende los roles conocidos del
paquete v1. Cada fila tiene exactamente `vector_id` (`v-<hex>`), `unit_id`,
`entity_type`, `start`, `end`, `mention_id`, `sensitivity`, `validity` y
`provenance`. Los intervalos apuntan al texto original. `validity` contiene los
tres atributos. `provenance` contiene `method` (`independent_reference` o
`independent_worksheet`), `version` y `evidence_ref`: recurso binario local con
hash verificado. Una referencia sensible debe coincidir con su mención y
validez; un distractor no personal no se convierte en gold de detección.
El cargador valida este recurso antes de cualquier candidato, incluso cuando
la ejecución solicitada sea otra pista.

El ejemplo contiene 16 vectores pequeños, completamente ficticios o constantes
genéricas no personales. Se contrastaron 13 con `python-stdnum 2.2` ya instalado
como herramienta de desarrollo. CLABE usa una hoja independiente: prefijo
`00299900000000001`, términos reducidos con pesos 3/7/1, suma 28 y dígito 2.
La variante terminada en 3 falla el checksum. No se añadió dependencia runtime.
La [evidencia de referencia](audit/BMX-04-vectors.json) contiene únicamente
estos fixtures públicos; no es una salida de auditoría para documentos reales.

La referencia v1 comprueba el **checksum ordinario estricto**. Los RFC genéricos
de facturación producen una discrepancia documentada: el checker independiente
rechaza su checksum ordinario y DeidFlow aplica una excepción. El informe
conserva las dos discrepancias; no afirma que los códigos genéricos sean
jurídicamente inválidos ni cambia los validadores para obtener coincidencia.
Los genéricos y el teléfono imposible son distractores no personales explícitos.

`ValidationCandidate(id, source_sha256, validate)` permite un callback local
confiable de `(entity_type, value) -> mapping` de los tres estados. Identidad y
fingerprint son declarados por el caller; no se ejecuta código de los datos.
Una respuesta malformada o excepción produce `candidate_error`, conserva todos
los vectores requeridos y deja las métricas sin puntuación. Errores del dataset
siguen como `INVALID_RUN`; configuración ausente/no soportada como `UNSUPPORTED`.

El informe `df-eval-mx.validation-report.v1` publica conteos, versiones y hashes,
sin valores ni IDs originales. Mantiene campos operativos separados y calidad
`DESCRIPTIVE_ONLY`. Un acuerdo perfecto de validación no prueba titularidad,
expedición, detección completa ni anonimato. Véase [acta BMX-04](audit/BMX-04.md).
