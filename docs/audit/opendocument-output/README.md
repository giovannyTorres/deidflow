# OpenDocument: escritor y MIME, preparación dependiente

Código: `96f3b252814a9b2edcd39ef4f1fbab45aaada155`. Base: `a29183c9d43327bf978f168b66dfcf693d92b72f`. Rama: `feat/opendocument-output-preparation`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1267 pasan; 11 omitidas; 293.94 s |
| Cobertura combinada | 84.76 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 0.589351 ms/registro; ratio 1.649555; recall crítico 1.0 |
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
python -m pytest -q --basetemp=/var/tmp/deidflow-opendocument-output-review-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/var/tmp/deidflow-opendocument-output-coverage.json
python scripts/benchmark_micro.py --check --output /var/tmp/deidflow-opendocument-output-micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-opendocument-output-dist
python -m twine check --strict /var/tmp/deidflow-opendocument-output-dist/*
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

## Preparación dependiente y alcance

**No abrir un PR de esta rama contra master mientras el lector no esté integrado.** Base de revisión: `feat/opendocument-reader-review` (`a29183c`, código `9324215`). Después de integrar y auditar ese prerrequisito, actualizar mediante merge de master y volver a verificar el candidato. No se reescribió historia ni se fusionó nada en master.

El escritor comparte el recorrido/XML y la cuadrícula del lector; sus 42 funciones compartidas permanecen iguales. Se añadieron rutas de salida y MIME, normalización de errores de lectura ZIP limitada al formato ODF, y correcciones para conservar párrafos, comentarios, cuadros de texto y anclas. Los callbacks confiables quedan fuera de la normalización de errores de entrada. El preflight binario reutiliza la clasificación del lector antes de operaciones destructivas; no se considera completo un blob a partir de sus cadenas legibles.

Las dos P2 de la revisión interna se reprodujeron en rojo y quedaron corregidas: ubicación binaria sin soporte y pérdida de contexto auxiliar en celdas. Las 128 aserciones originales y 12 decoradores/casos se conservan; no se relajaron oráculos. Los 188 casos focalizados pasaron y las dos aperturas reales de LibreOffice que se habían excluido de esa corrida sí se ejecutaron dentro de la suite final.

ODS conserva su revisión obligatoria. El adjunto ODS retenido en EML todavía bloquea la salida por una limitación anterior; existe un borrador separado para corregir esa propagación. No se presenta como entrega funcional de adjuntos ODS. BMX-14b también es un borrador documental, no un issue de GitHub creado.

Tamaño: 1.617 líneas Python cambiadas frente al lector, contando comentarios/blancos/helpers/pruebas y sin excluir fixtures. La guía aproximada se aplica preservando las regresiones de privacidad y contexto. Las variables de hilos solo controlaron las comprobaciones; no son cambios persistentes. Las métricas son regresión ficticia de desarrollo, no calidad profesional o anonimato acreditados.

Borradores reproducibles: [BMX-14b](../../tickets/benchmark-mx-extensions/BMX-14b.md) y [revisión de adjuntos de hojas](../../tickets/format-extensions/EML-SPREADSHEET-REVIEW.md). No son issues remotos.

La [reproducción completa del wheel sin extras](REPRODUCE_WHEEL.md) contiene el programa exacto del smoke específico; también se ejecutó desde stdin con `-I` para comprobar las instrucciones publicadas.
