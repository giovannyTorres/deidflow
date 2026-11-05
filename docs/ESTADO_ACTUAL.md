# DeidFlow: estado del proyecto (v0.4.0)

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
- **Corpus financiero.** Se implementó el cargador del corpus multilingüe de
  Gretel (Apache-2.0, documentos financieros sintéticos con unas 4,600 piezas en
  español). No se pudo ejecutar porque el entorno no tenía acceso a Hugging Face;
  los pasos están en `PUBLIC_CORPORA.md`.
- **Entrega a producción.** CI en Linux, Windows y macOS con Python 3.11 a 3.13,
  umbral de cobertura, prueba del wheel sin dependencias opcionales, flujo de
  release con SBOM, sumas SHA-256 y atestaciones de procedencia, publicación en
  PyPI opcional mediante trusted publishing, Dependabot, `SECURITY.md` y
  `CONTRIBUTING.md`.

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

El proyecto tiene una base técnica verificable para evaluación supervisada. La
publicación como solución lista para producción sigue pendiente: faltan mayor
cobertura en documentos reales, evaluación privada autorizada y una licencia
pública de uso definida. (Resuelto en 0.4.0: licencia Apache-2.0.)
El código se publicó únicamente en GitHub el 3 de noviembre de 2026 como
versión experimental, con la licencia actual de derechos reservados. No se
publicó en PyPI. Los documentos originales y los conjuntos privados permanecen
fuera del repositorio.
