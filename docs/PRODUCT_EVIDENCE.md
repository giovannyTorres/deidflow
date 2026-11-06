# Evidencia de aceptación de DeidFlow 0.6.0b1

Los paquetes conservan contexto, mantienen identidades y relaciones declaradas,
y permiten guardar sesiones cifradas. La evidencia registrada demuestra esas
capacidades en regresiones ficticias. **No acredita anonimización automática
ni desempeño universal en documentos reales.** Los paquetes dejan sus salidas
pendientes de revisión humana; una tasa de fuga entre aprobados sin documentos
aprobados se registra como `null`, nunca como cero.

Los artefactos de esta evaluación están en
[`benchmarks/results/product-v060`](../benchmarks/results/product-v060/).
El índice vincula los reportes con SHA-256; los JSON y el índice registran
revisión, estado del checkout, digest de fuentes Python, modelos, perfiles,
corpus, script y guard de red. No contienen textos originales, mapas de
reidentificación ni claves. Los CSV son proyecciones agregadas; un valor vacío
representa una métrica sin denominador o no disponible.

## Contrato de contexto, identidad y relaciones

Se repitieron los mismos 40 documentos ficticios en español de la línea base
0.5.0b1, sin editar el corpus. Son 20 sesiones de dos documentos, con 102
menciones sensibles, 96 fragmentos de contexto, 51 pares de identidad y 20
relaciones explícitas. Entre documentos se guarda y carga la sesión cifrada
con un allocator nuevo.
Los fallos iniciales de esta suite orientaron correcciones de límites e identidad;
es una regresión corregida, no una estimación independiente del desempeño.

| Medida | Línea base 0.5.0b1 | Paquetes 0.6.0b1 |
| --- | ---: | ---: |
| Caracteres sensibles eliminados | 84.75% | 100% (1856/1856) |
| Menciones completamente sustituidas | 84.31% | 100% (102/102) |
| Contexto obligatorio conservado | 100% | 100% (96/96) |
| Caracteres no sensibles conservados | 99.72% | 100% (4357/4357) |
| Identidad estable entre documentos | 64.71% | 100% (51/51) |
| Colisiones entre entidades distintas | 0 | 0 |
| Documentos con fuga anotada | 14/40 | 0/40 |
| Éxito conjunto de privacidad y contexto | 26/40 | 40/40 |
| Relaciones conservadas con evidencia | API no disponible | 20/20 |
| Guardados/cargas cifrados comprobados | API no disponible | 20/20 |

Los 40 documentos candidatos requieren revisión humana. Los marcadores son
indexados, de tipo correcto y con límites exactos en las 102 menciones.
La identidad usa valores completos iguales y contexto compatible; no prueba
correferencia, apodos ni desambiguación de homónimos. Las relaciones las declara
el evaluador: el resultado prueba su almacenamiento y evidencia, **no su
extracción automática**. La comparación histórica incorpora cambios de API,
modelos y reglas; no atribuye toda la mejora a un solo componente.

## Regresión amplia y pérdida de contexto residual

La comparación de 600 documentos usa el mismo modelo `es-general`, perfil
`balanced` y política general en ambos motores. Una sesión independiente por
documento aísla la comparación de detección, límites y contexto. El denominador
de contexto excluye todos los spans sensibles anotados, también fechas y otros
cuasiidentificadores; no penaliza su eliminación intencional.

| Medida | Motor base | Paquete general |
| --- | ---: | ---: |
| Caracteres de identificadores directos eliminados | 96.756% | 97.419% |
| Menciones directas completamente sustituidas | 94.248% | 95.314% |
| Documentos con alguna fuga directa anotada | 136/600 | **113/600** |
| Caracteres de todos los tipos anotados eliminados | 95.938% | 96.832% |
| Caracteres no sensibles conservados | 97.872% | 99.196% |
| Revisión requerida / bloqueados | 519 / 81 | 595 / 5 |
| Aprobados automáticamente | 0 | 0 |

Persisten **113 documentos con fuga directa anotada (18.83%)**; por eso estas
cifras no autorizan liberar automáticamente las salidas. El paquete conserva
84437 de 85121 caracteres no sensibles: aún modifica 684. La revisión humana
es una parte explícita del comportamiento, no una corrección supuesta en la
puntuación. Los 595 documentos pendientes y los 5 bloqueados se incluyen en
los denominadores; ningún documento descartado recibe crédito de privacidad.

Los errores observados en estas plantillas motivaron correcciones gramaticales
de respuestas de diálogo y domicilios que absorbían campos siguientes.
**Este conjunto es diagnóstico y de regresión para las reglas nuevas**, aunque
sus familias se separaron al entrenar el modelo existente. No se hizo búsqueda
de umbrales ni entrenamiento con esta evaluación. La retención mide caracteres,
no suficiencia semántica ni utilidad para cada tarea posterior.

## Decisión sobre reglas narrativas

La ablación se ejecuta por separado sobre las 600 plantillas de `validation`.
Compara el mismo modelo y política con reglas explícitas de rol, con o sin
`NarrativeRecognizer`. La elección de conservar el reconocedor narrativo se
apoyó en esta partición, no en elegir la mejor puntuación del test observado.

| Medida | Rol + narrativa | Solo rol |
| --- | ---: | ---: |
| Caracteres directos eliminados | 91.838% | 90.885% |
| Menciones directas completas | 89.494% | 88.035% |
| Documentos con fuga directa | 171/600 | 195/600 |
| Caracteres no sensibles conservados | 98.433% | 98.458% |
| Revisión requerida / bloqueados | 594 / 6 | 592 / 8 |

Las reglas narrativas recuperan 337 caracteres directos y 30 menciones completas,
con 20 caracteres no sensibles adicionales transformados (de 79827).

La diferencia confirma un intercambio medido entre cobertura y contexto, no una
garantía de superioridad en cualquier dominio. Test y validación son sintéticos
y comparten un generador; no sustituyen anotación independiente de textos reales.

## Demostración de postentrenamiento local

La demo entrena un baseline ficticio pequeño para `PERSON` y adapta sus pesos
con `PATIENT_ID`, replay y particiones separadas. No adapta los modelos clínico,
financiero ni general incorporados. Conserva la separación train/validation y
evalúa después 40 documentos de test y 40 de regresión, con 30 spans por
categoría y 10 negativos por partición.

| Medida | Base ficticia | Candidato adaptado |
| --- | ---: | ---: |
| Recall exacto `PATIENT_ID`, test | 0/30 | 30/30 |
| Recall / precisión `PERSON`, test y regresión | 100% / 100% | 100% / 100% |
| Documentos con fuga de salida, test | 0/40 | 0/40 |
| Sobre-redacción de contexto, test | 0% | 0% |
| Sobre-redacción de contexto, regresión | 0% | 0% |

La corrida final conserva el mismo candidato `es-adapt-635141c861ffe5e612296f65`.
Frente a la demostración inicial de desarrollo, las correcciones generales de
límites reducen la sobre-redacción de test del 1.523% al 0% en **ambos** modelos;
esa mejora no se atribuye al postentrenamiento.

El entrenamiento aprende una categoría nueva. La salida ya protegía esos
identificadores mediante reglas, por lo que **no se observó mejora de fuga del
producto completo**. La promoción queda `BLOCKED`, `activated: false`, por
procedencia ficticia. La demo reduce explícitamente los mínimos de documentos
y negativos para comprobar el mecanismo; esos mínimos no son los defaults de
promoción. Incluso con cero fugas observadas en 40 documentos, el límite superior
Wilson del 95% es 8.76%; la muestra no acredita riesgo cero. Véase
[el protocolo completo](POST_TRAINING.md).

## Reproducir

Usar el mismo código/modelos registrados, Python 3.11 y Faker 40.44.0 para el
corpus amplio. Instalar los extras gratuitos `vault` y `training`; NumPy se usa
solo al entrenar. Cada comando exige rutas de salida nuevas:

```bash
PYTHONPATH=src python scripts/benchmark_context.py \
  --pipeline domains --profile balanced --checkpoint-between-documents \
  --compare-to benchmarks/results/context-baseline-v050b1.json \
  --output /tmp/context40.json --csv /tmp/context40.csv

PYTHONPATH=src python scripts/benchmark_domain_regression.py \
  --documents 600 --seed 1729 \
  --output /tmp/synthetic-test600.json --csv /tmp/synthetic-test600.csv

PYTHONPATH=src python scripts/benchmark_domain_regression.py \
  --documents 600 --seed 1729 --split validation --ablate-narrative \
  --output /tmp/synthetic-validation600.json --csv /tmp/synthetic-validation600.csv

PYTHONPATH=src python scripts/adapt_span_tagger.py demo \
  --output /tmp/posttraining-demo
```

El guard Python registró cero intentos de red en las pruebas de inferencia.
No es una prueba del aislamiento de red de todo el sistema operativo. El
entrenamiento y el paquete no requieren servicios pagados ni LLM.

## Lo que sigue abierto

- Medir privacidad, contexto y carga de revisión con corpus públicos autorizados
  o datos propios anotados independientemente, separados por persona/documento
  fuente y distintos de los usados para desarrollar reglas o modelos.
- Reducir las fugas y pérdidas de contexto residuales medidas en el corpus
  amplio; la perfección en los 40 casos del contrato no elimina esos errores.
- Validar por separado OCR, PDF, Office, HTML y cada flujo de integración. Estas
  cifras son de texto y no se extrapolan a los formatos.
- Auditar amenazas de reidentificación y acceso a llaves, mapas y sesiones en
  el despliegue real. Preservar contexto puede conservar cuasiidentificadores;
  este benchmark no demuestra anonimato legal ni resistencia a inferencias.

Los reportes históricos de corpus públicos del repositorio siguen siendo
históricos. No se presentan como una corrida nueva de esta versión. Claude
Code puede reproducir los comandos, verificar digests y revisar los fallos,
las reglas y los límites declarados; esa auditoría externa todavía no forma
parte de estos resultados.
