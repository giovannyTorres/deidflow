Auditoría Claude: pendiente

## Resultado y alcance

H1/H2: retirar todos los Cf, aplicar NFKC, detectar y proyectar al intervalo
original completo, preservando el resto del documento. Los Cf residuales dentro
de palabras requieren revisión. La información léxica de ordinales se conserva
como metadato: NFKC sigue siendo la vista de tokenización y coordenadas.

La candidata anterior empeoraba MEDDOCAN. **Esa regresión está corregida.**
Los tipos y offsets de todas las predicciones coinciden con master en validación
sintética y MEDDOCAN dev, con reglas y paquete general. También se comprobaron
el paquete clínico y builtin:auto en MEDDOCAN. No se cambiaron pesos, umbrales,
perfiles, modelos, defaults de Narrative ni pases de transformación.

**Gretel y las condiciones externas siguen pendientes: no fusionar todavía.**

## Código y reproducción

Base master: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
Código probado y revisado internamente: `3de9d732dca9a6df106a757836f0c8194be73916`.
Commits de corrección: 37745e4, 93ed28c y 3de9d73; posteriores, documentación, recibos y el reproductor clínico ejecutado por separado.
Los diffs se limitan a normalización, detección/adaptadores, pruebas y evidencia;
la versión del paquete y las dependencias permanecen intactas.

En el checkout candidato, usando las herramientas de desarrollo instaladas:

```sh
PYTHONPATH=src python -m pytest -q --cov=deidflow --cov-branch \
  --cov-report=term --cov-report=json:/tmp/deidflow-unicode-evidence/continuation/coverage.json \
  --basetemp=$(mktemp -d /var/tmp/deidflow-unicode-fixed-full.XXXXXX)
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.12 src/deidflow
python -m pip check
PYTHONPATH=src python scripts/benchmark_micro.py --check \
  --output /tmp/deidflow-unicode-evidence/continuation/micro.json
```

Resultado: **1227 pasan, 11 omitidas**, 237.84 s; una suite integrada en el código
fijado. Cobertura **86.61% sentencias,
78.60% ramas, 84.21% combinada**.
Omisiones: activos OCR/spaCy opcionales ausentes; no se cuentan como aprobadas.
Ruff, formato, mypy y pip check PASS. Microbenchmark PASS:
0.341 ms/registro, ratio 1.071 frente a referencia de esa corrida.

Build desde git archive del SHA fijado: python -m build --no-isolation y twine
check --strict PASS. Wheel instalado sin extras con pip --no-index --no-cache-dir
fuera del checkout: API anterior, modelos, Cf, anchura completa, revisión residual
y cobertura del piso con NLP puro Python PASS. No hubo upload a PyPI.

## Validación y evidencia

| Corpus/configuración | FP base → candidata | Recall de caracteres | Sin cubrir |
| --- | ---: | ---: | ---: |
| Sintético 600 / reglas | 268 → 268 | 0.428915 → 0.428915 | 600 → 600 |
| Sintético 600 / general | 1090 → 1090 | 0.928963 → 0.928963 | 273 → 273 |
| MEDDOCAN dev 250 / reglas | 776 → 776 | 0.587256 → 0.587256 | 250 → 250 |
| MEDDOCAN dev 250 / general | 2066 → 2066 | 0.972887 → 0.972887 | 97 → 97 |
| MEDDOCAN dev 250 / clínico | 2030 → 2030 | 0.978497 → 0.978497 | 79 → 79 |
| MEDDOCAN dev 250 / auto | 974 → 974 | 0.973164 → 0.973164 | 94 → 94 |

Se verificaron hashes idénticos de predicciones tipadas, no solo conteos. Las
posiciones NLP inciertas (<0.75) de clínico/auto también coinciden. Los hashes
que incluyen score/confianza/contexto y el ECE se registran separadamente;
no se afirma identidad de cada campo numérico ni se recalibraron perfiles.

El helper congelado solo puntúa validación: sintético 600/1729, MEDDOCAN dev o
Gretel train-holdout hash 10%. Se repitió validación tras cambios; **test/banco
independiente puntuado: 0**, warm-up: 0. Los fixtures pytest son regresión ficticia
de desarrollo, no un banco independiente. Gretel acepta únicamente el archivo
train y SHA registrados; su ejecución está pendiente por falta de acceso al activo.

- [Acta, TDD y comandos exactos](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/README.md)
- [Comparación actual y pins](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/validation.json)
- [Salud local y hashes de distribución](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/health.json)
- [Reproductor clínico/auto](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/verify_clinical_routes.py)
- [Recibo fallido anterior, conservado](https://github.com/giovannyTorres/deidflow/blob/fix/unicode-detection/docs/audit/unicode-normalization/history/93ed28c-validation.json)

## Auditoría y fusión

Revisión interna Matt Pocock: Standards 0 infracciones y un juicio P3 no
bloqueante aceptado sobre parámetros de lote; Spec sin defectos de código
pendientes. Esto no sustituye a Claude ni al CI remoto.

Se solicitan hallazgos externos con severidad · reproducción · esperado.
Fusionar solo con CI 11/11 verde, ningún hallazgo bloqueante de Claude abierto,
todos los hilos resueltos y aprobación de Giovanny. Gretel sigue siendo un
criterio de aceptación pendiente. No se borraron ramas, reescribió historia
ajena, modificó #32 ni publicó una nueva versión.
