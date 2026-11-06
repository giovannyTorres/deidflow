# OpenDocument: lectura y verificación local

Código: `93242156e9cb259a01b6dba66bde7c3000f9c49c`. Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`. Rama: `feat/opendocument-reader-review`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1169 pasan; 11 omitidas; 234.21 s |
| Cobertura combinada | 84.18 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.292130 ms/registro; ratio 0.963359; recall crítico 1.0 |
| Wheel y sdist; twine estricto | Pasan; build del SHA de código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI y reproducción específica pasan; cero intentos de red |

Los once casos omitidos necesitan activos OCR explícitos, un modelo spaCy local o el adaptador opcional pytesseract. No se presentan como aprobados. Solo se ejecutó Linux/Python 3.12.14; la matriz de GitHub sigue pendiente.

Esta evidencia es regresión ficticia de desarrollo. El microbenchmark existente usa su corpus sintético fijo de CI, conocido de antemano; no es el banco independiente DF-EVAL-MX. No se ejecutó ningún conjunto de test reservado, ni se ajustaron modelos, perfiles o umbrales, ni se incorporaron datos personales reales.

## Reproducción

Con las dependencias de desarrollo y extras ya instalados, desde el checkout del SHA de código:

```sh
export PYTHONPATH="$PWD/src"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.12 src/deidflow
python -m pip check
python -m pytest -q --basetemp=/var/tmp/deidflow-opendocument-reader-review-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/var/tmp/deidflow-opendocument-reader-coverage.json
python scripts/benchmark_micro.py --check --output /var/tmp/deidflow-opendocument-reader-micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-opendocument-reader-dist
python -m twine check --strict /var/tmp/deidflow-opendocument-reader-dist/*
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

## Límite de este incremento

Añade lectura y verificación independiente de ODT/ODS; la transformación automática directa sigue devolviendo `UNSUPPORTED` sin crear archivos. La reescritura MIME ODF permanece deshabilitada; los adjuntos no soportados conservan su retirada existente. El siguiente incremento del escritor es preparación dependiente y no se presenta como PR contra master hasta integrar este lector.

Las regresiones públicas cubren texto, atributos, nombres XML y prefijos, límites de profundidad, comentarios/PIs en ambas codificaciones, partes y metadatos ZIP opacos, consumo completo y acotado de DEFLATE, contenido mal ubicado y material binario. Las cadenas legibles de binarios son diagnóstico y nunca acreditan cobertura completa. Los 92 casos focalizados pasaron; la suite completa anterior se interrumpió al encontrar dos P1 y no se usa para acreditar esta entrega. La suite final mide el código corregido.

Tamaño: 1.673 líneas físicas de Python de manera conservadora, contando helpers/imports/aserciones y omitiendo solo 116 líneas de entrada ficticia. Son 1.519 líneas nuevas no vacías ni comentarios, aun incluyendo datos de fixtures; la guía aproximada de revisión se conserva sin omitir casos de privacidad. No se cambió código de salida de DOCX/XLSX ni sus interfaces. Las variables de hilos solo controlan estos procesos de verificación; no son configuración persistente del entorno.
