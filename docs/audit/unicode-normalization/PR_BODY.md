Auditoría Claude: pendiente

## Problema y comportamiento

H1/H2 permiten omitir identificadores con controles Cf o anchura completa. La
candidata detecta sobre Cf-free NFKC y proyecta a intervalos originales completos.
Las salidas mantienen el texto ajeno a los intervalos; los Cf residuales dentro
de palabras requieren revisión. Los ordinales de direcciones conservan su clase
léxica mediante procedencia, para no interpretar «3 o más» como un piso.

**Borrador: no fusionar. La aceptación de validación NO está cumplida.**

## SHAs y alcance

- Base master: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
- Código probado y revisado internamente: `93ed28cc4b9ee1c8f0d2b9fb3e919f70df3c7140`.
- Commits de código: 37745e4 y 93ed28c; cambios posteriores son documentación.
- 10 archivos de código/pruebas/helper; 931 líneas añadidas antes del handoff.
- Sin cambios de pesos, umbrales, perfiles, dependencias o versión de paquete.
  Los defaults de master se mantienen; no se activa otro pase de transformación.
- Código de reglas versionado `rules-0.7`; planes actuales/calibraciones previos
  se invalidan. Los recibos históricos conservan su verificación.

## Comandos ejecutados y resultados

En el worktree candidato, con el venv de desarrollo existente y PYTHONPATH=src:

```sh
PYTHONPATH=src python -m pytest -q --cov=deidflow --cov-branch \
  --cov-report=term --cov-report=json:/tmp/deidflow-unicode-evidence/coverage.json \
  --basetemp=$(mktemp -d /var/tmp/deidflow-unicode-full.XXXXXX)
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.12 src/deidflow
python -m pip check
PYTHONPATH=src python scripts/benchmark_micro.py --check \
  --output /tmp/deidflow-unicode-evidence/micro.json
```

- Suite completa: **1207 pasan, 11 omitidas**, 335.90 s; una corrida integrada
  en el código fijado. Omisiones por activos opcionales OCR/spaCy ausentes.
- Cobertura: **86.65% sentencias,
  78.64% ramas, 84.25% combinada**.
- Ruff/formato (191 archivos), mypy (65 módulos) y pip check: PASS.
- Microbenchmark: PASS, 0.561 ms/registro;
  ratio 1.388 frente a su referencia.
- Build desde git archive del SHA probado: `python -m build --no-isolation`;
  `python -m twine check --strict dist/*`: PASS. Wheel instalado mediante
  `pip --no-index --no-cache-dir` en venv vacío fuera del checkout: API anterior,
  modelos empaquetados, Unicode y revisión residual PASS. No upload.

TDD y revisión interna Matt Pocock están documentados en la evidencia. No son
la auditoría externa de Claude ni el CI de GitHub. Las pruebas adversariales de
software son regresión ficticia de desarrollo; no son un banco independiente.

## Validación y bloqueo

El [helper de validación](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/scripts/validate_unicode_detection.py) usa
synthetic validation 600/1729 y MEDDOCAN dev 250: una puntuación por configuración,
sin warm-up, sin test/independiente. Se repitió validación entre iteraciones,
sin cambiar modelos, umbrales ni gold; los fallos no se descartaron ni se
rebautizaron como test intacto. Comandos exactos en el acta enlazada abajo.

- Sintético: FP/reglas 268 y FP/general 1090; recall/caracteres y documentos sin
  cubrir iguales a master.
- MEDDOCAN reglas: FP 776→777; recall/caracteres 0.587256 sin cambio.
- MEDDOCAN general balanced: FP 2066→2090; recall/caracteres 0.972887→0.972624;
  documentos sin cubrir 97→99. **No cumple el criterio de no regresión.**
- Gretel train-holdout: **pendiente por falta de activos locales**; no se ejecutó
  ni sustituyó su test. Test/independiente puntuado: **0**.

## Evidencia y condiciones de fusión

- [Acta y reproducción](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/README.md)
- [Validación agregada, modelos/configuraciones y hashes](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/validation.json)
- [Salud local, cobertura y distribución](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/health.json)

La auditoría de Claude sigue pendiente; se solicitan hallazgos con severidad,
reproducción y esperado. No marcar aprobada ni fusionar hasta CI 11/11 verde,
ningún hallazgo bloqueante abierto, todos los hilos resueltos y aprobación de
Giovanny. El incumplimiento de validación también mantiene P1 abierto.
