# DeidFlow: estado del proyecto (candidata v0.6.0b1)

## Producto en español con contexto e identidad

La candidata 0.6 incorpora paquetes clínico, financiero, jurídico inicial y
general; marcadores españoles; sesiones cifradas reanudables; grafos de menciones
y relaciones explícitas; revisión humana con recibos verificables; y
postentrenamiento local con evaluación de regresiones antes de promoción.
Los paquetes y `Policy.context()` exigen revisión humana por código. Todo se
ejecuta localmente, sin LLMs ni servicios de pago, manteniendo Apache-2.0.

La identidad se conserva por valor exacto con contexto compatible, sin adivinar
alias ni unir personas con roles explícitamente contradictorios. Las correcciones
de contexto conservan marcadores de incertidumbre hasta la revisión. El paquete
jurídico usa el modelo general y reglas específicas; no se presenta como un
especialista validado con expedientes jurídicos reales.

El modelo general se incorporó tras reproducir la evaluación publicada en el
PR #25. También se conserva el trabajo concurrente de HTML y correo de los PR #26 y #28,
con controles adicionales sobre sintaxis, atributos, cabeceras y adjuntos.
También se incorporan las direcciones de #27 y el rendimiento HTML de #29,
con correcciones de límites y pruebas adversariales. La
[revisión actual de 24 ramas](BRANCH_REVIEW_v060.md) incluye las decisiones de
compatibilidad de dependencias.
La integración posterior de #30 actualiza el modelo general a su segunda
revisión; los paquetes general y jurídico pasan a 1.1.0, con hash verificado
y comparación sobre los mismos textos de regresión.

Para comprobar la entrega: [contrato de producto](PRODUCT_ACCEPTANCE.md),
[sesiones](SESSIONS.md), [paquetes](DOMAIN_PACKS.md),
[revisión](REVIEW_WORKFLOW.md), [postentrenamiento](POST_TRAINING.md) y
[guía de auditoría](AUDIT_GUIDE.md). Los resultados de regresión y su separación
de evidencia representativa se documentan en [evaluación de contexto](CONTEXT_BENCHMARK.md).
Los registros de versiones anteriores que siguen son históricos.

## Consolidación de las 19 ramas (versión 0.5)

Se revisaron las 19 ramas remotas existentes. La rama principal sigue siendo
`master`; no se renombra ni se crea una publicación de PyPI al integrar código.
La consolidación conserva Apache-2.0, los modelos empaquetados y los perfiles
de v0.4, y añade los controles de liberación corregidos, salida XLSX supervisada,
funciones opcionales de sesión y métricas de auditoría. Las reglas narrativas
adicionales son optativas: no reemplazan silenciosamente los detectores actuales.
El formato cifrado de vault pasa a v2 y rechaza v1; reanudarlo exige su allocator
correspondiente. Los fingerprints de política incluyen el nuevo control de
verificación independiente, por lo que deben revalidarse los recibos previos.

| Ramas revisadas | Decisión de integración |
| --- | --- |
| `master` | Base de la consolidación. |
| `claude/v0.4.0-apache-tagger`, `claude/leak-target-profiles` | Ya estaban incorporadas; se preservan modelos y perfiles. |
| `claude/pan-hispanic-identifiers`, `claude/docx-output` | Sus árboles coinciden con los respectivos merges existentes. |
| `fix/release-approval-gates` | Se incorporan incertidumbre estructurada, bloqueo de partes Office desconocidas y cobertura de medios retenidos. |
| `fix/v0.3.1-release-evidence` | Corrección ya incluida en la rama anterior; se recupera su plan de revisión humana sin volver a la versión 0.3.1. |
| `claude/xlsx-output` | Se integra con controles adicionales y salida siempre supervisada (`REVIEW_REQUIRED`). |
| `claude/audit-anonymization-metrics-57htz7` | Integración selectiva de funciones y métricas; se corrigen controles de sesión/cifrado y se conserva Apache-2.0. No se adoptan sus afirmaciones históricas como evidencia de la versión actual. |
| `dependabot/github_actions/actions/{checkout-7,setup-python-7,upload-artifact-7,download-artifact-8,attest-build-provenance-4}` | Se actualizan las cinco acciones. El release debe esperar los checks del mismo código. |
| `dependabot/pip/{pandas-3.1.0,scikit-learn-1.9.1,pip-26.3}` | Se amplía soporte compatible; las constraints actuales están separadas del snapshot histórico. |
| `dependabot/pip/filelock-4.2.7` | Se utiliza una versión compatible posterior, 4.2.9, sin degradar el entorno. |
| `dependabot/pip/thinc-10.0.0` | No se incorpora: spaCy 3.8 requiere `thinc>=8.3.12,<8.4.0`; se conserva 8.3.14. |

Los snapshots, corpus y resultados anteriores conservan su versión y contexto.
Las nuevas funciones no demuestran que haya mejorado el recall del modelo ni
eliminan la necesidad de evaluación representativa antes de una liberación
automática. El flujo completo de corrección y aprobación humana sigue en el
[roadmap](roadmap.md#supervised-tabular-release-workflow).

## Novedades de la versión 0.4.0

- **Licencia Apache-2.0.** El código ya puede usarse, modificarse y
  redistribuirse, incluso con fines comerciales, conservando `LICENSE` y
  `NOTICE`. Las versiones anteriores reservaban todos los derechos.
- **Etiquetador estadístico propio (`es-clinical`).** Un perceptrón estructurado
  promediado, sin dependencias, entrenado con el corpus público MEDDOCAN
  (CC-BY-4.0). En el conjunto de prueba oficial, evaluado una sola vez, el F1
  exacto sube de 0.509 (reglas v0.3) a **0.958**; la cobertura de caracteres
  sensibles pasa de 53.8% a 96.6%, y las puntuaciones están calibradas
  (ECE 0.008). Se usa con `SpanTagger.builtin("es-clinical")` o
  `--tagger builtin:es-clinical`.
- **Verificación corregida.** Antes, la reverificación volvía a detectar los
  propios marcadores (`Domicilio: [ADDRESS]`) y bloqueaba todo documento real.
  Ahora ignora solo hallazgos formados exclusivamente por marcadores; cualquier
  letra o dígito original sigue bloqueando.
- **Medición de fuga real.** Con reglas + etiquetador, 149 de 250 documentos de
  prueba quedaron `APPROVED`, pero 40 de ellos aún conservaban al menos un
  carácter sensible; con `review_margin=60` se aprueban 76 y 11 conservan algo.
  `APPROVED` no equivale a anonimización garantizada: la revisión humana de
  `REVIEW_REQUIRED` y el muestreo de aprobados siguen siendo necesarios.
- **Modelo financiero (`es-finance`).** Entrenado con el corpus multilingüe de
  Gretel (Apache-2.0, documentos financieros sintéticos; 4,148 en español para
  entrenar y 461 para la prueba). En la prueba, evaluada una sola vez, el F1
  exacto es 0.740 frente a 0.308 de las reglas, y la cobertura de caracteres
  sensibles con reglas + modelo es 83%. Es más difícil que el texto clínico: de
  161 documentos aprobados, 57 aún conservaban algún carácter sensible. También
  se agregó un validador de IBAN con dígito de control.
- **Entrega a producción.** CI en Linux, Windows y macOS con Python 3.11 a 3.13,
  umbral de cobertura, prueba del wheel sin dependencias opcionales, flujo de
  release con SBOM, sumas SHA-256 y atestaciones de procedencia, publicación en
  PyPI opcional mediante trusted publishing, Dependabot, `SECURITY.md` y
  `CONTRIBUTING.md`.

- **Perfiles y enrutador.** `--tagger builtin:auto` elige el modelo clínico o
  financiero por documento. El perfil `assurance`, ajustado en validación para
  que como máximo el 2% de los documentos aprobados filtre un identificador
  directo, logró 1.7% en validación pero 7.7% en la prueba clínica (antes
  10.1%). La meta no se sostiene: hace falta un mejor modelo o revisión humana.

Pendiente: no existe un corpus público anotado con datos mexicanos (CURP, RFC,
CLABE, domicilios mexicanos); para producción en México hace falta un conjunto de
prueba privado anotado con la herramienta local y medir ahí antes de confiar en
cualquier cifra pública.

## Estado heredado de v0.3

DeidFlow ya cuenta con una biblioteca Python funcional para detectar y transformar
datos sensibles de manera local, con énfasis en español y formatos mexicanos.
Conserva API, CLI, validadores de RFC/CURP/CLABE, seudonimización mediante HMAC,
procesamiento tabular por lotes y OCR Tesseract 5.5.4 en español e inglés. La
inferencia utiliza recursos instalados en el equipo, sin modelos generativos,
servicios de pago ni envío de documentos a servicios de IA.

El avance principal de v0.3 es que ahora existe evidencia pública independiente
de sus capacidades y límites. En MEDDOCAN, corpus clínico español con
identificadores artificiales y anotaciones humanas, el F1 exacto de las reglas
subió de 24.33% a 50.89%; la mejora persiste al separar artículos de origen. El
recall exacto actual es 40.22%. Sin embargo, los 250 documentos evaluados todavía
conservan caracteres sensibles sin detectar. En los 127 documentos judiciales
ingleses de TAB, el F1 exacto fue 0.0. Estos resultados impiden afirmar que el
sistema anonimiza automáticamente cualquier expediente o documento.

La eliminación de contenido en PDF reconstruye páginas desde píxeles nuevos,
verifica las máscaras y vuelve a examinar el resultado. El nuevo exportador RAG
produce un PDF, un JSONL y una auditoría con aprobación conjunta. El JSONL se
obtiene del PDF efectivamente transformado. Mantiene páginas, líneas y relaciones
entre fragmentos; las tablas con celdas combinadas o continuidad entre páginas
siguen sin reconstrucción fiable y pueden exigir revisión.

En rendimiento, las 100 páginas nativas tardaron 75.31 segundos con ocho
trabajadores, frente a 155.49 con uno en la corrida actual y 94.02 en la
reproducción de v0.2. Las 2,000 regiones sensibles conocidas quedaron cubiertas,
aunque el estado final siguió siendo revisión por incertidumbre del OCR. Las 100
páginas escaneadas continuaron bloqueadas por hallazgos residuales. Las pruebas
tabulares revisan todas las celdas sensibles esperadas y preservación de importes;
los resultados completos y sus condiciones están en `PERFORMANCE.md`.

También están implementados el conector Gmail de solo lectura, la aprobación
individual de adjuntos, informes agregados y una interfaz de anotación local con
autenticación y consentimiento. Solo se probaron datos ficticios: no se accedió a
Gmail, credenciales ni documentos privados reales. La ejecución privada queda a
cargo del usuario en un entorno externo a Codex.

El proyecto tiene una base técnica verificable para evaluación supervisada.
La preparación para producción sin supervisión sigue pendiente: faltan mayor
cobertura y evaluación independiente representativa del dominio de uso. La
licencia pública quedó resuelta en v0.4.0 con Apache-2.0.
El registro histórico de v0.3 corresponde a la publicación experimental en
GitHub del 3 de noviembre de 2026, con los términos de derechos reservados que
regían entonces; no describe la licencia actual. Los documentos originales y
los conjuntos privados permanecen fuera del repositorio.
