# Primer recorrido local del benchmark MX (BMX-01)

Este incremento implementa [BMX-01](tickets/benchmark-mx/01-primer-recorrido-local.md)
de [DF-EVAL-MX v0.1.0](specs/BENCHMARK_MX_SPEC.md). Evalúa exclusivamente detección
EMAIL en texto español mediante las reglas existentes de DeidFlow para México.
No cambia el detector, los transformadores, la API existente ni las dependencias.

## Reproducción local

Desde un checkout con DeidFlow instalado, sin extras ni conexión de red:

```python
from deidflow.benchmarks.email import run_email_benchmark

report = run_email_benchmark(
    "examples/benchmark-mx-email",
    candidate="rules.mx",
    profile="email-descriptive-v1",
    output="/tmp/deidflow-email-run-001",  # Debe ser un directorio nuevo.
)
print(report["result"]["metrics"]["EMAIL"])
```

Solo se admiten ese candidato y ese perfil. La ejecución crea `report.json` en
un directorio nuevo; rechaza destinos existentes, incluidos enlaces simbólicos.
El paquete de ejemplo contiene dos documentos totalmente ficticios: un correo
en el dominio reservado `.test` y un negativo sin datos de contacto. Es una
**regresión conocida**, no un corpus independiente ni evidencia poblacional.

Resultado esperado del ejemplo: TP=1, FP=0, FN=0, soporte=1,
precision=recall=F1=1.0. Estos valores verifican el recorrido; no califican la
capacidad general de DeidFlow ni garantizan anonimato.

## Contrato mínimo de entrada

Este formato dedicado al primer incremento no sustituye los contratos completos
de la especificación. La admisión general corresponde a BMX-02.

El directorio contiene exactamente dos recursos necesarios:

- `manifest.json`: objeto con `schema_version="df-eval-mx.email.v1"`,
  `dataset_version` numérica `mayor.menor.parche` (1–6 dígitos por componente),
  `synthetic=true` y `corpus_sha256` de los bytes originales del corpus.
- `corpus.jsonl`: UTF-8; cada línea contiene `id`, `text` y `spans`. Los IDs
  deben ser únicos y no vacíos. Cada span contiene `entity_type="EMAIL"`,
  `start` y `end`: enteros, intervalo semiabierto de índices de caracteres
  Python sobre el texto original, dentro del documento. No se permiten
  duplicados idénticos ni campos adicionales en estos objetos. El parser
  rechaza claves JSON repetidas y constantes no finitas antes de validar.

Límites de lectura: 4096 bytes de manifiesto y 1 MiB de corpus. Los recursos
fijos no pueden resolver fuera del directorio del paquete. Un paquete vacío,
alterado, ilegible o con anotaciones inválidas produce un error sanitizado sin
crear un informe. `synthetic=true` es una declaración del autor; el cargador no
puede demostrar que cualquier texto arbitrario sea ficticio. No incorporar datos
personales reales.

## Informe y reproducibilidad

`schema_version="df-eval-mx.email-report.v1"` delimita este informe mínimo:

- `result` contiene identificadores/hash del paquete y candidato, versión de
  reglas, digest SHA-256 del código Python instalado de DeidFlow, país, idioma,
  configuración sin NLP, perfil no ratificado y alcance textual EMAIL.
- El matching es exacto por tipo e intervalo y uno a uno, utilizando el
  evaluador existente. Se informan TP, FP, FN, soporte y precision/recall/F1.
  Los cocientes sin denominador son `null`, nunca una aprobación implícita.
- `operational` separa fecha UTC, duración y versión de Python. Con los mismos
  bytes del paquete, código y configuración, `result` debe ser idéntico entre
  ejecuciones. La duración incluye carga, detección y preparación del informe;
  excluye su escritura y no constituye una medida formal de rendimiento.

El digest de código usa los archivos `.py` ordenados por ruta relativa; para
cada archivo concatena longitudes de 8 bytes big-endian, nombre UTF-8 y contenido
original. Los hashes prueban identidad de bytes, no autoría ni independencia.
El informe no contiene textos, valores, IDs originales de casos, rutas ni
nombres de archivos del paquete. Los errores de entrada/salida son sanitizados.
Los resultados previos nunca se sobrescriben.

## Límites pendientes

La calidad siempre es `DESCRIPTIVE_ONLY`. No se evalúan transformación, datos
residuales, otras entidades, otros formatos, independencia de particiones,
perfiles ratificados ni calidad profesional. No se adquieren datos ni se
descargan modelos. La prueba de red bloquea DNS/conexiones Python y comprueba
cero intentos; no acredita aislamiento nativo del proceso. Este último y los
límites por caso corresponden a BMX-07. No se evalúan cambios concurrentes
maliciosos al sistema de archivos.

Las [pruebas del recorrido](../tests/test_email_benchmark.py) ejercitan el
detector real, repetición, conteos conocidos, matching exacto, denominadores
ausentes, destino existente, canarios y errores de paquete/salida. La evidencia
de aceptación se registra en [el acta BMX-01](audit/BMX-01.md).
