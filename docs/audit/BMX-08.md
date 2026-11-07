# BMX-08: clausura, similitud y exposición

Base: `25a5c0f`. Estado: implementada, revisada y verificada en integración BMX-03–08.
Código revisado: `4fa622e04f15aa990735eeb7523c98e1394ce6a4`.
Contrato: [auditoría y límites](../BENCHMARK_MX_INDEPENDENCE.md).

TDD: 10 pruebas fallaron por falta del módulo, después pasaron con clausura
iterativa, igualdad original/normalizada, perfil explícito y exposición.
Se añaden dos comprobaciones posteriores de identidad explícita y contrato
de congelación; esta última usa declaraciones ficticias para probar el gate,
no acredita un corpus ciego real ni una identidad/historial autenticado.

La auditoría no altera el texto de puntuación. Los diagnósticos solo publican
conteos/códigos y el hash de configuración; no valores, filenames o gold.
Duplicados, familia compartida y variantes no cruzan particiones; nombres
comunes sin evidencia no fusionan documentos. Perfil ausente o presupuesto
agotado conserva incertidumbre. Exposición conocida/desconocida bloquea blind.

## Standards

Revisor `/root/batch08_standards`: 0 infracciones escritas y 0 juicios
accionables tanto inicialmente como tras el delta de artefactos originales.

## Spec

Revisor `/root/batch08_spec`: 1 P1 inicial por omitir hash binario del artefacto
y agrupar solo hash de fuente textual. La regresión DOCX compartido con textos
extraídos distintos falló (acreditaba independencia); tras agrupar hash de
artefacto no nulo deniega y registra un componente cruzado. Revalidó con su
reproducción original y 13 pruebas propias. Final: 0 abiertos.

Salud: **243 pruebas focalizadas**, Ruff/formato y mypy76 pasan. Logs en
`/tmp/deidflow-batch/BMX-08/`. No se cambian dependencias ni código de producción.
Suite completa y empaquetado se comprobarán en integración final.

Integración final completada: 1314 pruebas pasan, 11 omisiones de activos
opcionales, Ruff/formato/mypy, microbenchmark y wheel base verificados.
[Acta integrada](BATCH_NEXT10.md) y [recibo de salud](BATCH_NEXT10_HEALTH.json)
prevalecen sobre las notas históricas de integración pendiente de este paso.
