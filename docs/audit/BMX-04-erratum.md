# BMX-04: fe de erratas de la referencia RFC genérica

Corrección de referencia incorporada durante BMX-10, el 2026-11-06 UTC.
No se modifican los validadores, detectores ni dependencias de producción.

La referencia inicial confundía rechazo del RFC completo con fallo del
checksum. En `python-stdnum 2.2`, `is_valid(..., validate_check_digits=True)`
rechaza los dos RFC genéricos por el componente de homoclave antes de comparar
el último dígito. Para comprobar únicamente ese atributo se ejecutó
`stdnum.mx.rfc.calc_check_digit` sobre el prefijo sin el último carácter:

| Constante de facturación | Dígito calculado | Dígito presente | Checksum ordinario |
| --- | --- | --- | --- |
| `XAXX010101000` | `4` | `0` | inválido |
| `XEXX010101000` | `0` | `0` | válido |

`XEXX` pasa de referencia `invalid` a `valid` para checksum. Ambos siguen como
distractores no personales y conservan patrón/estructura declarados para estas
constantes de facturación; una regla de aceptación estricta de stdnum no
reemplaza esa clasificación contextual. No se consultaron expedición,
titularidad ni registros, y no se deduce invalidez jurídica de los genéricos.

El ejemplo actual `examples/benchmark-mx-validation` es versión `1.0.1`, con
referencia `mx-checks-1.0.1` y manifest SHA-256:
`18d82a70ff0ae27a66e40da7bdf8f0220f14065d93f839e93250c73394ab007e`.
Su recurso `evidence-1` conserva los 16 vectores y añade las observaciones
separadas de dígito ordinario y aceptación completa.

La prueba pública primero falló porque la fila publicada de `XEXX` todavía
decía `invalid`; después de la corrección pasan las 27 pruebas focalizadas de
`tests/test_benchmark_validation.py`. La pista real completa 16 vectores y
registra seis acuerdos y una discrepancia RFC de checksum, correspondiente a
`XAXX`. PHONE mantiene patrón/estructura desconocidos y checksum no aplicable.
Los logs red/green, la comprobación stdnum de los 13 valores correspondientes y
el informe real quedan en `/tmp/deidflow-batch/BMX-10/xexx-*` y
`/tmp/deidflow-batch/BMX-10/validation-reference-1.0.1/`.

Se preservan sin reescritura el [recibo inicial](BMX-04-vectors.json), el
[acta inicial](BMX-04.md) y los recibos de salud históricos. Esos documentos
describen la versión `1.0.0`, cuyo manifest era
`22d591766e2659784145aeac953131dd3cb6bd83a93a2fbdbce3d94c641bd67a`;
su afirmación sobre dos checksums genéricos inválidos queda corregida por esta
fe de erratas. Los resultados anteriores no se presentan como reejecutados.
