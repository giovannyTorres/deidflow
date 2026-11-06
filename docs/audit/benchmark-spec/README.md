# Procedencia de la proyección documental

Esta entrega parte de `master` en `44d04b1` y proyecta documentación del commit
`f2e4751d280a100e5af450337d70db78a8fefa03` conservado en
`benchmark/evaluacion-mx-spec-tickets`.

El [índice de revisión](../../benchmark-mx/README.md) distingue el estado actual
de los estados históricos. Los 27 tickets siguen siendo borradores locales;
esta entrega no crea issues ni publica dependencias nativas en GitHub.

## Qué se conserva y qué se adapta

La especificación congelada y los 27 cuerpos de tickets se copian byte por byte.
También se conservan el manifiesto `tickets.json`, su índice, la otra
especificación, el glosario, la ADR y el recibo operativo. El
[manifiesto de proyección](projection-manifest.json) registra los hashes de estas
34 copias exactas.

Los 14 registros Markdown de `docs/audit/` que permiten seguir las actas de los
tickets se incluyen como documentos históricos. Se añade un aviso de procedencia
y se fijan al commit original los enlaces cuya evidencia no se copia. Esos
enlaces se validan contra objetos Git locales; no se afirma haber accedido al
servicio remoto. Los hashes, fechas, conteos y aprobaciones dentro de las actas
describen exclusivamente la implementación histórica que allí se identifica.

No se copian módulos Python, pruebas, corpus de ejemplos ni reportes JSON
voluminosos. No se alteran dependencias, workflows o funciones del producto.

## Validación de esta entrega

La evidencia local está en [validation.json](validation.json). Se comprueban:

- SHA-256 congelado de la especificación.
- Los 27 hashes de cuerpos declarados en `tickets.json`, así como los 34 archivos
  de copia exacta frente al commit original.
- JSON de los manifiestos y del recibo; 27 IDs únicos y cero issues registrados.
- Destinos y fragmentos locales de enlaces Markdown añadidos; destinos de los
  permalinks históricos contra el árbol Git del commit fijado.
- Ausencia de cambios fuera de `docs/` y ausencia de Python nuevo.
- Limpieza del diff mediante `git diff --check`.

No se ejecuta la suite completa para esta entrega documental. La validación
local no es un resultado de CI. La auditoría externa de Claude y la aprobación
de Giovanny siguen pendientes; cualquier hallazgo o hilo deberá resolverse.

El [cuerpo preparado para la futura PR](PR_BODY.md) registra el commit de alcance
y las cuatro condiciones de incorporación. Su existencia no acredita
publicación, auditoría ni merge.
