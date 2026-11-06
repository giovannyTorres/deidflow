# BMX-07: aislamiento local y límites

Base: `a82b1c4`. Estado: implementada y revisada; integración final pendiente.
Código revisado: `e8032793468f87fd399dddf65eb8db3332ba9afd`.
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

Revisor `/root/batch07_standards`: 1 infracción P1 y 2 juicios P3 iniciales.
El P1 reprodujo hijo CLONE_UNTRACED con socket no observado; prueba pública
roja/verde y rechazo de integridad para clone/clone3, ptrace e io_uring. Se
centralizaron montajes runtime y se tiparon mediciones de admisión. Revalidó
seis probes nativos: limpio completo, clone ordinario registra socket y las
otras cuatro rutas retiran acreditación. Final: 0 pendientes en ambas clases.

## Spec

Revisor `/root/batch07_spec`: 2 P2 iniciales, ambos corregidos con pruebas
rojas/verdes y revalidados: RLIMIT_NOFILE hard=64 antes impedía el informe;
ahora completa sin elevar límites. JSON 50 000 niveles antes invalidaba arnés;
ahora es MALFORMED_RESPONSE con soporte conservado. Final: 0 pendientes.

Salud: **230 pruebas focalizadas**, incluidas 16 nativas de esta tarea sin
omisiones en este host, Ruff/formato y mypy75 pasan. Logs en
`/tmp/deidflow-batch/BMX-07/`. Corrida limpia: 1 documento/3 menciones de
soporte, 0 intentos, 0 eventos de integridad, custodia acreditada únicamente
para esa ejecución y su referencia declarada. No acredita calidad.
Suite completa y wheel siguen pendientes de integración final.
