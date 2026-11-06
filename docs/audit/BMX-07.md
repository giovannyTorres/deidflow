# BMX-07: aislamiento local y límites

Base: `a82b1c4`. Estado: pruebas focalizadas; revisión independiente pendiente.
Contrato: [API, requisitos y límites](../BENCHMARK_MX_ISOLATION.md).

TDD: 10 pruebas fallaron por módulo inexistente antes de implementar. La primera
ejecución detectó intentos AF_UNIX del bootstrap site de Python; se aisló con
`-S`, sin excluir syscalls del candidato ni ocultar el fallo. 10 pasaron tras
ese ajuste. Dos pruebas posteriores verifican capacidad ausente y respuesta
exitosa malformada. Son pruebas de procesos y namespaces reales, no mocks de
sockets. El único mock simula descubrimiento de herramientas ausentes.

El host dispone realmente de bubblewrap, strace y namespaces. Se observó
denegación de referencia fuera de input, socket Python/libc/subproceso incluso
capturado, timeout y ENOMEM bajo RLIMIT_AS; canarios no aparecen en resúmenes.
La carga del programa sucede tras la frontera auditada. Solo se preparan
requisitos persistentes para hosts sin capacidad; no se cambió este entorno.

La API aislada es explícita y separada de callbacks anteriores. No se declara
que una llamada Python arbitraria esté aislada ni que el guard de sockets de
runner.py sea aislamiento nativo. La admisión de píxeles/expansión no se anuncia
como decodificación de formatos futuros. No se añaden dependencias Python.

## Standards

Pendiente revisión independiente.

## Spec

Pendiente revisión independiente.
