> Actualización de continuación: BMX-09 ratificada y revisada con objetivo
> automático/global/reentrenamiento local fácil; BMX-10 y BMX-11 implementadas
> y revisadas. BMX-12 sigue en ejecución. Las cifras que siguen son el recibo
> histórico de la integración03–08; la continuación se verificará al final.
> [Decisión vigente](BMX-09.md), [BMX-10](BMX-10.md), [BMX-11](BMX-11.md).

# Lote solicitado BMX-03 a BMX-12

**BMX-03 a BMX-08 implementadas, revisadas e integradas: seis tareas técnicas.**
BMX-09 espera ajustes humanos; BMX-10/11/12 no se iniciaron porque dependen de
esa ratificación. No se sustituyeron por tareas posteriores. Todos los formatos
previstos, incluido OCR, son obligatorios por decisión explícita del solicitante.
D1–D3 siguen sin ratificar: pidió ajustarlos antes.
[Decisiones, escenarios y matriz preparados](BMX-09-decisions-for-review.md).

Base: `69942cc8fe6e9fae9130ab2bdb8fb703991eb03c`. Último código revisado:
`4fa622e04f15aa990735eeb7523c98e1394ce6a4`. Verificación/build desde commit
`d17b7ae0f4e8010b15257e1d4da21e332bfe6bbe`; cambios posteriores documentales.
[Recibo estructurado de salud, hashes y métricas](BATCH_NEXT10_HEALTH.json).

## Archivos modificados

El recibo incluye la lista completa de archivos. El código se limita a
src/deidflow/benchmarks/: dos módulos existentes de admisión/runner y ocho de
métricas, cobertura, validez, transformación, pipeline, aislamiento e independencia.
Hay seis archivos nuevos de pruebas y un constructor de fixtures compartido,
un ejemplo ficticio de validez de 16 vectores, contratos de uso, actas y estados
de tickets. No hay cambios en detectores, políticas, transformación productiva,
pyproject.toml, dependencias ni versión.

## Salud integrada

| Comprobación | Resultado real |
| --- | --- |
| Suite completa con ramas | **1314 pasan, 11 omitidas**, 204.79 s |
| Cobertura de sentencias | **87.29%** (11727/13435) |
| Cobertura de ramas | **79.21%** (4512/5696) |
| Cobertura combinada | **84.88%**, umbral 78 superado |
| Ruff / formato | Pasan; 256 archivos |
| mypy Python 3.12 | Pasa; 76 módulos |
| pip check | Sin dependencias rotas |
| Microbenchmark | Pasa; 0.301 ms/registro, ratio 0.972 frente a referencia de esa corrida |
| Build local / twine --strict | Wheel y sdist pasan; no upload |
| Wheel base sin extras | API anterior y seis pistas nuevas pasan fuera del checkout |
| Fuente frente a wheel | Recibos deterministas iguales, incluido SHA de fuentes |

Las 11 omisiones son activos OCR/spaCy locales no configurados; ninguna prueba
nativa de aislamiento se omitió en este host. No son pruebas OCR aprobadas.
La base tenía 1219 aprobadas y las mismas 11 omisiones; cobertura 86.74% de
sentencias, 78.51% de ramas y 84.26% combinada. Se comprobó Python 3.12.14;
no se atribuyen resultados de CI remota. Los campos machine del microbenchmark
no se publican en el recibo; los resultados operativos están separados.

Se mantuvieron las guardas de privacidad: basetemp en /var/tmp porque /tmp
contiene un marcador Git ajeno. No se desactivaron controles de Codex. Los seis
fingerprints previos de AGENTS.md, CLAUDE.md y docs/agents/ permanecen idénticos
y no se incluyeron esos cambios en commits. La especificación conserva su SHA
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`;
los 27 cuerpos de ticket coinciden con los hashes del manifiesto.

## Tareas y revisión Matt Pocock

TDD por comportamiento y dos revisores nuevos por tarea, según la skill oficial
code-review: Standards y Spec separados, diff fijado y correcciones rojo/verde.
Los conjuntos focalizados de cada paso no son sumandos de una misma suite.

| Tarea / acta | Entrega | Salud del paso | Revisión final |
| --- | --- | --- | --- |
| [BMX-03](BMX-03.md) | Detección por entidad e incertidumbre | 151 pasan | Standards 0 / Spec 0 pendientes |
| [BMX-04](BMX-04.md) | Validez con referencia independiente | 177 pasan | Standards 0 / Spec 0 |
| [BMX-05](BMX-05.md) | Transformación gold y conservación | 197 pasan | Standards: 0 infracciones, 1 juicio P3 aceptado / Spec 0 |
| [BMX-06](BMX-06.md) | Pipeline real y todos los outputs | 214 pasan | Standards 0 / Spec 0 |
| [BMX-07](BMX-07.md) | Proceso aislado y trazado nativo | 230 pasan | Standards 0 / Spec 0 |
| [BMX-08](BMX-08.md) | Clausura, similitud y exposición | 243 pasan | Standards 0 / Spec 0 |
| BMX-09 | Decisiones y escenarios preparados | Sin ratificar | Pendiente ajuste D1–D3 |
| BMX-10 / BMX-11 | Corpus de identificadores y contextual | No iniciadas | Bloqueadas por BMX-09 |
| BMX-12 | Perturbaciones | No iniciada | Depende de BMX-10/11 |

Las actas conservan los hallazgos iniciales y su resolución, incluidos outputs
secundarios con residuales o pérdida de negación, mapas malformados, capacidades
ignoradas, supresión del trazado de hijos, límites heredados, JSON profundo y
artefactos originales duplicados. El P3 aceptado de BMX-05 mantiene comprobaciones
simples separadas de context_quality por sus reglas distintas de taxonomía y
operadores; no es una infracción escrita pendiente.

## Métricas de fixtures y alcance

- EMAIL anidado: TP=1, FP=0, FN=1; precision=1, recall=0.5, F1=0.667. El caso
  controlado TP=FP=FN=1 produce las tres métricas 0.5.
- Validez: 16/16 vectores completados. Checksum RFC: acuerdo 5/7; dos genéricos
  discrepan entre checksum ordinario estricto y excepción del candidato.
  [Recibo del oráculo independiente](BMX-04-vectors.json).
- Transformación/pipeline del fixture: retirada 2/2, conservación 34/34, éxito
  conjunto 2/2. Los adversarios mantienen soporte: bloquear todo da éxito 0,
  sin aprobados da riesgo indefinido y perder No da contexto 0/1 y FAIL.
- Aislamiento: sockets Python/libc/subproceso registrados aun capturados;
  CLONE_UNTRACED/clone3, ptrace e io_uring invalidan la auditoría. Timeout,
  ENOMEM y errores conservan soporte. Corrida limpia: 0 intentos de red.
- Independencia del fixture conocido: 2 componentes, 0 documentos blind_test,
  NO_BLIND_TEST y acreditación falsa. No se rebautizó material expuesto.
- Recall crítico del microbenchmark: 1 en su fixture de presupuesto, distinto
  del fixture anidado; no es una medición poblacional del benchmark MX.

Todo es ficción conocida y DESCRIPTIVE_ONLY. La entrada aislada de proceso no
vuelve aislados los callbacks anteriores. RLIMIT_AS es por proceso y limita
espacio de direcciones, no RSS/cgroup agregado; admisión de píxeles/expansión
no prueba decodificación. La auditoría de independencia comprueba declaraciones,
sin autenticar historial o custodia. Las celdas de formatos futuros siguen
pendientes aunque sean obligatorias. No se afirma calidad profesional ni anonimato.

## Reproducción

Desde la raíz, con las herramientas de desarrollo ya instaladas:

```sh
mkdir -p /tmp/deidflow-verification
.venv/bin/python -m pytest -q tests/test_benchmark*.py tests/test_email_benchmark.py \
  --basetemp=$(mktemp -d /var/tmp/deidflow-focused.XXXXXX)
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy --python-version 3.12 src/deidflow
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q --cov=deidflow --cov-branch \
  --cov-report=term --cov-report=json:/tmp/deidflow-verification/coverage.json \
  --basetemp=$(mktemp -d /var/tmp/deidflow-full.XXXXXX)
.venv/bin/python scripts/benchmark_micro.py --check \
  --output /tmp/deidflow-verification/micro.json
```

Para empaquetado: extraer git archive d17b7ae a un directorio vacío, ejecutar
python -m build --no-isolation con outdir externo y twine check --strict.
Instalar el wheel con pip --no-index --no-cache-dir en otro venv vacío, ejecutar
fuera del checkout y comprobar la ruta de importación, sin numpy/spacy/cryptography.
Las APIs de las seis pistas están en docs/BENCHMARK_MX_*.md; resultados comparados
y hashes del wheel/sdist quedan en el recibo. Logs locales de esta ejecución:
/tmp/deidflow-batch/integrated/. No hubo descargas durante evaluación.

## GitHub y siguiente paso

Commits incrementales, actas y borradores están en la rama de revisión
[benchmark/evaluacion-mx-spec-tickets](https://github.com/giovannyTorres/deidflow/tree/benchmark/evaluacion-mx-spec-tickets).
No se fusionó master, creó tag ni publicó PyPI. API productiva, algoritmos,
dependencias de producción y versión permanecen sin cambios.

GitHub Issues sigue configurado: **0 issues creados**. api.github.com queda
fuera de la allowlist; el borrador de entorno previo conserva ese destino
preparado para revisión. Los borradores están en GitHub como archivos, sin
inventar números de issue. No se aplicaron cambios persistentes de nube:
bubblewrap/strace y las capacidades verificadas ya existen en este host.
[Requisitos exactos para otros hosts](../BENCHMARK_MX_ISOLATION.md).

Para continuar BMX-09–12 hace falta ajustar y ratificar D1–D3 con el solicitante.
Ya están preparados los escenarios y la matriz; esa revisión no aprueba un
perfil de calidad profesional ni autoriza liberación automática.
