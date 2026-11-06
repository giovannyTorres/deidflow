# Evaluación de privacidad y conservación de contexto

`scripts/benchmark_context.py` ejecuta 40 documentos ficticios en español:
10 clínicos, 10 financieros, 10 jurídicos y 10 generales, agrupados en 20
sesiones de dos documentos. El corpus contiene 102 menciones sensibles, 96
fragmentos de contexto que deben conservarse y 20 relaciones declaradas.
Sus nombres y situaciones fueron escritos para esta prueba; los correos usan
dominios reservados de ejemplo. No procede de expedientes ni clientes reales.

El archivo fijo es `benchmarks/context-cases-es.jsonl`, SHA-256
`a1dd2204118f3639131d021477310e06ceafd4c7ccfa31fc852c771b036bac07`.
No debe utilizarse para entrenar o seleccionar un modelo y después presentarse
como evidencia independiente. Si se corrige una anotación, hay que versionar el
corpus y repetir ambas configuraciones sobre el mismo nuevo digest.

## Qué mide

- **Privacidad:** caracteres sensibles eliminados, menciones sustituidas por
  completo, límites exactos del marcador y coincidencia del tipo semántico.
  Por separado comprueba si el valor literal anotado aún aparece en cualquier
  parte de la salida. Las máscaras reciben crédito solo por su prefijo
  realmente cambiado. Las transformaciones de generalización, fechas y funciones
  arbitrarias no reciben crédito de eliminación sin demostrar su semántica.
  Una acción declarada no basta: toda la sustitución debe tener la sintaxis
  correspondiente (marcador estándar completo, token HMAC completo, bloques de
  censura o cadena vacía). Un marcador seguido de un apellido sin censurar no
  recibe crédito. Las etiquetas personalizadas ajenas al catálogo se consideran
  no medidas, aunque su forma coincida con la de un marcador.
- **Contexto:** caracteres originales no sensibles conservados y fragmentos
  obligatorios intactos: dosis, unidades, diagnósticos, negaciones, importes,
  tasas, términos contractuales y expresiones de relaciones. Comprueba los
  fragmentos originales en su posición correspondiente, no solo que sus palabras
  aparezcan en otro lugar de la salida. Valida todos los huecos de los mapas de
  offsets; un mapa que oculta una edición no recibe crédito.
- **Identidad:** pares de menciones de la misma entidad en documentos distintos
  que reciben el mismo marcador, y colisiones entre entidades distintas. Solo
  cuenta marcadores indexados con límites exactos. No presupone que un apodo,
  un nombre parcial o dos homónimos correspondan a la misma persona.
- **Relaciones:** conservación de aristas declaradas explícitamente, su
  dirección, evidencia y procedencia humana. También penaliza aristas inesperadas
  o duplicadas. Esto mide almacenamiento de relaciones, **no extracción
  automática ni resolución de correferencias**. Una API sin grafo se registra
  como `unsupported`, no como una medición de fidelidad.
- **Estado de liberación:** registra por separado aprobados, bloqueados y
  pendientes de revisión. Un documento sin salida no gana puntuación por haber
  eliminado todos los datos. El éxito conjunto exige salida verificable, ausencia
  de fuga anotada y conservación de todos sus fragmentos de contexto requeridos.

Los reportes incluyen conteos y cocientes agregados por dominio; no guardan
textos, valores, offsets, claves, archivos originales ni mapas de reidentificación.
Las tasas con denominador cero son `null`. El guard impide llamadas DNS/connect
de Python durante la inferencia y registra intentos, incluidos los interceptados
por la aplicación. No sustituye el aislamiento de red del sistema operativo.

## Reproducir y comparar

Desde la raíz del repositorio, en un entorno con la biblioteca instalada:

```console
python scripts/benchmark_context.py --pipeline baseline --profile balanced \
  --output /tmp/context-baseline.json --csv /tmp/context-baseline.csv

python scripts/benchmark_context.py --pipeline domains --profile balanced \
  --checkpoint-between-documents \
  --compare-to benchmarks/results/context-baseline-v050b1.json \
  --output /tmp/context-candidate.json --csv /tmp/context-candidate.csv
```

El primer comando usa `Policy.llm()` y `builtin:auto` de la versión instalada;
el nombre heredado de la política no implica llamadas a un LLM. El segundo usa
los paquetes por dominio. `--checkpoint-between-documents` necesita el extra
gratuito `vault`, guarda una instantánea cifrada temporal y carga una sesión con
un allocator nuevo entre los dos documentos. Si no existe esa capacidad, falla
explícitamente. Los archivos de salida deben ser nuevos.

Para una comparación histórica real, ejecute cada revisión en su propio checkout
y use exactamente el mismo corpus. Volver a ejecutar `--pipeline baseline` con
código o modelos nuevos no reproduce automáticamente una revisión anterior.
El reporte registra revisión, versión, perfil y digests de los modelos; la
comparación rechaza corpus diferentes.

## Línea base registrada

`benchmarks/results/context-baseline-v050b1.json` y su CSV corresponden al código
de biblioteca `7d35654044f670d2f7cddab315428d01d803ed4e`, anterior a los nuevos
paquetes y sesiones persistentes, con `builtin:auto` y perfil `balanced`:

| Medida | Resultado |
| --- | ---: |
| Caracteres sensibles eliminados | 84.75 % |
| Menciones sensibles completamente sustituidas | 84.31 % |
| Fragmentos de contexto obligatorio conservados | 100 % |
| Caracteres no sensibles conservados | 99.72 % |
| Consistencia de identidad entre documentos | 64.71 % |
| Documentos con fuga anotada | 14 de 40 |
| Éxito conjunto de privacidad y contexto | 26 de 40 |
| Colisiones entre identidades | 0 |
| Grafo de relaciones / persistencia de sesión | No disponible en esa API |

Los 11 documentos aprobados de esta prueba no conservaron valores sensibles
anotados. Este tamaño y selección no permiten concluir una tasa de fuga cero
en producción; los resultados de corpus públicos más amplios siguen vigentes.

Esta suite comprueba regresiones de texto y comportamiento de las API. No mide
PDF, OCR, Office, HTML, representatividad del español real, protección frente a
inferencia de identidad o anonimato legal. No es una clasificación de bibliotecas
ni evidencia de que DeidFlow sea la mejor del mercado.

## Regresión amplia sobre 600 documentos generados

```console
python scripts/benchmark_domain_regression.py --documents 600 --seed 1729 \
  --output /tmp/domain-synthetic600.json --csv /tmp/domain-synthetic600.csv
```

Este experimento mantiene iguales el modelo `es-general`, el perfil `balanced`
y la política del paquete general. Compara el motor base con el motor que añade
las reglas de rol y ajuste de límites del paquete. Crea una sesión independiente
por documento; no mide relaciones ni persistencia entre documentos.

Usa `synthetic_es.generate(..., split="test")`, las ocho familias de plantillas
reservadas por el entrenamiento original del modelo, con Faker 40.44.0 en la
corrida registrada. El reporte incluye los digests de textos, anotaciones,
generador, fuentes Python, recursos/modelos y perfil, junto con las revisiones y
el indicador de cambios locales. Las métricas se separan en todos los tipos
anotados e identificadores directos. Si se configura generalización de edades
o desplazamiento de fechas, no recibe crédito de eliminación completa.
La utilidad se mide únicamente fuera de **todos** los spans sensibles anotados,
para no llamar pérdida de contexto a la eliminación intencionada de una fecha.

Es una repetición de regresión sobre plantillas sintéticas, no una evaluación
independiente de expedientes reales. No entrena, calibra, busca umbrales ni
selecciona modelos con sus resultados. Las cifras históricas del release gate
con `Policy.strict()` y otro enrutador no son directamente intercambiables con
esta comparación que mantiene modelo y política constantes.

Los errores observados en estas plantillas motivaron correcciones gramaticales
de la versión 0.6: respuestas de diálogo confundidas con nombres y domicilios
que absorbían campos posteriores. Por eso el conjunto es diagnóstico y de
regresión para las **reglas nuevas**; no es una evaluación independiente de
esas reglas, aunque sus familias sí se separaron al entrenar el modelo existente.

Una comparación de reglas narrativas debe seleccionar decisiones únicamente
con validación y comprobar después las regresiones conocidas:

```console
python scripts/benchmark_domain_regression.py --documents 600 --seed 1729 \
  --split validation --ablate-narrative --output /tmp/narrative-validation.json \
  --csv /tmp/narrative-validation.csv
```

Ese comando compara el modelo base, reglas de rol y reglas de rol más
`NarrativeRecognizer`, con el mismo modelo y política. La opción de ablación
rechaza `--split test`. Los resultados de test ya observados se identifican
siempre como una repetición de regresión, no como nueva evidencia intacta.

La [evidencia de aceptación 0.6](PRODUCT_EVIDENCE.md) reúne los resultados
registrados, los digests y sus limitaciones. El CSV amplio exporta métricas
agregadas por motor y alcance; el JSON conserva además el detalle por familia
de plantillas y la procedencia completa.
La colección actual es
[`product-v060-general2`](../benchmarks/results/product-v060-general2/);
la colección anterior se conserva como evidencia histórica.
