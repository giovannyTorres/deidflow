Agrega lectura y verificación local de ODT/ODS. La salida automática y la reescritura de adjuntos permanecen sin soporte en este incremento. Preserva la incertidumbre de XML, metadatos binarios y contenedores no inspeccionados.

Auditoría Claude: pendiente

SHA de código: `93242156e9cb259a01b6dba66bde7c3000f9c49c`. Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1169 pasan; 11 omitidas; 234.21 s |
| Cobertura combinada | 84.18 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.292130 ms/registro; ratio 0.963359; recall crítico 1.0 |
| Wheel y sdist; twine estricto | Pasan; build del SHA de código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI y reproducción específica pasan; cero intentos de red |

Comandos, alcance, hashes y límites: [README de auditoría](https://github.com/giovannyTorres/deidflow/blob/feat/opendocument-reader-review/docs/audit/opendocument-reader/README.md) y [health.json](https://github.com/giovannyTorres/deidflow/blob/feat/opendocument-reader-review/docs/audit/opendocument-reader/health.json) en `docs/audit/opendocument-reader/`. Evidencia exclusivamente ficticia de desarrollo; cero ejecuciones del test independiente. Sin nuevas dependencias, modelos, cambio de API pública ni publicación.

Comandos ejecutados: `python -m ruff check .`; `python -m ruff format --check .`; `python -m mypy --python-version 3.12 src/deidflow`; `python -m pip check`; `python -m pytest -q --basetemp=… --cov=deidflow --cov-branch --cov-fail-under=78`; `python scripts/benchmark_micro.py --check`; `python -m build --no-isolation`; `python -m twine check --strict`; smoke del wheel sin extras y reproducción específica fuera del checkout. Las rutas completas se documentan en el acta.

Revisión interna Matt: Standards 0 pendientes; Spec 0 pendientes. No es aprobación de Claude.

- [ ] CI 11/11 verde.
- [ ] Ningún hallazgo bloqueante de Claude abierto.
- [ ] Todos los hilos resueltos.
- [ ] Aprobación de Giovanny.

Este PR habilita solo entrada y verificación: las salidas ODT/ODS directas siguen `UNSUPPORTED`/sin archivo; el escritor y MIME están en una preparación dependiente. 92 casos focalizados y cuatro controles negativos de capacidad protegen ese límite. 1.673 líneas físicas conservadoras con helpers/aserciones, o 1.519 adiciones no vacías ni comentarios incluyendo fixtures; no se eliminó cobertura para ajustar la guía aproximada. Sin cambios de salida de los formatos existentes.
