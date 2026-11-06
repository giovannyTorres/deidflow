# BMX-06: pipeline textual real

Base: `ed3287b`. Estado: implementada, revisada y verificada en integración BMX-03–08.
Código revisado: `4d95eb85f9638776ed513e64371e5a8cd93eacf5`.
Guía: [contratos y límites](../BENCHMARK_MX_PIPELINE.md).

TDD: 10 pruebas fallaron primero por módulo inexistente. La comprobación del
contrato real detectó que `Result.findings` son residuales: la prueba de TP=1
falló (0) antes de observar el scan original separado. Dos expectativas del
test se ajustaron a las claves existentes de métricas/nulos, sin cambiar el
contrato BMX-03. Se verifica además mutación de sufijo sin excluir soporte.

Se ejecuta `deidentify_text` real, preservando estados y todas las salidas
observables. Candidatos controlados bloquean todo, emiten el original bajo los
cuatro estados, duplican un identificador, falsean mapas, alteran un sufijo o
fallan. Los límites L/N..(L+U)/N son empíricos; aprobados inexistentes dan null.
El caso integrado observado retira 2/2 menciones de referencia (una anidada),
conserva 34/34 caracteres requeridos y produce 2/2 éxitos conjuntos. Detección
original: TP=1, FP=0, FN=1 (F1=2/3), distinto de los residuales vacíos del motor.
Todo es ficción conocida, no calidad profesional ni test ciego.

La observación de métricas documentales remitida desde la revisión BMX-05 se
aborda aquí. Sin datos reales, red, cambios de producción ni dependencias.

## Standards

Revisor `/root/batch06_standards`: 0 infracciones documentadas y 2 juicios P3
iniciales. Se extrajo selección/resolución compartida y se tipó observación
documental; confirmó 0 pendientes y sin nuevos hallazgos en el delta final.

## Spec

Revisor `/root/batch06_spec`: 1 P1 y 3 P2 detectados en dos pasadas.
Se corrigieron mediante pruebas rojas/verdes: artefactos textuales secundarios
ignorados, salida perdida ante mapas None, capacidades obligatorias ignoradas
y conservación incompleta al agregar varias salidas. Revalidó los cuatro: 0
pendientes. Confirmó con 17 tests y caso de negación: 0/1 contexto, 32/34
caracteres retenidos, 2 sobretransformados, conformidad FAIL. No se publican
máscaras internas ni nombres de artefacto.

Salud: **214 pruebas focalizadas**, Ruff/formato y mypy74 pasan. Logs en
`/tmp/deidflow-batch/BMX-06/`. Suite completa y wheel al integrar el lote.

Integración final completada: 1314 pruebas pasan, 11 omisiones de activos
opcionales, Ruff/formato/mypy, microbenchmark y wheel base verificados.
[Acta integrada](BATCH_NEXT10.md) y [recibo de salud](BATCH_NEXT10_HEALTH.json)
prevalecen sobre las notas históricas de integración pendiente de este paso.
