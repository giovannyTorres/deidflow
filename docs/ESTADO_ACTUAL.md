# DeidFlow: estado del proyecto

DeidFlow ya cuenta con una biblioteca Python funcional para detectar y transformar
datos sensibles de manera local, con Ã©nfasis en espaÃ±ol y formatos mexicanos.
Conserva API, CLI, validadores de RFC/CURP/CLABE, seudonimizaciÃ³n mediante HMAC,
procesamiento tabular por lotes y OCR Tesseract 5.5.4 en espaÃ±ol e inglÃ©s. La
inferencia utiliza recursos instalados en el equipo, sin modelos generativos,
servicios de pago ni envÃ­o de documentos a servicios de IA.

El avance principal de v0.3 es que ahora existe evidencia pÃºblica independiente
de sus capacidades y lÃ­mites. En MEDDOCAN, corpus clÃ­nico espaÃ±ol con
identificadores artificiales y anotaciones humanas, el F1 exacto de las reglas
subiÃ³ de 24.33% a 50.89%; la mejora persiste al separar artÃ­culos de origen. El
recall exacto actual es 40.22%. Sin embargo, los 250 documentos evaluados todavÃ­a
conservan caracteres sensibles sin detectar. En los 127 documentos judiciales
ingleses de TAB, el F1 exacto fue 0.0. Estos resultados impiden afirmar que el
sistema anonimiza automÃ¡ticamente cualquier expediente o documento.

La eliminaciÃ³n de contenido en PDF reconstruye pÃ¡ginas desde pÃ­xeles nuevos,
verifica las mÃ¡scaras y vuelve a examinar el resultado. El nuevo exportador RAG
produce un PDF, un JSONL y una auditorÃ­a con aprobaciÃ³n conjunta. El JSONL se
obtiene del PDF efectivamente transformado. Mantiene pÃ¡ginas, lÃ­neas y relaciones
entre fragmentos; las tablas con celdas combinadas o continuidad entre pÃ¡ginas
siguen sin reconstrucciÃ³n fiable y pueden exigir revisiÃ³n.

En rendimiento, las 100 pÃ¡ginas nativas tardaron 75.31 segundos con ocho
trabajadores, frente a 155.49 con uno en la corrida actual y 94.02 en la
reproducciÃ³n de v0.2. Las 2,000 regiones sensibles conocidas quedaron cubiertas,
aunque el estado final siguiÃ³ siendo revisiÃ³n por incertidumbre del OCR. Las 100
pÃ¡ginas escaneadas continuaron bloqueadas por hallazgos residuales. Las pruebas
tabulares revisan todas las celdas sensibles esperadas y preservaciÃ³n de importes;
los resultados completos y sus condiciones estÃ¡n en `PERFORMANCE.md`.

TambiÃ©n estÃ¡n implementados el conector Gmail de solo lectura, la aprobaciÃ³n
individual de adjuntos, informes agregados y una interfaz de anotaciÃ³n local con
autenticaciÃ³n y consentimiento. Solo se probaron datos ficticios: no se accediÃ³ a
Gmail, credenciales ni documentos privados reales. La ejecuciÃ³n privada queda a
cargo del usuario en un entorno externo a Codex.

El proyecto tiene una base tÃ©cnica verificable para evaluaciÃ³n supervisada. La
publicaciÃ³n como soluciÃ³n lista para producciÃ³n sigue pendiente: faltan mayor
cobertura en documentos reales, evaluaciÃ³n privada autorizada y una licencia
pÃºblica de uso definida. La licencia actual reserva los derechos del titular.
El cÃ³digo, los datos originales y los artefactos permanecen locales; no se ha
publicado ni enviado cÃ³digo a un repositorio remoto.
