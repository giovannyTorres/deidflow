# BMX-06: pipeline textual real

Base: `ed3287b`. Estado: pruebas focalizadas; revisión independiente pendiente.
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

Pendiente revisión independiente.

## Spec

Pendiente revisión independiente.
