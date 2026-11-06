# Revisión documental de DF-EVAL-MX

Esta rama presenta la especificación, 27 borradores de tickets y la decisión
operativa para revisar su incorporación por PRs pequeñas. **Esta entrega solo
añade documentación. La implementación del benchmark no forma parte de esta PR
ni está incorporada a su base `master` (`44d04b1`).**

La fuente conservada es el commit
[`f2e4751d280a100e5af450337d70db78a8fefa03`](https://github.com/giovannyTorres/deidflow/tree/f2e4751d280a100e5af450337d70db78a8fefa03)
de `benchmark/evaluacion-mx-spec-tickets`. Los estados «implementado», las
casillas satisfechas, los resultados y las revisiones presentes en los documentos
copiados describen esa rama histórica. No acreditan la nueva proyección ni las
futuras PRs extraídas. `tickets.json` se conserva como manifiesto histórico; este
índice establece el alcance actual.

Hay **27 borradores locales y cero issues de GitHub creados o verificados**. Los
IDs BMX no son números de GitHub. La publicación y las dependencias nativas siguen
pendientes del acceso disponible a la API; no se ha realizado ninguna operación
remota para preparar esta rama.

## Documentos de revisión

- [Especificación congelada DF-EVAL-MX](../specs/BENCHMARK_MX_SPEC.md): SHA-256
  `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.
- [Evaluación oficial MX](../specs/EVALUACION_OFICIAL_MX.md) y
  [glosario](../GLOSSARY.md).
- [27 borradores y manifiesto de hashes](../tickets/benchmark-mx/README.md).
- [ADR operativa BMX-09](../adr/0001-bmx-09-operational-profiles-v1.md) y
  [recibo de decisión](operational-decision-v1.json). La decisión operativa no
  ratifica umbrales de calidad ni aprueba una implementación.
- [Plan de PRs y dependencias reales](PR_SPLIT_PLAN.md).
- [Procedencia y validación de esta proyección](../audit/benchmark-spec/README.md).

## Estado y condiciones de incorporación

La especificación y los 27 cuerpos de tickets mantienen sus bytes y hashes
originales. Los registros de implementación necesarios para sus enlaces se
incluyen con un aviso histórico; la evidencia voluminosa y los módulos ausentes
se consultan mediante enlaces fijados al commit original.

No hay resultados nuevos de CI ni auditoría externa de Claude acreditados por
este índice. Cada PR, incluida esta entrega documental, requiere antes de merge:

1. Los **11/11 checks de CI** de su commit actual: nueve combinaciones de
   sistema/Python, paquete y dependencias.
2. Auditoría externa de **Claude** del commit que se propone incorporar.
3. Todos los hilos y hallazgos de revisión **resueltos**.
4. **Aprobación explícita de Giovanny** para esa PR antes del merge.

La evidencia histórica, un resultado local o una revisión de otra rama no
sustituyen ninguna de estas cuatro condiciones.
