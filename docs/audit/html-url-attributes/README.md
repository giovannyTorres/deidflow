# HTML: conservar URL y atributos (H3/H4)

Código: `ad9d72abb8bd4b9914385039840678846c1876a5`. Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`. Rama: `fix/html-url-attributes`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1105 pasan; 11 omitidas; 280.90 s |
| Cobertura combinada | 84.11 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 1.321104 ms/registro; ratio 3.223469; recall crítico 1.0 |
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
python -m pytest -q --basetemp=/var/tmp/deidflow-html-url-attributes-review-tests --cov=deidflow --cov-branch --cov-fail-under=78 --cov-report=json:/var/tmp/deidflow-html-url-attributes-coverage.json
python scripts/benchmark_micro.py --check --output /var/tmp/deidflow-html-url-attributes-micro.json
python -m build --no-isolation --outdir /var/tmp/deidflow-html-url-attributes-dist
python -m twine check --strict /var/tmp/deidflow-html-url-attributes-dist/*
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

H3/H4 tienen ciclos rojos/verdes reales. La revisión detectó pérdida de texto en referencias sin punto y coma; cinco casos adicionales comprueban prefijos conocidos, numéricos y desconocidos. El test adversarial usa una URL de 210.071 caracteres y límite de tres segundos. Las URL cambiadas de más de 1 MiB fallan cerradas antes de crear el mapa; las URL sin cambios conservan sus bytes. HTML mantiene su estado de revisión existente.

La suite definitiva se ejecutó sobre el SHA final indicado, sin cambios de archivos durante la ejecución. También los estáticos, el build y las pruebas específicas del wheel usan ese código.
