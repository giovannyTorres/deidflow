# Índice de entrega y comprobaciones locales

Corte: 6 de noviembre de 2026. Cada enlace fija una revisión concreta; las ramas
indican dónde se publicó la entrega. Este índice no acredita incorporación en master.

## Entregas disponibles

Los conteos corresponden a suites distintas: **no se suman**. La cobertura es la
combinada de sentencias y ramas; los recibos conservan el detalle y los hashes.

| Entrega | Rama y revisión; acta con comandos | Pasan / omitidas | Cobertura y recibo |
| --- | --- | ---: | --- |
| Unicode H1/H2 | [fix/unicode-detection · d05f807](https://github.com/giovannyTorres/deidflow/blob/d05f807f8d7e4fd6d2c25e42443a9603e09eb1d0/docs/audit/unicode-normalization/README.md) | 1227 / 11 | [84.21 %](https://github.com/giovannyTorres/deidflow/blob/d05f807f8d7e4fd6d2c25e42443a9603e09eb1d0/docs/audit/unicode-normalization/health.json) |
| HTML H3/H4 | [fix/html-url-attributes · 8996689](https://github.com/giovannyTorres/deidflow/blob/8996689b956d4343fbbd4d1643f7e39ac1ac0780/docs/audit/html-url-attributes/README.md) | 1105 / 11 | [84.11 %](https://github.com/giovannyTorres/deidflow/blob/8996689b956d4343fbbd4d1643f7e39ac1ac0780/docs/audit/html-url-attributes/health.json) |
| CSV H5, [PR #32](https://github.com/giovannyTorres/deidflow/pull/32) | [codex/csv-review-20261106 · 12a5cd7](https://github.com/giovannyTorres/deidflow/blob/12a5cd7d1837a1e0db15f6bc974f727dc2a6a933/docs/audit/csv-review-h5/README.md) | 1127 / 11 | [84.10 %](https://github.com/giovannyTorres/deidflow/blob/12a5cd7d1837a1e0db15f6bc974f727dc2a6a933/docs/audit/csv-review-h5/health.json) |
| Especificación y tickets | [benchmark/spec-review · 52c9a10](https://github.com/giovannyTorres/deidflow/blob/52c9a1026eee6d9110d935f12c02c464286a25f7/docs/audit/benchmark-spec/README.md) | Sin suite: solo documentos | [Validación documental](https://github.com/giovannyTorres/deidflow/blob/52c9a1026eee6d9110d935f12c02c464286a25f7/docs/audit/benchmark-spec/validation.json) |
| EMAIL BMX-01 | [benchmark/email-review · 1f7f3e2](https://github.com/giovannyTorres/deidflow/blob/1f7f3e219a442ae842d81a26c7c2382ebc5ce7a7/docs/audit/benchmark-email/README.md) | 1102 / 11 | [84.09 %](https://github.com/giovannyTorres/deidflow/blob/1f7f3e219a442ae842d81a26c7c2382ebc5ce7a7/docs/audit/benchmark-email/health.json) |
| Recetas Unicode BMX-12, preparación | [benchmark/unicode-recipes-preparation · 2a8c9ba](https://github.com/giovannyTorres/deidflow/blob/2a8c9bae5ea6aad46556a7be20fe00d486a5568c/docs/audit/BMX-12-unicode-development/INTEGRATION_CHECKS.md) | 1413 / 11 | [85.41 %](https://github.com/giovannyTorres/deidflow/blob/2a8c9bae5ea6aad46556a7be20fe00d486a5568c/docs/audit/BMX-12-unicode-development/integration-health.json) |
| Lector ODT/ODS | [feat/opendocument-reader-review · ec3dd3f](https://github.com/giovannyTorres/deidflow/blob/ec3dd3f6ee1e1409bcee1956be911b9d20022f64/docs/audit/opendocument-reader/README.md) | 1169 / 11 | [84.18 %](https://github.com/giovannyTorres/deidflow/blob/ec3dd3f6ee1e1409bcee1956be911b9d20022f64/docs/audit/opendocument-reader/health.json) |
| Salida ODT/ODS y MIME, preparación | [feat/opendocument-output-preparation · eb52dfb](https://github.com/giovannyTorres/deidflow/blob/eb52dfb4f57794e4728b5db5905c0bdc8dd631a2/docs/audit/opendocument-output/README.md) | 1267 / 11 | [84.76 %](https://github.com/giovannyTorres/deidflow/blob/eb52dfb4f57794e4728b5db5905c0bdc8dd631a2/docs/audit/opendocument-output/health.json) |

Los SHA de código medido son distintos de algunos cierres documentales:
Unicode `3de9d73`; HTML `ad9d72a`; CSV `1681389`; EMAIL `a888f72`;
BMX `12e9d06`; lector `9324215`; salida `96f3b25`. Los recibos fijan los SHA completos.
Los comandos fuente están en las actas enlazadas y sus `PR_BODY.md`; BMX usa
`INTEGRATION_CHECKS.md`. Los reproductores del wheel están en ambas actas ODF.
Las siete ramas con código pasaron Ruff, formato, mypy, `pip check`, el
microbenchmark con límites, build, Twine y smoke del wheel sin extras;
los recibos delimitan cada ejecución y sus excepciones opcionales.
Las once omisiones de cada suite dependen de integraciones o activos opcionales;
no cuentan como pruebas aprobadas ni como una matriz remota de CI ejecutada.

## Qué acredita la evidencia

Las revisiones Matt de Standards y Spec fueron internas. No son auditorías de
Claude, aprobación del propietario ni resultados de CI remoto.
El scoring del banco de test reservado fue **cero**; las regresiones ficticias
conocidas y los microbenchmarks de CI no acreditan adopción, anonimato ni calidad profesional.

Unicode conserva igualdad exacta de tipos y offsets de predicciones frente a
master `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29` en sintético de validación y
MEDDOCAN **dev**, con las configuraciones documentadas. [Comparación y pins](https://github.com/giovannyTorres/deidflow/blob/d05f807f8d7e4fd6d2c25e42443a9603e09eb1d0/docs/audit/unicode-normalization/validation.json).
Gretel **no se ejecutó** por falta de acceso al activo; su aceptación sigue pendiente.
Las seis sondas H1/H2 pasaron de seis salidas `APPROVED` con residuo confirmado
a cero; son regresión ficticia expuesta, no evaluación independiente.
El [recibo BMX](https://github.com/giovannyTorres/deidflow/blob/2a8c9bae5ea6aad46556a7be20fe00d486a5568c/docs/audit/BMX-12-unicode-development/comparison.json) separa detección y transformación con gold suministrado.

## Dependencias y límites abiertos

BMX-12 necesita las bases fundacionales del arnés y su división posterior en
recetas/admisión y comparador/evidencia. La salida ODF necesita que el lector
se integre y supere sus propias condiciones. **Ninguna de estas dos preparaciones
es un PR listo contra master.** El merge lector → preparación no incorpora nada en master.
ODS requiere revisión; un adjunto ODS retenido todavía deja la salida EML `BLOCKED`
por propagación heredada. Su [borrador de seguimiento](https://github.com/giovannyTorres/deidflow/blob/eb52dfb4f57794e4728b5db5905c0bdc8dd631a2/docs/tickets/format-extensions/EML-SPREADSHEET-REVIEW.md)
y [BMX-14b](https://github.com/giovannyTorres/deidflow/blob/eb52dfb4f57794e4728b5db5905c0bdc8dd631a2/docs/tickets/benchmark-mx-extensions/BMX-14b.md) son documentos, no issues creados.
La decisión sobre es-general-3, el default de Narrative, el rescan y la descripción
del producto sigue pendiente. Esta entrega no declara cerrados todos los P1.

## Estado remoto y configuración

Master sigue en `44d04b1`: no hubo merge en master, release ni publicación en PyPI.
Las ramas se publicaron; no se crearon PRs nuevos ni issues, ni se respondieron
o resolvieron hilos. El intento real de GitHub API devolvió `Forbidden`; #32 ya existía.
Los cuerpos `PR_BODY.md` son propuestas para revisión, no prueba de publicación.

El borrador de red `dd547f99-e24e-45d4-a4c9-6fbc48ca9cf2~cecfgdraft_481a8cc0c4f481a3a5c22adb30ebe4e5`
añade acceso a `api.github.com` y `huggingface.co`, conservando el preset existente.
Está guardado, **sin aplicar ni publicar al runtime**; no demuestra acceso efectivo.

Auditoría Claude: pendiente

- [ ] CI real 11/11 del commit propuesto en verde.
- [ ] Ningún hallazgo bloqueante de Claude abierto, con auditoría externa ligada al commit.
- [ ] Todos los hallazgos e hilos resueltos.
- [ ] Aprobación explícita de Giovanny antes de cualquier merge.

## Contrato congelado y siguiente revisión

La [especificación original](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/specs/BENCHMARK_MX_SPEC.md), el [índice de tickets](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/tickets/benchmark-mx/README.md)
y su [manifiesto de hashes](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/tickets/benchmark-mx/tickets.json) permanecen congelados en `f2e4751`.
La [proyección documental](https://github.com/giovannyTorres/deidflow/blob/52c9a1026eee6d9110d935f12c02c464286a25f7/docs/audit/benchmark-spec/projection-manifest.json) conserva 34 copias exactas y 27 borradores.
Las actas históricas describen su propia revisión, no el estado actual de master.
El [plan de división y dependencias](https://github.com/giovannyTorres/deidflow/blob/52c9a1026eee6d9110d935f12c02c464286a25f7/docs/benchmark-mx/PR_SPLIT_PLAN.md) guía la siguiente revisión por incrementos.
