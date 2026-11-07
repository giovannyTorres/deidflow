# Cierre integrado posterior de BMX-12 Unicode

Preparación: **no es un PR del lote completo contra master**. Código y helpers medidos: `12e9d061debc1a13452ee384e8c4e7b0a664471b`; la suite corrió en `a5ae62104e3ea7850987905c58eab8439c77d459`, que solo añade el recibo documental. La comparación H1/H2 conserva su SHA y sus motores fijados originales.

| Comprobación | Resultado |
| --- | --- |
| Suite completa | 1.413 pasan, 11 omitidas; 346,04 s |
| Cobertura combinada | 85.41 %; supera 78 % |
| Ruff / formato / mypy | Pasan; 278 archivos formateados, 83 módulos revisados |
| pip check | Pasa |
| Microbenchmark ficticio de CI | Pasa; 0.363246 ms/registro; ratio 0.783756; recall crítico 1.0 |
| Build y twine estricto | Pasan; artefactos del git archive limpio del código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI, ambas recetas, admisión independiente y reportes pasan; cero intentos de red |

## Intermitencias observadas

Se conservan dos ejecuciones previas de desarrollo. La primera tuvo dos fallos en pruebas de tiempo de direcciones, cuyo código de producción y pruebas son idénticos a master. Esas dos pruebas pasaron aisladas con cobertura en 8,66 s. La siguiente ejecución tuvo un timeout del caso nativo CLONE_UNTRACED: conservó todas las capacidades en falso y no acreditó custodia. El caso pasó aisladamente, con cobertura y en 25 repeticiones. No se demostró un defecto de auditoría ni se modificó su código.

La ejecución definitiva, coordinada sin carga de otras comprobaciones durante la fase sensible y con BLAS en un hilo, pasó todas las pruebas. **No se cambiaron aserciones, presupuestos ni límites de producción**. El [recibo](integration-health.json) conserva hashes de los logs previos y del final; los logs completos permanecen privados en `/tmp/deidflow-bmx-final-evidence/`. La intermitencia del entorno se mantiene como riesgo para observar en CI. Las once omisiones corresponden a integraciones OCR/spaCy/pytesseract sin activos opcionales configurados.

## Comandos reproducibles

Con las dependencias ya instaladas, sobre el código indicado y destinos nuevos:

```sh
export PYTHONPATH="$PWD/src"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.12 src/deidflow scripts/compare_bmx_unicode.py scripts/_bmx_unicode_worker.py
python -m pip check
python -m pytest -q --basetemp=/var/tmp/deidflow-bmx-unicode-quiet-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/tmp/deidflow-bmx-final-evidence/coverage.json
python scripts/benchmark_micro.py --check --output /tmp/deidflow-bmx-final-evidence/micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-bmx-review-dist
python -m twine check --strict /var/tmp/deidflow-bmx-review-dist/*
```

Las cuatro variables solo controlaron estos procesos de comprobación; no son cambios persistentes de la nube. No se puntuó el banco de test independiente. El corpus sintético llamado `test` por el microbenchmark antiguo es una regresión conocida de CI, ajena al banco reservado DF-EVAL-MX. No se publicaron datos personales, release ni artefactos en PyPI.

La entrega sigue necesitando los incrementos fundacionales en master y después dos extensiones separadas: recetas/admisión y comparador/evidencia. Cada futuro PR mantiene sus cuatro condiciones: CI real 11/11, ningún hallazgo bloqueante de Claude, hilos resueltos y aprobación de Giovanny.
