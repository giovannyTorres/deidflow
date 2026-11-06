> **Registro histórico de la rama de implementación.** Este texto describe
> el trabajo conservado en [`f2e4751`](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-01.md),
> no una implementación incorporada a `master` ni una auditoría o CI de esta PR.
> Los enlaces fijados al commit permiten consultar evidencia que no se copia aquí.
> Consulte el [estado de esta revisión](benchmark-spec/README.md).

# Evidencia de BMX-01

Estado: BMX-01 implementado, revisado y verificado. Los demás tickets no se han
implementado en esta entrega.
Fecha: 2026-11-06. Entorno local: Linux, Python 3.12.14.

Ticket: [BMX-01](../tickets/benchmark-mx/01-primer-recorrido-local.md).
Contrato y reproducción: [primer recorrido EMAIL](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/BENCHMARK_MX_EMAIL.md).
Especificación: DF-EVAL-MX v0.1.0, SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

Base fija de implementación/revisión:
`9d8bbafa9f422ba1b85a3d1ebeb9cbf616fa246c`.
El incremento es aditivo: módulo de evaluación, pruebas, paquete ficticio y
documentación. No modifica API existente, detectores, políticas, transformación,
dependencias de producción ni versión. Los cambios previos a instrucciones de
agentes se conservan fuera del commit del ticket.

## TDD observado

Se ejercitó la interfaz pública paquete/candidato/perfil → informe con el
detector real. Cada ciclo añadió primero el comportamiento y observó el fallo.
Los fallos se corrigieron antes de continuar; no se cambiaron los detectores
para mejorar resultados. Los recuentos corresponden a la prueba del incremento.

| Ciclo | Comportamiento | Rojo | Verde |
| --- | --- | --- | --- |
| 1 | Paquete positivo/negativo → informe descriptivo | 1 fallo: módulo inexistente | 1 pasa |
| 2 | Preservar destino existente sin exponer su nombre | 1 fallo, 1 pasa | 2 pasan |
| 3 | Rechazar entrada ilegible, metadatos no admitidos e intervalos inválidos | 3 fallos, 3 pasan | 6 pasan |
| 4 | Sanitizar errores del destino | 1 fallo, 6 pasan | 7 pasan |
| 5 | Sanitizar fallo de lectura al identificar el candidato | 1 fallo, 14 pasan | 15 pasan |
| 6 | Sanitizar destino demasiado largo y paquete con enlace circular | 2 fallos, 15 pasan | 17 pasan |
| 7 | Rechazar claves JSON repetidas y manifiesto no UTF-8 | 4 fallos, 17 pasan | 21 pasan |

La refactorización separó admisión, identificación y escritura del informe y
concentró la creación de paquetes en las pruebas. Después de las correcciones
de revisión, **21 pruebas pasan**.
Las verificaciones adicionales que ya pasaron al escribirse no se presentan
como ciclos rojos: matching exacto, repetición sin red, canarios, denominadores
ausentes, configuración no admitida y el ejemplo distribuido.

Los logs locales por ciclo están en `/tmp/deidflow-bmx01/tdd-0N-red.log` y
`tdd-0N-green.log`. No se adjuntan trazas de fallos con rutas/canarios al informe
compartible. La prueba final puede reproducirse con:

```sh
.venv/bin/python -m pytest -q tests/test_email_benchmark.py
```

## Métricas y aceptación integrada

| Comprobación final | Resultado observado |
| --- | --- |
| Pruebas focalizadas BMX-01 | 21 pasan |
| Suite completa, una ejecución final | 1098 pasan, 11 omitidas, 280,07 s |
| Cobertura global de líneas | 86,53 % (10331/11939) |
| Cobertura global de ramas | 78,35 % (3985/5086) |
| Cobertura combinada pytest-cov | 84,09 %; umbral 78 % superado |
| Cobertura del módulo nuevo | 89,83 % líneas (106/118), 78,57 % ramas (22/28) |
| Ruff / formato | Pasan; 223 archivos ya formateados |
| mypy | Pasa; 65 módulos, objetivo Python 3.12 |
| pip check | Sin requisitos incompatibles |
| Microbenchmark existente | Pasa; 1000 registros, 5 repeticiones |
| Build offline y twine estricto | Wheel y sdist pasan |
| Wheel sin extras y comparación del benchmark | Pasan; resultado idéntico al checkout |

Las 11 omisiones se conservan: nueve integraciones necesitan activos OCR locales
explícitos, una necesita el modelo spaCy externo y una intenta importar el
adaptador opcional `pytesseract`, ausente en este entorno. No se descargaron
activos ni se presentaron estas omisiones como aprobadas. Solo se ejecutó la
matriz Python 3.12/Linux de este entorno.

Microbenchmark: mediana 0,296998 ms/registro y ratio motor/referencia 0,932857.
El recall crítico exacto fue 1.0 para EMAIL, CURP, RFC, CLABE y API_KEY en el
corpus sintético existente. Es una guarda de regresiones gruesas en un runner
compartido; no prueba mejoras estadísticas ni calidad poblacional.
Herramientas: pytest 9.2.0, Ruff 0.17.4, mypy 1.20.2.

El ejemplo contiene dos documentos ficticios, uno positivo y uno negativo.
Resultado observado en las pruebas: TP=1, FP=0, FN=0, soporte=1;
precision=recall=F1=1.0. Calidad: `DESCRIPTIVE_ONLY`. No es una estimación de
calidad poblacional ni garantía de anonimato.

El [informe observado](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-01-report.json) conserva los datos agregados y los
campos operativos reales de una ejecución. Se repitió en dos destinos nuevos:
`result` idéntico, cero intentos de red Python y canarios ausentes. El wheel
instalado fuera del checkout produjo el mismo `result` sin NumPy, spaCy ni
cryptography. También pasó el smoke test de modelos incorporados y sesiones
en memoria; persistencia cifrada sigue requiriendo el extra `vault`.

Identidad del candidato medido:

- Código revisado: `72015f7f4abd776ce2c900f7764a3d242575ec7f`.
- Código Python SHA-256:
  `e880055b5bf5b22db470266a7f8a6ca83243917112eef89be14cc774196b9fbb`.
- Reglas: `rules-0.6`. Modelo NLP: ninguno. Perfil:
  `email-descriptive-v1`, no ratificado.
- Manifiesto SHA-256:
  `144b40aaf0cbef25ae55d74175a15c4bac6fc1048472a3edbb6bbb0078a34e93`.
- Corpus SHA-256:
  `b88bf25437a58f017ef7afcfc3c7759a567e9e061a5b84d87d7c5a1064e78a1d`.

## Comandos de aceptación

Ejecutados con dependencias de desarrollo previamente instaladas. El backend
de build `hatchling 1.33.0` y sus dependencias se instalaron exclusivamente
desde la caché local, sin consultar índices remotos. No se añadieron requisitos
al proyecto ni cambios persistentes del entorno cloud para este ticket.

```sh
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy --python-version 3.12 src/deidflow
.venv/bin/python -m pip check

benchmark_test_root=$(mktemp -d /var/tmp/deidflow-bmx01-tests.XXXXXX)
.venv/bin/python -m pytest -q --basetemp="$benchmark_test_root" \
  --cov=deidflow --cov-branch --cov-fail-under=78 \
  --cov-report=term-missing:skip-covered \
  --cov-report=json:/tmp/deidflow-bmx01/coverage.json \
  --cov-report=xml:/tmp/deidflow-bmx01/coverage.xml

.venv/bin/python scripts/benchmark_micro.py --check \
  --output /tmp/deidflow-bmx01/micro-final.json
.venv/bin/python -m build --no-isolation \
  --outdir /tmp/deidflow-bmx01/dist-final
.venv/bin/python -m twine check --strict /tmp/deidflow-bmx01/dist-final/*

.venv/bin/python -m venv /tmp/deidflow-bmx01/wheel-venv
/tmp/deidflow-bmx01/wheel-venv/bin/python -m pip install \
  --no-index --no-cache-dir /tmp/deidflow-bmx01/dist-final/*.whl
```

El directorio de resultados debe existir para los reportes de pytest; las
pruebas funcionales del evaluador requieren destinos nuevos. `--basetemp` usa
`/var/tmp` porque en este entorno `/tmp` contiene un marcador Git ajeno: las
pruebas privadas conservan sus guardas y rechazan almacenamiento bajo Git.
No se modificaron las variables de privacidad de Codex para eludir esa guarda.
La comparación del wheel se hizo desde `/tmp`, comprobando su ruta instalada
y bloqueando DNS/conexiones Python con `offline_network()`.

Artefactos locales de empaquetado (no publicados):

- Wheel SHA-256:
  `a60e17c7cec21d40e275e6d4853c6826ac49dc4f42c7261f37d587e575759c31`.
- Sdist SHA-256:
  `1eedebe9459cea28cf6d58aa3457f3576775e04c0b72572d49359e7931fad5f0`.

Estos artefactos se construyeron con el código revisado; la actualización de
documentación de cierre es posterior y no cambia el código. Los hashes del
sdist no se presentan como un build del commit documental final.

## Archivos de esta entrega

- `src/deidflow/benchmarks/email.py`: recorrido público mínimo, admisión e informe.
- `tests/test_email_benchmark.py`: 21 casos sobre el recorrido y sus fallos.
- `examples/benchmark-mx-email/manifest.json` y `corpus.jsonl`: paquete ficticio.
- `docs/BENCHMARK_MX_EMAIL.md`: contrato, reproducción y límites.
- `docs/audit/BMX-01.md` y `BMX-01-report.json`: acta e informe observado.
- `docs/tickets/benchmark-mx/01-primer-recorrido-local.md`, `README.md` y
  `tickets.json`: aceptación local y trazabilidad del ticket; no cierre de issue.

## Revisión Matt Pocock

Dos revisores independientes, con contexto fresco, compararon la base fija con
`fc32b301a1b1fcba16a3bbe61e56e4db96d2941e` y verificaron las correcciones en
`72015f7f4abd776ce2c900f7764a3d242575ec7f`. Cada eje reprodujo sus casos y ejecutó
las 21 pruebas focalizadas. Los ejes permanecen separados.

### Standards

Dos hallazgos documentados P2: la comprobación inicial del destino podía exponer
una ruta demasiado larga; el parser aceptaba claves JSON duplicadas y descartaba
contenido. Peor problema de este eje: exposición de rutas en excepciones.
No se identificaron smells Fowler sustantivos.

Resolución: se eliminó la consulta duplicada al destino y se utiliza la creación
exclusiva con errores sanitizados. El parser rechaza claves repetidas en todos
los niveles y constantes no finitas. Regresiones observadas rojas y verdes.
Comprobación final del revisor: **0 hallazgos pendientes**, sin smells
sustantivos ni peor problema pendiente de este eje.

### Spec

Un hallazgo: la sanitización prometida era incompleta para enlaces circulares de
entrada y rutas de salida demasiado largas. No se encontraron otros requisitos
faltantes ni ampliación del alcance. Peor problema de este eje: nombres
originales expuestos mediante excepciones.

Resolución: errores de resolución de enlaces se convierten en diagnóstico
genérico de paquete inválido; el destino usa la frontera de escritura sanitizada.
Dos regresiones observadas rojas y verdes.
Comprobación final del revisor: **0 hallazgos pendientes**, sin faltantes ni
ampliación del alcance; sin peor problema pendiente de este eje.

Recuento inicial: Standards 2; Spec 1. No se escoge un peor problema global.
Recuento final: Standards 0 pendientes; Spec 0 pendientes.

## Riesgos y trabajo posterior

- Solo EMAIL en texto y regresión sintética conocida; transformación y datos
  residuales no evaluados. Los demás tickets permanecen sin implementar.
- El formato mínimo no constituye la admisión completa de BMX-02.
- Sin perfil ratificado, independencia acreditada ni aislamiento nativo. La
  prueba bloquea DNS/conexiones Python; no certifica una sandbox del proceso.
- La cobertura del módulo no es total: quedan sin ejercitar ramas de límites,
  admisión y recuperación tras fallos durante la escritura. Tampoco se probaron
  aquí Python 3.11/3.13, otros sistemas ni las 11 integraciones omitidas.
- No se publican datos personales reales, modelos ni nueva versión en PyPI.
- GitHub Issues sigue sin acceso API verificado; BMX-01 es un identificador
  documental, no se inventa número ni cierre remoto de issue.
