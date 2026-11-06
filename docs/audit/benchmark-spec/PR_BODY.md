La especificación y los tickets del benchmark están mezclados con una rama de
implementación grande. Esta PR los presenta como una proyección documental para
revisar el contrato, su procedencia y la división en incrementos pequeños.

Commit de alcance documental: `900e3d28281366c422f123fb11af5c93ed5cddb5`.
Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
Fuente histórica: `f2e4751d280a100e5af450337d70db78a8fefa03`, conservada en
`benchmark/evaluacion-mx-spec-tickets`. El commit posterior añade este cuerpo de
PR y actualiza únicamente su evidencia documental; la revisión debe abarcar el
HEAD completo que se publique.

Incluye las especificaciones, 27 borradores locales, ADR/recibo BMX-09, glosario,
[índice de estado](../../benchmark-mx/README.md) y
[plan de PRs con dependencias](../../benchmark-mx/PR_SPLIT_PLAN.md). Las actas
copiadas llevan avisos históricos y enlaces fijados al commit original. Las
afirmaciones de implementación y sus resultados corresponden a esa rama, no a
`master` ni a esta PR. No se han creado o verificado issues en GitHub.

La especificación conserva SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987` y los
27 cuerpos conservan sus hashes de `tickets.json`. El diff solo añade archivos
bajo `docs/`; contiene cero cambios Python, de dependencias, workflows o funciones.

Validación local, detallada en [validation.json](validation.json) y en el
[manifiesto de proyección](projection-manifest.json):

```sh
python /tmp/deidflow-benchmark-spec-validate.py
git diff --check 44d04b1
git diff --name-only 44d04b1 -- . ':!docs'
sha256sum docs/specs/BENCHMARK_MX_SPEC.md
```

Resultados: 34 copias exactas frente a la fuente histórica; 27 hashes de tickets
correctos; 27 IDs únicos y cero issues registrados; JSON válido; enlaces y
fragmentos locales resueltos; destinos de permalinks comprobados contra objetos
Git locales; diff sin errores y sin rutas fuera de `docs/`. El comprobador local
temporal y su SHA-256 quedan identificados en la evidencia. No se accedió al
servicio remoto ni se ejecutó la suite completa para esta entrega documental.

Auditoría Claude: pendiente

Condiciones obligatorias antes de merge, todas pendientes para la PR que se
publique:

- [ ] CI **11/11** del commit actual: nueve combinaciones sistema/Python,
  paquete y dependencias.
- [ ] Auditoría **externa de Claude** ligada al commit propuesto.
- [ ] Todos los hallazgos e hilos de revisión **resueltos**.
- [ ] **Aprobación explícita de Giovanny** antes del merge.

Este recibo no acredita publicación, revisión externa, aprobación ni merge. La
evidencia histórica no sustituye las cuatro condiciones anteriores.
