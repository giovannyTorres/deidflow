# Revisión de ramas para 0.6

Inventario inicial: 24 ramas remotas, con `master` en
`f99cfce64a1a233f818caa6aef8efd1cc937277b`. La consolidación anterior está
registrada en [estado del proyecto](ESTADO_ACTUAL.md). Esta revisión conserva
los cambios concurrentes incorporados durante el desarrollo del producto.

Durante la validación apareció y se integró `claude/es-general-2` mediante #30,
con `master` avanzando a `f4199078d93b5b349afb1ce8c27baef7c82b5240`.
La comparación controlada mantuvo los textos, reglas y política anteriores:
el modelo nuevo mejoró privacidad y conservación de contexto en las regresiones,
sin perder identidad ni relaciones en los 40 casos fijos. Se adoptó con nuevos
pins y versiones `general@1.1.0` y `legal@1.1.0`; los pins antiguos no se
redirigen silenciosamente. Las mediciones finales constan en
[evidencia del producto](PRODUCT_EVIDENCE.md).

| Ramas | Resultado |
| --- | --- |
| `master` | Base actual; se conserva su historia. |
| `claude/es-general-tagger` | Incorporada mediante #25; pesos y métricas reproducidas, sin reentrenamiento silencioso. |
| `claude/html-text-output`, `claude/linear-markup-patterns` | Incorporadas mediante #26 y #29; se añaden controles de atributos, CSS y cobertura con regresiones adversariales. |
| `claude/eml-output`, `claude/eml-messages` | Incorporadas mediante #28; el código final de `eml-messages` ya coincide con la base. Se añaden límites MIME, decodificación estricta y procedencia de metadatos regenerados. |
| `claude/latam-addresses` | Incorporada mediante #27; se corrigen límites parciales, contexto de medidas y selección de intervalos. |
| `claude/xlsx-review-fixes` | Incorporada mediante #24; se conservan criterios y fórmulas compartidas corregidas. |
| `claude/docx-output`, `claude/xlsx-output`, `claude/pan-hispanic-identifiers`, `claude/leak-target-profiles`, `claude/v0.4.0-apache-tagger` | Ya consolidadas en la base; se mantienen formatos, identificadores, modelos, perfiles y Apache-2.0. |
| `claude/audit-anonymization-metrics-57htz7`, `fix/release-approval-gates`, `fix/v0.3.1-release-evidence`, `integrate/reviewed-branches` | Revisadas en la consolidación anterior; se mantienen las correcciones de cobertura y liberación y se amplían sesiones, identidad y evaluación. Las afirmaciones históricas no sustituyen evidencia nueva. |
| `dependabot/github_actions/actions/setup-python-7`, `dependabot/pip/pandas-3.1.0` | Las versiones compatibles ya están incluidas en la base. |
| `dependabot/pip/google-auth-2.62.1`, `dependabot/pip/preshed-3.0.15` | #21 y #22 incorporadas al archivo activo de constraints de Windows; son las mismas versiones instaladas y auditadas en la integración. |
| `dependabot/pip/polars-2.1.0`, `dependabot/pip/polars-runtime-32-2.1.0` | #19 y #23 requieren una migración conjunta: cada PR aislado rompe la correspondencia exacta entre Polars y su runtime. Se conserva la pareja compatible 1.44.2. |
| `dependabot/pip/mypy-2.4.1` | #20 es una migración mayor del verificador. Se conserva la versión 1.20.2 que verifica esta entrega; no mejora por sí misma el producto ni la detección. |

Los detalles y SHAs de las cinco propuestas de dependencias están en
[el registro estructurado](dependabot-branch-review.json). Los snapshots históricos
de dependencias se conservan como evidencia; el archivo de constraints activo sí
se actualiza. Las propuestas mayores quedan pendientes de una validación específica.

No se borran ramas ni se sustituyen modelos por el mero hecho de tener una fecha
más reciente. La revisión evalúa comportamiento, compatibilidad y evidencia.
