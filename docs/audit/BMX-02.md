# Evidencia de BMX-02

Estado: implementación terminada; revisión independiente y aceptación integrada
pendientes. Fecha: 2026-11-06. Linux / Python 3.12.14.

Ticket: [BMX-02](../tickets/benchmark-mx/02-admision-paquete.md).
Contrato: [paquete local v1](../BENCHMARK_MX_PACKAGE.md).
Base fija: `0e456550de7cd8cc5f3316a028b308a5aff4bd1d`.
Especificación DF-EVAL-MX v0.1.0, SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

El cambio es aditivo al sistema de evaluación. Conserva BMX-01 y las APIs de
producción, no cambia detectores/políticas/transformadores ni dependencias o
versión. Los cambios anteriores de agentes se conservan fuera del ticket.
No se adquirieron datos ni modelos ni se requieren cambios persistentes cloud.

## TDD observado

Paquetes reales en disco desde paquete/candidato/perfil → informe. Los
candidatos locales controlados entran por esa interfaz, sin sustituir clases
o módulos internos.

| Ciclo | Comportamiento | Rojo | Verde del archivo nuevo |
| --- | --- | --- | --- |
| 1 | Paquete y menciones anidadas con detector real | 1 fallo, interfaz inexistente | 1 pasa |
| 2 | Hashes, tamaños, conteos y referencia confiable | 5 fallos | 6 pasan |
| 3 | Versiones, IDs y manifiesto cerrado | 8 fallos | 14 pasan |
| 4 | JSON estricto y Unicode | 10 fallos, otras variantes ya rechazadas | 28 pasan |
| 5 | Fuentes, permisos y exposición | 10 fallos | 38 pasan |
| 6 | Documentos y unidades | 10 fallos, uno del constructor del fixture corregido | 48 pasan |
| 7 | Menciones, perfiles y expectativas | 15 fallos | 63 pasan |
| 8 | Relaciones, linajes, grupos y contradicciones | 17 fallos | 80 pasan |
| 9 | ZIP equivalente sin extracción | 1 fallo; referencias peligrosas ya rechazadas | 88 pasan |
| 10 | Binarios inertes y recursos conocidos | 2 fallos | 90 pasan |
| 11 | Fallos del candidato separados del dataset | 7 fallos | 97 pasan |
| 12 | Panel y capacidades no soportadas | 5 fallos | 102 pasan |
| 13 | Selectores con estado seguro | 2 fallos | 109 pasan |
| 14 | Artefacto validado antes de declarar pista no soportada | 1 fallo | 111 pasan |
| 15 | Operador compatible con la acción requerida | 3 fallos | 115 pasan |
| 16 | Fecha UTC de revisión de permisos obligatoria y conservada | 2 fallos, otras fechas ya rechazadas | 119 pasan |
| 17 | 2100 menciones cruzadas sin matching auxiliar recursivo | 1 fallo con RecursionError | 120 pasan |

Las cinco variantes positivas adicionales (Unicode/CRLF, spans cruzados,
precedencia, derivación y varias unidades) ya pasaron al añadirse; no se
presentan como ciclos rojos. La repetición offline del ejemplo también pasa.
Se añadió además una regresión que exige TP=FP=FN=1 y F1=0.5 con predicciones
duplicadas y límites parciales; ya pasó al escribirse.
**121 pruebas nuevas y las 21 de BMX-01 pasan.** Logs locales:
`/tmp/deidflow-bmx02/`; este acta omite trazas con rutas/canarios ficticios de
fallos intencionales.

## Verificación integrada

Pendientes suite completa con cobertura, microbenchmark, empaquetado y wheel
instalado. Ya pasan Ruff, formato y mypy durante la implementación.
Manifiesto del ejemplo:
`7fd7f5a4808a85b3c73c9561c82b40eb06e91f9dd2e4c8165bc3b7b4bc8ddeb8`.
Métricas observadas: TP=1, FP=0, FN=1, soporte=2; precision=1.0,
recall=0.5, F1=2/3. Calidad `DESCRIPTIVE_ONLY`; fixture conocido, no test ciego.

## Standards

El revisor independiente encontró un P2 en `5434f0c`: el evaluador genérico
calculaba un matching solapado recursivo que no se publicaba y fallaba con
2100 spans cruzados admitidos. No encontró smells Fowler sustantivos.
Peor hallazgo del eje: caída ante entradas admitidas.

Corrección: conteo exacto mediante conjuntos por unidad, sin emparejamiento
solapado auxiliar. La regresión observó RecursionError antes y ahora obtiene
TP=2100, FP=FN=0 con el candidato local controlado. Pendiente confirmación final
del revisor.

## Spec

El revisor independiente encontró dos P2 en `5434f0c`: se permitía `remove` con
operador `keep`, y faltaba una fecha en el contrato de revisión de permisos.
No identificó ampliación injustificada de alcance. Peor hallazgo del eje:
expectativas internamente contradictorias admitidas.

Corrección: compatibilidad explícita acción/operadores y `reviewed_at` UTC
obligatorio. Ambas correcciones tienen ciclos rojos y verdes. Se actualizó el
fixture sintético y su hash para incluir la fecha; no se inventó revisión humana.
Pendiente confirmación final del revisor.

Recuento inicial: Standards 1; Spec 2. No se escoge un peor problema global.

## Límites pendientes

- Admisión no autentica permisos, anotadores o custodia. BMX-08 auditará la
  independencia profunda; aquí se validan relaciones y grupos declarados.
- El recorrido sigue limitado a EMAIL textual. Otros tipos, formatos,
  ambigüedad y cobertura parcial no se puntúan favorablemente.
- Los binarios no se inspeccionan como documentos nativos; recetas y
  expectativas no se ejecutan. No se acredita aislamiento nativo, tiempo
  o RSS duros. Callbacks son código confiable, no una sandbox.
- El fingerprint de un callback es declarado por el caller. No se infiere
  configuración de modelos ni garantía offline de un callback desconocido.
- GitHub Issues sigue sin acceso API verificado; BMX es un ID documental.
  No se inventa número/cierre de issue ni se publica en PyPI.
