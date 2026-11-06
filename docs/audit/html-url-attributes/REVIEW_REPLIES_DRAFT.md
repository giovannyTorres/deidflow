# Respuestas preparadas para H3 y H4 de #31

La API de GitHub está bloqueada por la política de red del entorno. Estas
respuestas no se han enviado ni se han resuelto los hilos. Al crear el PR,
añadir su URL real a cada respuesta y solicitar la auditoría; no inventar IDs.

## H3: URL con escapes porcentuales

Corregido en `ad9d72abb8bd4b9914385039840678846c1876a5`. La vista decodificada
se usa para detectar y validar el esquema. Si el atributo no cambia, conserva
sus bytes originales; si contiene un correo codificado, se proyecta solo su
reemplazo al origen y se conservan los escapes y las entidades circundantes.

La entrada exacta de H3 conserva `%20` y `%26`. Se comprueban también correos
codificados y anidados, UTF-8, esquemas peligrosos, referencias sin punto y coma
y una URL adversarial de 210.071 caracteres. Rojo/verde observado.

## H4: atributo sin comillas

Corregido en el mismo SHA. El atributo sin cambios conserva su codificación;
cuando se reescribe, el valor completo queda entre comillas. La entrada exacta
con `Informe&#32;clínico` deja de bloquearse. HTML conserva su política existente
de revisión. Rojo/verde observado.

## Evidencia común

1.105 pruebas aprobadas, 11 omitidas; estáticos, microbenchmark y wheel sin
extras aprobados. [Acta](README.md) y [recibo agregado](health.json). Evidencia
ficticia de desarrollo, sin puntuación del test independiente. Revisiones
internas Matt: Standards 0 pendientes, Spec 0 pendientes. Auditoría externa,
CI real 11/11, resolución de hilos y aprobación de Giovanny siguen pendientes.
