# CSV: ámbito común de seudónimos entre celdas (H5)

Código: `16813896250993360610e26bd89b1ed812250dab`. Base: `c49d039f19afd719df4ecee280fcb7fa09268aac`. Rama local: `fix/csv-review-document-scope`; destino remoto existente: `codex/csv-review-20261106` ([PR #32](https://github.com/giovannyTorres/deidflow/pull/32)).

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1127 pasan; 11 omitidas; 436.48 s |
| Cobertura combinada | 84.10 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.336815 ms/registro; ratio 1.124456; recall crítico 1.0 |
| Wheel y sdist; twine estricto | Pasan; build del SHA de código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI y reproducción específica pasan; cero intentos de red |

Los once casos omitidos necesitan activos OCR explícitos, un modelo spaCy local o el adaptador opcional pytesseract. No se presentan como aprobados. Solo se ejecutó Linux/Python 3.12.14; la matriz de GitHub sigue pendiente.

Esta evidencia es regresión ficticia de desarrollo. El microbenchmark existente usa su corpus sintético fijo de CI, conocido de antemano; no es el banco independiente DF-EVAL-MX. No se ejecutó ningún conjunto de test reservado, ni se ajustaron modelos, perfiles o umbrales, ni se incorporaron datos personales reales.

## Reproducción

Con las dependencias de desarrollo y extras ya instalados, desde el checkout del SHA de código:

```sh
export PYTHONPATH="$PWD/src"
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.12 src/deidflow
python -m pip check
python -m pytest -q --basetemp=/var/tmp/deidflow-csv-review-h5-review-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/var/tmp/deidflow-csv-review-h5-coverage.json
python scripts/benchmark_micro.py --check --output /var/tmp/deidflow-csv-review-h5-micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-csv-review-h5-dist
python -m twine check --strict /var/tmp/deidflow-csv-review-h5-dist/*
```

Los destinos deben ser nuevos. El build medido se produjo desde un `git archive` limpio del SHA indicado, antes de este cierre documental. El [recibo agregado](health.json) contiene hashes de artefactos y del log completo local; no contiene textos de entrada ni trazas privadas. Los logs locales permanecen fuera del repositorio.

## Revisiones

Standards: cero infracciones documentadas o smells pendientes. Spec: cero hallazgos pendientes. Son revisiones internas independientes según la skill oficial de Matt Pocock; no sustituyen la auditoría externa de Claude.

## Condiciones pendientes

- [ ] CI real 11/11 en verde.
- [ ] Ningún hallazgo bloqueante de Claude abierto.
- [ ] Todos los hilos resueltos.
- [ ] Aprobación de Giovanny.

`api.github.com` continúa excluido por la política de red aplicada. El borrador de configuración preparado permite ese host; aún necesita publicarse/aplicarse en el entorno. No se afirma que exista un PR nuevo ni que se haya respondido o resuelto un hilo remoto. Sin merge, release, etiqueta ni publicación en PyPI.

## Detalles de evidencia

La reproducción exacta falló antes y pasó después: el mismo correo en dos celdas distintas recibe el mismo token con ámbito de documento. Se comprueban repetición del plan, separación entre documentos, continuidad de ámbitos dataset/tenant/sesión, rechazo de planes obsoletos y recibos alterados. La API pública de revisión textual no expone el nuevo ámbito interno. `merge origin/master` respondió `Already up to date` en la rama de #32; no se fabricó un merge.
