# BMX-05: transformación aislada y conservación

Base: `f391e5a` (cierre incremental BMX-04). Estado: código y pruebas focalizadas;
revisiones independientes pendientes, integración completa al final del lote.
Contrato: [uso y límites](../BENCHMARK_MX_TRANSFORMATION.md).

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

Pendiente revisión independiente Matt Pocock.

## Spec

Pendiente revisión independiente ticket/AC-06/AC-08.
