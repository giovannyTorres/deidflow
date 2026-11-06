# BMX-11: referencia contextual ficticia y transformación

Incremento acotado sobre `cae4f65a9c2b8598260cf4bf89910a26cfb6e427`, posterior
al cierre de BMX-10. Ticket: [BMX-11](../tickets/benchmark-mx/11-corpus-contextual.md).
Contrato y reproducción: [corpus contextual](../BENCHMARK_MX_CONTEXTUAL.md).

Se entrega un generador instalado con doce casos literales originales: diez
confirmados, 47 menciones y ocho familias; dos desafíos separados con tres
hipótesis ambiguas. Los paquetes contextual y estricto comparten todas las
menciones y difieren en las expectativas clínicas. Guía, referencia y revisión
real de agentes viajan como evidencia hash-bound. El recibo D1–D3 se lee con
pin explícito y se comprueban las acciones D3 aplicables. No hay dependencias
nuevas ni cambios de detección, política o transformación de producción.

Los spans clínicos anidados, los nombres cruzados artificiales y sus límites
se conservan. Homónimos explícitamente distintos mantienen IDs diferentes;
continuidad observable comparte IDs y grupo. La vinculación del alias queda
indeterminada. Se conserva el linaje de la narrativa sin puntos hacia la
narrativa original. Las pruebas adversariales trasladan familia o identidad
vinculada entre particiones y verifican que la auditoría rechaza independencia.

La referencia fue revisada por dos agentes reales distintos antes de medir
al candidato. No se inventan humanos ni se usa `human_review` como método de
procedencia. La anotación sigue siendo un fixture sintético expuesto y no una
muestra de despliegue o banco ciego. Los desafíos no resueltos y la relación
de alias indeterminada permanecen explícitos. Los hashes finales, actores,
fechas y resoluciones están en el
[ledger de referencia](../benchmark-mx/contextual-reference-reviews-v1.json).

La primera revisión resolvió un pin inicial superado por metadatos finales.
Después se detectó un `no` sobrante en la frase de conservación fuera de spans
retirados. Ambos agentes revisaron realmente esa corrección; el coordinador
registró su cierre el 2026-11-06T18:33:21Z. No cambiaron los doce textos,
50 anotaciones, acciones, identidades ni linaje. La guía final tiene SHA-256
`b06b5441e60cd7f1ce8bdda6e1bd1dd264aba4a44cb9a46011e7bbbe44f9bc6e`;
la referencia final,
`4cba8c476195d18c8eb9c1cd666757ead7f061d2483da343143a122ebc5e4a99`.
Se conservan ambas revisiones y la corrección en el historial del ledger.

TDD: otro agente escribió las primeras pruebas del generador y ejecutó un rojo
real por módulo ausente antes de crear el módulo. Ese output se preservó después
desde su transcript, con una advertencia explícita: no existía un log redirigido
original y no se reconstruyó el estado para fabricar uno. El primer recorrido
con fuente pasó 21 pruebas; el baseline ampliado pasó 22. La siguiente prueba
vertical reprodujo cinco faltas reales del validador de revisión: actor repetido,
resultado rechazado, decisión ausente/incorrecta y timestamp sin UTC. Sus logs
red/green registran cinco fallos iniciales y siete checks aprobados después.

Logs originales de esta sesión, en `/tmp/deidflow-batch/BMX-11/`:
`test-absent-module-transcript.txt`, `test-contextual-first-source.log`,
`test-contextual-authored.log`, `test-review-evidence-red.log`,
`test-review-evidence-green.log` y `test-contextual-reviewed.log`.
No se afirma que se siguiera una secuencia TDD perfecta para cada línea.

La [evidencia reproducible](BMX-11-generation.json) conserva el manifest de
cada modo, repetición byte a byte, soporte y resultados sanitizados. Con gold,
transform.text retira los 18 identificadores y conserva las 29 menciones
clínicas en contextual; estricto retira las 47. Ambos logran 10/10 de éxito
conjunto. El desafío conserva REVIEW_REQUIRED y 0/2 éxitos. La prueba que
borra todo pierde negaciones, dosis y relaciones: falla conservación y éxito
conjunto aunque los identificadores desaparezcan.

La detección real rules.mx se ejecutó después de revisar la referencia. Sobre
47 menciones confirmadas reconoce exactamente una PERSON y una MEDICATION;
las omisiones, límites incorrectos y falsos positivos se publican sin ajustar
el candidato ni la referencia. Las tasas de revisión y exclusiones del desafío
se informan aparte. Los IDs de identidad no constituyen una métrica de
consistencia de identidad implementada.

Se mantiene DESCRIPTIVE_ONLY, perfiles técnicos `ratified:false` y recibo
operativo ratificado separado. El objetivo automático/global con ajuste local
sencillo no se convierte en calidad acreditada para estos pocos textos es-MX.
La auditoría no encuentra cruces ni grupos separados; deja NO_BLIND_TEST e
independencia ciega no acreditada. No se ejecuta suite completa, cobertura,
microbenchmark ni wheel en este incremento; corresponden a integración.

Verificación focalizada final: 210 pruebas de corpus, admisión, detección,
transformación, pipeline e independencia. Ruff y formato pasan para el módulo
y sus pruebas; mypy Python 3.12 pasa para el módulo. El target configurado 3.11
encuentra el stub NumPy instalado con sintaxis 3.12, igual que en BMX-10; no se
modificó configuración o dependencia para ocultarlo. Logs `final-focused.log`,
`final-ruff.log`, `final-format.log` y `final-mypy.log` en el directorio temporal
ya indicado. Los tres ejemplos se repitieron byte a byte y se volvieron a medir
con los digests finales después de la corrección de guía.

La revisión fresca de Spec/Standards del código se registrará por el coordinador
después del commit. Este acta no inventa su resultado ni cierra BMX-12.
