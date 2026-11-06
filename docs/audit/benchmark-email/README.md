# BMX-01: extracción independiente del recorrido EMAIL

Código: `a888f72ffbb7cbdac165e72ea137ac24315b659a`. Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`. Rama: `benchmark/email-review`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1102 pasan; 11 omitidas; 425.45 s |
| Cobertura combinada | 84.09 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.328373 ms/registro; ratio 1.077028; recall crítico 1.0 |
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
python -m pytest -q --basetemp=/var/tmp/deidflow-benchmark-email-review-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/var/tmp/deidflow-benchmark-email-coverage.json
python scripts/benchmark_micro.py --check --output /var/tmp/deidflow-benchmark-email-micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-benchmark-email-dist
python -m twine check --strict /var/tmp/deidflow-benchmark-email-dist/*
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

Extracción de BMX-01 desde `f2e4751` sin introducir otros módulos del arnés. El módulo ausente produjo un rojo real; tras extraerlo pasaron 21 casos. Cuatro casos adicionales fallaron antes de corregir separadores U+2028/U+2029 dentro de JSONL y rutas de salida inválidas; pasan los 25 casos focalizados. Ejemplo ficticio EMAIL: TP=1, FP=0, FN=0, precision=recall=F1=1.0, `DESCRIPTIVE_ONLY`. No mide transformación, independencia ni aislamiento nativo.
