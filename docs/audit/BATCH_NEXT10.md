# Lote solicitado BMX-03 a BMX-12

**Las diez tareas del bloque están completadas y verificadas.** Las nueve tareas
técnicas se implementaron secuencialmente; BMX-09 documenta la decisión del
solicitante: automático, global y fácilmente reentrenable/ajustable localmente,
identificadores plausibles protegidos y perfiles clínicos contextual/estricto.
Todos los formatos previstos siguen siendo obligatorios.

[Decisión vigente](../adr/0001-bmx-09-operational-profiles-v1.md),
[recibo de salud final](BATCH_NEXT10_CONTINUATION_HEALTH.json),
[archivos y estados de tareas](../tickets/benchmark-mx/README.md).
La meta de producto no acredita calidad global ni facilidad de fine-tuning ya
implementada. Este incremento evalúa regresión ficticia conocida en es-MX.

## Salud integrada actual

Base del lote: `69942cc8fe6e9fae9130ab2bdb8fb703991eb03c`.
Commit probado y extraído para build: `390147079908a7221098ca84af4befd3f48c88ff`.
Último código de BMX-12 revisado: `390147079908a7221098ca84af4befd3f48c88ff`.
Cambios posteriores de cierre son documentales.

| Comprobación | Resultado real |
| --- | --- |
| Suite completa con ramas | **1392 pasan, 11 omitidas**, 281.82 s |
| Cobertura de sentencias | **87.59%** (12382/14137) |
| Cobertura de ramas | **79.57%** (4752/5972) |
| Cobertura combinada | **85.21%**, supera umbral 78 |
| Ruff, formato, mypy Python 3.12, pip check | Pasan |
| Microbenchmark | Pasa; 0.309 ms/registro; ratio 1.018 frente a referencia de esa corrida |
| Build local y twine --strict | Wheel/sdist pasan; no upload |
| Wheel base sin extras | API anterior, seis pistas y generación de corpus/perturbaciones pasan fuera del checkout |
| Fuente frente a wheel | Recibos deterministas idénticos, incluido SHA de fuentes |

Python 3.12.14. Las omisiones corresponden a activos locales OCR/spaCy
no configurados; ninguna prueba nativa de aislamiento se omitió. No se cuentan
como pruebas OCR aprobadas ni se atribuyen resultados de CI remota.
Se mantuvieron las guardas: basetemp en /var/tmp por el marcador Git ajeno en
/tmp. Se preservaron los seis fingerprints previos de AGENTS.md, CLAUDE.md y
docs/agents/ sin incluirlos en commits. Los 27 cuerpos de tareas coinciden con
su manifiesto; la especificación conserva SHA `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

## Entregas y revisiones Matt Pocock

TDD por comportamiento y revisión oficial code-review en ejes independientes
Standards/Spec, con diff fijado por tarea y correcciones red/green. Los conteos
focalizados de cada acta son corridas distintas, no sumandos de la suite final.

| Acta | Entrega |
| --- | --- |
| [BMX-03](BMX-03.md) | Matching exacto, errores por entidad e incertidumbre |
| [BMX-04](BMX-04.md) | Patrón, estructura y checksum con referencia independiente |
| [BMX-05](BMX-05.md) | Transformación gold y conservación |
| [BMX-06](BMX-06.md) | Pipeline real y todos sus outputs |
| [BMX-07](BMX-07.md) | Aislamiento de proceso, límites y trazado nativo |
| [BMX-08](BMX-08.md) | Particiones, linaje, similitud y exposición |
| [BMX-09](BMX-09.md) | Objetivo y perfiles operativos ratificados |
| [BMX-10](BMX-10.md) | 36 casos sintéticos de seis identificadores, negativos y oráculos |
| [BMX-11](BMX-11.md) | 10 casos contextuales y 2 desafíos ambiguos, referencia revisada por agentes |
| [BMX-12](BMX-12.md) | Nueve perturbaciones reproducibles y reportes por estrato |

Standards: 0 infracciones escritas pendientes; se conserva el juicio P3
aceptado de BMX-05 sobre comprobaciones separadas de contexto/operadores.
Los juicios de duplicación de BMX-11 y Data Clumps de BMX-12 se resolvieron. Spec:
0 hallazgos pendientes. Las actas registran agentes, commits y resultados;
no se atribuye revisión humana experta a los corpus ficticios.

## Métricas y límites

- El fixture anidado EMAIL da TP=1, FP=0, FN=1: precision=1, recall=0.5,
  F1=0.667. El caso de control TP=FP=FN=1 da las tres métricas 0.5.
- Validez: 16/16 vectores históricos completados. La referencia actual tiene
  **un** desacuerdo RFC (6/7), no dos: XEXX tiene checksum ordinario válido.
  [Fe de erratas](BMX-04-erratum.md). BMX-10 completa 36 vectores; PHONE/EMAIL
  conservan predicciones de validez desconocidas.
- Transformación/pipeline de control: retirada 2/2, conservación 34/34 y éxito
  conjunto 2/2. Borrar todo o perder negaciones sigue fallando conservación.
- El baseline `rules.mx` **sin NER** reconoce exactamente 2/47 menciones
  contextuales, FP=3 y FN=45. Describe esa configuración y ficción; no es la
  calidad de todos los modelos de DeidFlow. La referencia no se ajustó a sus fallos.
- BMX-12 midió 369 pares/738 reportes reales y 36 auditorías sin cruces con su
  commit de autoría, identificado en el acta. La integración final añade
  32 pares/64 reportes fuente y los mismos en wheel con el código revisado.
  Pesos por raíz suman 1; no se publica F1 mezclado ni falsa independencia.
- Corrida aislada: 0 intentos de red y 0 eventos de integridad. RLIMIT_AS limita
  espacio de direcciones por proceso, no RSS/cgroup agregado. Los callbacks
  anteriores no adquieren aislamiento por usar la pista de proceso por separado.
- Ningún paquete contiene blind_test acreditado. Calidad `DESCRIPTIVE_ONLY`;
  umbrales/custodia pendientes de BMX-25. Ruido textual no es OCR real.

El recibo final incluye hashes de fuentes, modelos, corpus, decisión y artefactos,
lista completa de archivos y resultados. Solo se tocó código del benchmark,
pruebas, ejemplos y documentación: detectores, transformadores productivos,
API previa, dependencias y versión permanecen sin cambios. Los documentos
extensos y la densidad se evalúan como características de fixtures, sin afirmar
rendimiento poblacional ni garantías de anonimato.

## Reproducción y evidencia histórica

Desde la raíz, con herramientas ya instaladas:

```sh
mkdir -p /tmp/deidflow-verification
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

Para empaquetado, extraer git archive del commit probado en un directorio vacío,
construir con python -m build --no-isolation y twine check --strict. Instalar el
wheel con pip --no-index --no-cache-dir en venv vacío y ejecutar fuera del
checkout, verificando ruta de importación y ausencia de numpy/spacy/cryptography.
Logs locales: /tmp/deidflow-batch/final12/. APIs y reproducción de corpus:
[identificadores](../BENCHMARK_MX_IDENTIFIERS.md),
[contextual](../BENCHMARK_MX_CONTEXTUAL.md),
[perturbaciones](../BENCHMARK_MX_PERTURBATIONS.md).

El [recibo histórico03–08](BATCH_NEXT10_HEALTH.json) se conserva intacto: 1314
pruebas, 11 omisiones y 84.88% combinada en su commit. Sus estados pendientes de BMX-09
y el segundo desacuerdo RFC pertenecen a esa corrida previa, rectificada por
la ADR y fe de erratas; no son el estado actual ni una nueva ejecución.

## GitHub y trabajo posterior

Commits incrementales y evidencia están en la rama
[benchmark/evaluacion-mx-spec-tickets](https://github.com/giovannyTorres/deidflow/tree/benchmark/evaluacion-mx-spec-tickets).
No se fusionó master, creó tag ni publicó PyPI. GitHub Issues sigue configurado:
**0 issues creados**, porque api.github.com permanece fuera de la allowlist.
Los 27 borradores están en GitHub como archivos, sin números remotos inventados.
El destino necesario ya quedó preparado en el borrador de entorno para revisión;
no se aplicaron cambios persistentes de nube. Bubblewrap/strace y las capacidades
verificadas ya existen en este host.

BMX-13 a BMX-27 permanecen pendientes. Incluyen formatos reales, OCR, fuentes
públicas autorizadas, estadísticas, custodia y calificación integrada. El objetivo
global y de ajuste local fácil sigue vigente; este bloque no implementa todavía
su flujo completo ni autoriza liberación automática con calidad sin medir.
