# Plan de incorporación del benchmark MX

Plan basado en el diff entre `44d04b1` y
`f2e4751d280a100e5af450337d70db78a8fefa03`. Es una propuesta de extracción;
ninguna fila acredita implementación incorporada, CI nuevo o aprobación externa.
La rama original se conserva sin reescrituras ni eliminaciones.

## Tamaño y cortes

El diff contiene 10 504 líneas Python añadidas: arnés BMX-01–08, 6 998
(3 677 de producción y 3 321 de pruebas/ayudantes); corpus BMX-10–12, 3 506
(2 057 de producción y 1 449 de pruebas/ayudantes). Los grupos completos superan
el objetivo aproximado de 1 500 líneas de código por PR, excluyendo fixtures y
datos. Los tamaños siguientes cuentan pruebas salvo los ayudantes indicados.

Los módulos de la tabla están bajo `src/deidflow/benchmarks/` y las pruebas bajo
`tests/`. Cada corte debe conservar una capacidad verificable por sí misma una
vez incorporadas sus dependencias.

| PR | Comportamiento y archivos principales | Líneas Python de referencia |
| --- | --- | ---: |
| Documentación | Especificaciones, tickets, ADR, recibo, glosario y procedencia | 0 |
| BMX-01 | Recorrido EMAIL: `email.py`, `test_email_benchmark.py` | 614 |
| BMX-02a | JSON estricto, límites y lectura segura de directorio/ZIP: `_package_io.py`, pruebas directas acotadas | 148 + pruebas |
| BMX-02b | Admisión completa: `evaluation_package.py`, pruebas directas del cargador | 948 + hasta 538 antes de adaptar |
| BMX-03 | Detección e informes: `package_runner.py`, `detection_metrics.py`, `span_coverage.py`, pruebas de detección e integración restantes | aproximadamente 1 465 sin ayudantes de fixtures |
| BMX-04 | Validez independiente: `validation_runner.py`, `test_benchmark_validation.py` | 574 |
| BMX-05 | Transformación aislada: `transformation_metrics.py`, `transformation_runner.py`, `test_benchmark_transformation.py` | 726 |
| BMX-06 | Pipeline: `pipeline_runner.py`, `test_benchmark_pipeline.py` | 599 |
| BMX-07 | Ejecución aislada: `isolation.py`, `test_benchmark_isolation.py` | 648 |
| BMX-08 | Independencia: `independence.py`, `test_benchmark_independence.py` | 500 |
| BMX-10 | Escritura de paquetes y corpus de identificadores: `synthetic_package.py`, `test_benchmark_identifier_corpus.py` | 852 |
| BMX-11 | Corpus contextual: `contextual_package.py`, `test_benchmark_contextual_corpus.py` | 1 108, más recursos de referencia |
| BMX-12a | Generación de perturbaciones y admisión de derivaciones | aproximadamente 966 antes de imports/separadores |
| BMX-12b | Admisión de suite e informes comparados de detección | aproximadamente 464 antes de imports/separadores |

Cada PR funcional lleva su documentación y sus ejemplos/evidencias pertinentes,
con nuevas verificaciones atribuibles a su propio commit. Los tamaños no son
presupuestos ya comprobados de ramas extraídas. Deben medirse al preparar cada
diff; el coste de las dos recetas nuevas solicitadas para BMX-12 se añade al
corte de generación y todavía no está incluido en estos conteos.

## Dependencias funcionales y de pruebas

- `email.py` solo requiere módulos existentes en la base.
- `_package_io.py` solo usa la biblioteca estándar. La admisión completa depende
  de ese transporte y de `core.EntityType`; su validación de vectores y
  derivaciones no requiere generadores de corpus.
- `package_runner.py` requiere admisión, ayudantes EMAIL y métricas de detección;
  `detection_metrics.py` requiere `span_coverage.py`. Copiar solo el runner rompe
  sus imports.
- Validez requiere admisión y ayudantes EMAIL; el ticket BMX-04 declara además
  BMX-03 como predecesor.
- Transformación requiere admisión y ayudantes EMAIL. Pipeline requiere también
  detección y transformación.
- Aislamiento requiere transporte y ayudantes EMAIL. Independencia requiere
  admisión y ayudantes EMAIL.
- BMX-10 requiere el recibo BMX-09; sus pruebas requieren detección, validez e
  independencia.
- **BMX-11 también depende del módulo de BMX-10**: importa `canonical_json`,
  `read_operational_decision` y `write_package_records` desde
  `synthetic_package.py`. Sus pruebas requieren transformación e independencia.
  Es una dependencia real adicional a las declaradas en el ticket histórico.
- BMX-12 requiere admisión, `synthetic_package.py` y `package_runner.py`.
  Las dos recetas nuevas no pueden constituir hoy una PR funcional contra la
  base, donde esos módulos todavía no existen.

## Cortes que necesitan adaptación

BMX-02 no cabe como simple copia de archivos: transporte, admisión, runner y su
archivo de pruebas suman 2 820 líneas, incluso antes de las métricas que ahora
importa el runner. La propuesta separa transporte, admisión completa y detección;
no publica un cargador que acepte contratos sin validar.

De `test_benchmark_package.py` en el commit original, los rangos 261–290,
293–326, 329–383, 386–421, 424–459, 462–502, 505–548, 551–597, 628–689,
692–719, 722–739, 945–981, 1087–1104, 1188–1210 y 1213–1241 contienen
538 líneas de funciones y decoradores aptas para llamar directamente a
`load_evaluation_package`. Retirar los argumentos del runner y adaptar las
aserciones da margen al corte de admisión. Las restantes 582 líneas de funciones
(646 con imports/separadores actuales) conservan callbacks, scoring, selección e
informes con BMX-03. Los ayudantes iniciales ocupan 220 líneas brutas; preservar
las exportaciones `canonical`, `fixture_records`, `save_manifest` y `write_fixture`
que usan las demás pruebas y `benchmark_case_fixtures.py`.

BMX-12 completo ya suma 1 546 líneas. Separar la generación hasta
`generate_perturbation_suite`, sus pruebas y
`test_benchmark_derivation_admission.py` del par `_admit_suite` /
`run_perturbation_suite` y sus pruebas de informes, presupuesto y manipulación.
Medir de nuevo el corte de generación al añadir las dos recetas.

## Secuencia y ramas de preparación

Secuencia práctica propuesta: corrección Unicode independiente; documentación;
BMX-01; BMX-02a; BMX-02b; BMX-03; BMX-04; BMX-05; BMX-06; BMX-07;
BMX-08; BMX-10; BMX-11; BMX-12a; BMX-12b. BMX-09 queda documentado por la
ADR y el recibo. Unicode conserva su propia revisión y sus requisitos externos.

La documentación, EMAIL y el transporte pueden prepararse como ramas
independientes desde la base actual. Para cada corte dependiente, crear su rama
de revisión desde `master` una vez incorporados sus predecesores y trasladar
únicamente sus cambios. Las preparaciones locales anteriores deben identificarse
como tales y esperar; no abrir una PR contra `master` con el código no incorporado
de los predecesores dentro de su diff ni fingir que ya existen en la base.

Cada PR debe satisfacer las [cuatro condiciones de incorporación](README.md#estado-y-condiciones-de-incorporación).
No se fusiona ninguna rama ni se modifica la historia existente con este plan.
