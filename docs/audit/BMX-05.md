> **Registro histórico de la rama de implementación.** Este texto describe
> el trabajo conservado en [`f2e4751`](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-05.md),
> no una implementación incorporada a `master` ni una auditoría o CI de esta PR.
> Los enlaces fijados al commit permiten consultar evidencia que no se copia aquí.
> Consulte el [estado de esta revisión](benchmark-spec/README.md).

# BMX-05: transformación aislada y conservación

Base: `f391e5a` (cierre incremental BMX-04). Estado: implementada, revisada y verificada en integración BMX-03–08.
Código final: `16279a048448044669af4ea7558c959e534ba61e`.
Contrato: [uso y límites](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/BENCHMARK_MX_TRANSFORMATION.md).

TDD: 11 pruebas fallaron por falta del módulo antes de implementarlo. Se ajustó
una expectativa del test: la máscara con sufijo visible es fuga atribuible, no
solo incertidumbre; se corrigió el nombre de la excepción del cargador en el
test. La prueba adicional de copia residual falló por no atribuir una copia
literal única con mapa inválido; se incorporó esa comprobación independiente.

Se utiliza `transform_text` real, sin detector y sin modificar producción.
Perfiles explícitos opuestos conservan o retiran contexto clínico ficticio;
eliminar «Niega diabetes; dosis: 5 mg.» reduce retención y éxito conjunto.
Se ensayan original copiado, máscara parcial, mapa falseado, copia residual,
marcador de entrada, solapamientos con precedencia y errores saneados.

La revisión de calidad de los candidatos se mantiene DESCRIPTIVE_ONLY. No hay
datos personales reales, red, ratificación humana ni nuevas dependencias.
La ejecución es callback local de confianza; no constituye aislamiento nativo.

## Standards

Revisor `/root/batch05_standards`: 0 infracciones escritas, 3 juicios P3
iniciales. Se aclararon nombres/coordenadas y eliminaron campos sin uso.
Queda 1 P3 aceptado no bloqueante por verificaciones parecidas a context_quality:
se conservan independientes dadas las diferencias de taxonomía y operadores;
extraer dos comparaciones simples no justifica ampliar este ticket. Un renombrado
afectó por error el prefijo de un literal de bytes; se corrigió antes de push
y se repitieron los checks. Final: 0 infracciones, 1 juicio P3 aceptado.

## Spec

Revisor `/root/batch05_spec`: 2 P2 corregidos con pruebas rojas/verdes:
coincidencias accidentales en placeholder y selección de la intersección de
operadores. Confirmó ambos mediante endpoint público y 14 pruebas propias.
Una observación inicial de métricas documentales/estados se reasignó, de acuerdo
con el revisor, a BMX-06: esa tarea evaluará el pipeline real y sus denominadores
y límites. Final BMX-05: 0 abiertos; no se acredita liberación completa aquí.

Salud: **197 pruebas focalizadas**, Ruff/formato y mypy (73 módulos) pasan.
Logs en `/tmp/deidflow-batch/BMX-05/`. No se ejecutó aún integración completa.

Integración final completada: 1314 pruebas pasan, 11 omisiones de activos
opcionales, Ruff/formato/mypy, microbenchmark y wheel base verificados.
[Acta integrada](BATCH_NEXT10.md) y [recibo de salud](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BATCH_NEXT10_HEALTH.json)
prevalecen sobre las notas históricas de integración pendiente de este paso.
