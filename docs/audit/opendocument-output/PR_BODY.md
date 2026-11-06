**Plantilla para un futuro PR después de integrar el lector; no enviar ahora contra master.**

Agrega el escritor ODT/ODS y el adaptador MIME sobre el lector revisado, preservando contexto y fallando cerrado ante estructuras no soportadas. Preparación dependiente: no abrir un PR contra master hasta integrar el lector.

Auditoría Claude: pendiente

SHA de código: `96f3b252814a9b2edcd39ef4f1fbab45aaada155`. Base: `a29183c9d43327bf978f168b66dfcf693d92b72f`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1267 pasan; 11 omitidas; 293.94 s |
| Cobertura combinada | 84.76 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.589351 ms/registro; ratio 1.649555; recall crítico 1.0 |
| Wheel y sdist; twine estricto | Pasan; build del SHA de código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI y reproducción específica pasan; cero intentos de red |

Comandos, alcance, hashes y límites: [README de auditoría](https://github.com/giovannyTorres/deidflow/blob/feat/opendocument-output-preparation/docs/audit/opendocument-output/README.md) y [health.json](https://github.com/giovannyTorres/deidflow/blob/feat/opendocument-output-preparation/docs/audit/opendocument-output/health.json) en `docs/audit/opendocument-output/`. Evidencia exclusivamente ficticia de desarrollo; cero ejecuciones del test independiente. Sin nuevas dependencias, modelos, cambio de API pública ni publicación.

Comandos ejecutados: `python -m ruff check .`; `python -m ruff format --check .`; `python -m mypy --python-version 3.12 src/deidflow`; `python -m pip check`; `python -m pytest -q --basetemp=… --cov=deidflow --cov-branch --cov-fail-under=78`; `python scripts/benchmark_micro.py --check`; `python -m build --no-isolation`; `python -m twine check --strict`; smoke del wheel sin extras y reproducción específica fuera del checkout. Las rutas completas se documentan en el acta.

Revisión interna Matt: Standards 0 pendientes; Spec 0 pendientes. No es aprobación de Claude.

- [ ] CI 11/11 verde.
- [ ] Ningún hallazgo bloqueante de Claude abierto.
- [ ] Todos los hilos resueltos.
- [ ] Aprobación de Giovanny.

Base de revisión actual: `feat/opendocument-reader-review` (`ec3dd3f`, fuente `9324215`). El lector aún no está en master; esta rama sigue siendo preparación. ODS requiere revisión y el adjunto ODS retenido en EML sigue bloqueado por una limitación documentada. El ticket BMX-14b está redactado; la API bloqueada impide crearlo como issue.

El cambio mantiene las 128 aserciones y 12 decoradores originales; 1.617 líneas Python cambiadas con helpers/comentarios/pruebas, sin exclusiones. El escritor conserva y transforma el contexto auxiliar, bloquea ubicaciones binarias no soportadas y normaliza únicamente errores de entrada ZIP. No intercepta errores de callbacks confiables.
