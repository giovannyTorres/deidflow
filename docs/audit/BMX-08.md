# BMX-08: clausura, similitud y exposición

Base: `25a5c0f`. Estado: pruebas focalizadas; revisión independiente pendiente.
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

Pendiente revisión independiente.

## Spec

Pendiente revisión independiente.
