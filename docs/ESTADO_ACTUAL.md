# DeidFlow: estado del proyecto

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
pública de uso definida. La licencia actual reserva los derechos del titular.
El código se publicó únicamente en GitHub el 3 de noviembre de 2026 como
versión experimental, con la licencia actual de derechos reservados. No se
publicó en PyPI. Los documentos originales y los conjuntos privados permanecen
fuera del repositorio.
