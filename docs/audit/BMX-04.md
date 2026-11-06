# BMX-04: validez de identificadores con referencia independiente

Estado: implementación focalizada y dos revisiones verificadas; integración final pendiente.
Código revisado: `5393abe64bde30c3cbf7218c9056d16ff46c856f`.
Base: `c95967f67014d39cc9c1050ef8d594de2aa70daf`.
Ticket: [BMX-04](../tickets/benchmark-mx/04-validez-independiente.md).
Contrato/uso: [pista de validez](../BENCHMARK_MX_VALIDATION.md).

TDD: módulo inexistente falló primero; candidato malformado falló antes de
añadir la frontera; dos configuraciones sin estado fallaron antes de añadir
`UNSUPPORTED`. Las variantes de referencia adicionales ya pasaban al añadirse.
Se corrigió un offset del constructor de fixtures al comprobar que el segundo
valor extraído no era el mismo: la frase de contexto mide 21 caracteres, no 20.

26 pruebas nuevas y 151 anteriores pasan: **177 focalizadas**. Ruff y mypy
pasan (71 módulos). Logs en `/tmp/deidflow-batch/BMX-04/`. Suite completa y
empaquetado quedan para la integración final del lote.

La comprobación independiente real se registra en [este recibo](BMX-04-vectors.json):
13 casos contrastados con python-stdnum 2.2, CLABE por términos y suma 28.
Incluye forma física/moral, genéricos, checksum alterado, fechas imposibles,
truncado, formato y checksum no aplicable. No se copió un algoritmo de producción
para usarlo como único oráculo ni se consultó titularidad/registro alguno.

Se preserva una discrepancia real: RFC genéricos, checksum ordinario estricto
frente a excepción del candidato. No se rebautiza como fallo de detección ni
se altera el candidato o la referencia para producir acuerdo perfecto.
Referencia sensible/distractor se mantiene explícita, incluso con igual valor
inválido. Todo el material es fixture conocido; no evaluación ciega.

## Standards

Revisor independiente `/root/batch04_standards`: 0 hallazgos iniciales/finales,
peor severidad ninguna. Verificó localmente ejemplo, canario en excepción,
referencias inválidas, offsets booleanos y sanitización, sin editar código.

## Spec

Revisor independiente `/root/batch04_spec`: 0 hallazgos iniciales/finales,
peor severidad ninguna. Contrastó ticket/AC-04 y ejecutó los 16 vectores: dos
discrepancias RFC declaradas y PHONE sin denominador aplicable. Sin scope creep.

No se modifica API de producción, algoritmos evaluados, dependencias ni versión.
No se ratifican D1–D3. Los formatos obligatorios de primera versión se acordaron
como todos los previstos incluido OCR; los ajustes D1–D3 siguen pendientes.
