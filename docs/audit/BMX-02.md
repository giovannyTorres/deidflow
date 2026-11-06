> **Registro histórico de la rama de implementación.** Este texto describe
> el trabajo conservado en [`f2e4751`](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-02.md),
> no una implementación incorporada a `master` ni una auditoría o CI de esta PR.
> Los enlaces fijados al commit permiten consultar evidencia que no se copia aquí.
> Consulte el [estado de esta revisión](benchmark-spec/README.md).

# Evidencia de BMX-02

Estado: BMX-02 implementado, revisado y verificado. Los demás tickets pendientes
no se han implementado en esta entrega.
Fecha: 2026-11-06. Linux / Python 3.12.14.

Ticket: [BMX-02](../tickets/benchmark-mx/02-admision-paquete.md).
Contrato: [paquete local v1](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/BENCHMARK_MX_PACKAGE.md).
Base fija: `0e456550de7cd8cc5f3316a028b308a5aff4bd1d`.
Especificación DF-EVAL-MX v0.1.0, SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

El cambio es aditivo al sistema de evaluación. Conserva BMX-01 y las APIs de
producción, no cambia detectores/políticas/transformadores ni dependencias o
versión. Los cambios anteriores de agentes se conservan fuera del ticket.
No se adquirieron datos ni modelos ni se requieren cambios persistentes cloud.

## TDD observado

Paquetes reales en disco desde paquete/candidato/perfil → informe. Los
candidatos locales controlados entran por esa interfaz, sin sustituir clases
o módulos internos.

| Ciclo | Comportamiento | Rojo | Verde del archivo nuevo |
| --- | --- | --- | --- |
| 1 | Paquete y menciones anidadas con detector real | 1 fallo, interfaz inexistente | 1 pasa |
| 2 | Hashes, tamaños, conteos y referencia confiable | 5 fallos | 6 pasan |
| 3 | Versiones, IDs y manifiesto cerrado | 8 fallos | 14 pasan |
| 4 | JSON estricto y Unicode | 10 fallos, otras variantes ya rechazadas | 28 pasan |
| 5 | Fuentes, permisos y exposición | 10 fallos | 38 pasan |
| 6 | Documentos y unidades | 10 fallos, uno del constructor del fixture corregido | 48 pasan |
| 7 | Menciones, perfiles y expectativas | 15 fallos | 63 pasan |
| 8 | Relaciones, linajes, grupos y contradicciones | 17 fallos | 80 pasan |
| 9 | ZIP equivalente sin extracción | 1 fallo; referencias peligrosas ya rechazadas | 88 pasan |
| 10 | Binarios inertes y recursos conocidos | 2 fallos | 90 pasan |
| 11 | Fallos del candidato separados del dataset | 7 fallos | 97 pasan |
| 12 | Panel y capacidades no soportadas | 5 fallos | 102 pasan |
| 13 | Selectores con estado seguro | 2 fallos | 109 pasan |
| 14 | Artefacto validado antes de declarar pista no soportada | 1 fallo | 111 pasan |
| 15 | Operador compatible con la acción requerida | 3 fallos | 115 pasan |
| 16 | Fecha UTC de revisión de permisos obligatoria y conservada | 2 fallos, otras fechas ya rechazadas | 119 pasan |
| 17 | 2100 menciones cruzadas sin matching auxiliar recursivo | 1 fallo con RecursionError | 120 pasan |

Las cinco variantes positivas adicionales (Unicode/CRLF, spans cruzados,
precedencia, derivación y varias unidades) ya pasaron al añadirse; no se
presentan como ciclos rojos. La repetición offline del ejemplo también pasa.
Se añadió además una regresión que exige TP=FP=FN=1 y F1=0.5 con predicciones
duplicadas y límites parciales; ya pasó al escribirse.
**121 pruebas nuevas y las 21 de BMX-01 pasan.** Logs locales:
`/tmp/deidflow-bmx02/`; este acta omite trazas con rutas/canarios ficticios de
fallos intencionales.

## Verificación integrada

| Comprobación final | Resultado |
| --- | --- |
| Pruebas nuevas BMX-02 | 121 pasan |
| Focalizadas nuevas + legado BMX-01 | 142 pasan |
| Suite completa, una ejecución final | 1219 pasan, 11 omitidas; 249,37 s |
| Cobertura global de líneas | 86,74 % (10848/12507) |
| Cobertura global de ramas | 78,51 % (4216/5370) |
| Cobertura combinada pytest-cov | 84,26 %; umbral 78 % superado |
| Transporte `_package_io.py` | 91,26 % líneas; 83,33 % ramas |
| Contratos `evaluation_package.py` | 88,98 % líneas; 79,46 % ramas |
| Runner `package_runner.py` | 100 % líneas y ramas |
| Ruff / formato / mypy | Pasan; 229 archivos formateados, 68 módulos, objetivo 3.12 |
| pip check | Sin requisitos incompatibles |
| Microbenchmark, build y twine estricto | Pasan |
| Wheel sin extras, ambos recorridos y smoke de modelos/sesiones | Pasan |

Las 11 omisiones permanecen explícitas: nueve integraciones necesitan activos
OCR locales, una requiere el modelo spaCy externo y una importa `pytesseract`,
ausente aquí. No se descargaron activos ni se contaron omisiones como aprobadas.
Solo se probó Linux/Python 3.12; otras plataformas/versiones quedan a la matriz CI.
Manifiesto del ejemplo:
`7fd7f5a4808a85b3c73c9561c82b40eb06e91f9dd2e4c8165bc3b7b4bc8ddeb8`.
Métricas observadas: TP=1, FP=0, FN=1, soporte=2; precision=1.0,
recall=0.5, F1=2/3. Calidad `DESCRIPTIVE_ONLY`; fixture conocido, no test ciego.

El [informe observado](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-02-report.json) procede del código revisado
`3b28c35f2b066b72f7a1c4aa20b7462023a99080`. Dos destinos nuevos producen el
mismo `result`, con cero intentos de red Python. El wheel instalado fuera del
checkout produce exactamente ese resultado sin NumPy, spaCy ni cryptography;
también pasa el recorrido legado BMX-01 y el smoke test de modelos incorporados
y sesiones en memoria. Los campos operativos variables permanecen separados.

Código Python SHA-256:
`bc9fe0e0c596aee627f69bbb3f21298af8050e0c26d50062c58a38bf4cb3414d`.
Reglas `rules-0.6`, NLP desactivado. Perfil `email-descriptive-v1`, no ratificado.
Microbenchmark existente: 1000 registros, cinco repeticiones, mediana
0,359364 ms/registro y ratio motor/referencia 0,714357; guarda aprobada y recall
crítico exacto 1.0 para EMAIL, CURP, RFC, CLABE y API_KEY. Es una guarda de
regresiones en un runner compartido, no evidencia de mejora estadística ni
estimación de calidad poblacional.

## Comandos reproducibles

Herramientas de desarrollo ya instaladas; no se descargaron dependencias.

```sh
.venv/bin/python -m pytest -q tests/test_benchmark_package.py tests/test_email_benchmark.py
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy --python-version 3.12 src/deidflow
.venv/bin/python -m pip check

benchmark_test_root=$(mktemp -d /var/tmp/deidflow-bmx02-tests.XXXXXX)
.venv/bin/python -m pytest -q --basetemp="$benchmark_test_root" \
  --cov=deidflow --cov-branch --cov-fail-under=78 \
  --cov-report=term-missing:skip-covered \
  --cov-report=json:/tmp/deidflow-bmx02/coverage.json \
  --cov-report=xml:/tmp/deidflow-bmx02/coverage.xml

.venv/bin/python scripts/benchmark_micro.py --check \
  --output /tmp/deidflow-bmx02/micro-final.json
```

Crear previamente `/tmp/deidflow-bmx02` para los reportes. Se usa `/var/tmp`
porque `/tmp` contiene un marcador Git ajeno: las pruebas privadas mantienen
sus guardas y rechazan ubicaciones bajo Git. No se alteraron variables de
privacidad de Codex ni se omitieron esas guardas.

Empaquetado desde un árbol limpio del commit revisado, sin incluir los cambios
anteriores de configuración de agentes sin commit:

```sh
mkdir -p /tmp/deidflow-bmx02/build-final-source
git archive 3b28c35f2b066b72f7a1c4aa20b7462023a99080 | \
  tar -x -C /tmp/deidflow-bmx02/build-final-source
.venv/bin/python -m build --no-isolation \
  --outdir /tmp/deidflow-bmx02/dist-final /tmp/deidflow-bmx02/build-final-source
.venv/bin/python -m twine check --strict /tmp/deidflow-bmx02/dist-final/*
.venv/bin/python -m venv /tmp/deidflow-bmx02/wheel-venv
/tmp/deidflow-bmx02/wheel-venv/bin/python -m pip install \
  --no-index --no-cache-dir /tmp/deidflow-bmx02/dist-final/*.whl
```

La comparación instalada se hizo desde `/tmp`, comprobando la ruta de importación
del wheel y usando `offline_network()` en ambos recorridos. Los artefactos son
locales, no una publicación de versión. Wheel SHA-256:
`cced377418b2c7fb4866e32ea73a6920e09adcebaefa20fe932d26bbbb2f55dc`;
sdist SHA-256:
`ce31791793870d32512466e0274f2a3745f5994cfc5c72e83abbb647e524b174`.

## Standards

Se aplicó la skill oficial `code-review` de Matt Pocock (plugin 1.3.2): dos
revisores independientes con contexto fresco, comparados con la base fija.

El revisor independiente encontró un P2 en `5434f0c`: el evaluador genérico
calculaba un matching solapado recursivo que no se publicaba y fallaba con
2100 spans cruzados admitidos. No encontró smells Fowler sustantivos.
Peor hallazgo del eje: caída ante entradas admitidas.

Corrección: conteo exacto mediante conjuntos por unidad, sin emparejamiento
solapado auxiliar. La regresión observó RecursionError antes y ahora obtiene
TP=2100, FP=FN=0 con el candidato local controlado. El revisor repitió su
reproducción original en `3b28c35` y confirmó **0 hallazgos pendientes y 0 smells**;
sin peor hallazgo vigente de este eje.

## Spec

El revisor independiente encontró dos P2 en `5434f0c`: se permitía `remove` con
operador `keep`, y faltaba una fecha en el contrato de revisión de permisos.
No identificó ampliación injustificada de alcance. Peor hallazgo del eje:
expectativas internamente contradictorias admitidas.

Corrección: compatibilidad explícita acción/operadores y `reviewed_at` UTC
obligatorio. Ambas correcciones tienen ciclos rojos y verdes. Se actualizó el
fixture sintético y su hash para incluir la fecha; no se inventó revisión humana.
El revisor comprobó ambas correcciones en `3b28c35`, ejecutó nueve regresiones
focalizadas y confirmó **0 hallazgos pendientes**, sin ampliación injustificada
del alcance y sin peor hallazgo vigente de este eje.

Recuento inicial: Standards 1; Spec 2. No se escoge un peor problema global.
Recuento final: Standards 0 pendientes; Spec 0 pendientes.

## Límites pendientes

- La cobertura de transporte y contratos no es total; algunos fallos de límites,
  archivo/CRC y variantes de metadatos no se ejercitaron. Los porcentajes de
  cobertura no son una garantía de anonimato ni una auditoría de seguridad total.
- Admisión no autentica permisos, anotadores o custodia. BMX-08 auditará la
  independencia profunda; aquí se validan relaciones y grupos declarados.
- El recorrido sigue limitado a EMAIL textual. Otros tipos, formatos,
  ambigüedad y cobertura parcial no se puntúan favorablemente.
- Los binarios no se inspeccionan como documentos nativos; recetas y
  expectativas no se ejecutan. No se acredita aislamiento nativo, tiempo
  o RSS duros. Callbacks son código confiable, no una sandbox.
- El fingerprint de un callback es declarado por el caller. No se infiere
  configuración de modelos ni garantía offline de un callback desconocido.
- GitHub Issues sigue sin acceso API verificado; BMX es un ID documental.
  No se inventa número/cierre de issue ni se publica en PyPI.

## Archivos de la entrega

- `src/deidflow/benchmarks/_package_io.py`: lectura limitada y JSON estricto.
- `src/deidflow/benchmarks/evaluation_package.py`: contratos y relaciones.
- `src/deidflow/benchmarks/package_runner.py`: seam pública y estados separados.
- `tests/test_benchmark_package.py`: 121 casos verificables desde la seam.
- `examples/benchmark-mx-package/`: manifiesto y seis recursos ficticios.
- `docs/BENCHMARK_MX_PACKAGE.md`: contrato concreto y reproducción local.
- `docs/audit/BMX-02.md` y `BMX-02-report.json`: evidencia e informe observado.
- `docs/tickets/benchmark-mx/02-admision-paquete.md`, `README.md`, `tickets.json`:
  aceptación y trazabilidad documental. No se cierra un issue inexistente.
