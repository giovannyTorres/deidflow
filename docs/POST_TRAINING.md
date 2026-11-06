# Adaptación local del detector de spans en español

DeidFlow puede adaptar un modelo de spans existente con anotaciones de un nuevo
dominio. El entrenamiento y la inferencia son locales: no usan LLM, servicios de
pago, API ni GPU. El entrenamiento necesita NumPy (`pip install '.[training]'`);
el candidato resultante usa la inferencia habitual sin dependencias obligatorias.

El método es **warm-start del perceptrón estructurado desde sus pesos promediados**.
No es fine-tuning de un transformer ni continuación del estado original del
optimizador: comienza un acumulador de promediado nuevo. Conserva las etiquetas
BIO existentes, inicializa sus pesos y transiciones desde el modelo base y añade
las categorías anotadas nuevas. El replay, opcional y explícito, mezcla ejemplos
antiguos autorizados en el entrenamiento para reducir el olvido; no garantiza
preservar el desempeño. Eso se mide en una regresión independiente.

## Separación de datos y protocolo

1. Preparar `train` y `validation` independientes. Solo `train`, incluido replay,
   ajusta pesos y descubre features nuevas. `validation` selecciona la época y
   calibra probabilidades. La calibración del modelo padre no se reutiliza.
2. Declarar los criterios de promoción **antes** de entrenar. `stage` crea un
   candidato inactivo, el modelo base, un manifiesto y sus digests; no acepta
   documentos con rol `test` o `regression`.
3. Entregar por separado un `test` del dominio objetivo y una `regression` de
   contextos/categorías anteriores. `evaluate` carga los artefactos congelados y
   no llama al entrenamiento, selección de época ni calibración.
4. Un gate satisfecho produce `ELIGIBLE_FOR_MANUAL_REVIEW`. No instala, activa,
   sustituye el modelo incorporado ni declara anonimización. `BLOCKED` identifica
   cada criterio incumplido. Si se usan los resultados de test para modificar el
   candidato o los umbrales, ese test deja de ser independiente: hace falta otro.

Cada JSONL tiene un objeto por documento:

```json
{"id":"documento-ficticio-01","group_id":"familia-ficticia-A","split":"train","text":"Paciente: Talora.","spans":[{"start":10,"end":16,"label":"PERSON"}]}
```

Los offsets son índices de caracteres Python, inicio inclusivo y fin exclusivo.
Las categorías usan mayúsculas, números y guion bajo. Se aceptan `entity_type` en
lugar de `label` y `template_id` en lugar de `group_id`. Valores contradictorios
se rechazan. Las fronteras deben coincidir con tokens completos; solapamientos,
duplicados y offsets inválidos fallan antes de entrenar. Un documento negativo
tiene `spans: []`; debe revisarse completo, no significar “todavía no anotado”.

`group_id` identifica la familia real de origen: persona, documento fuente,
plantilla o episodio relacionado. Todos sus documentos deben quedar en la misma
partición. Si varias relaciones conectan documentos, asignar la misma familia a
todo el conjunto conectado. **No** generar grupos nuevos para cada split si los
documentos siguen relacionados. El programa exige el grupo y comprueba igualdad;
no puede deducir relaciones que no se declararon.

Se rechaza reutilización entre particiones de ID, grupo o texto normalizado
(Unicode NFKC, casefold y colapso de whitespace), aunque cambien las anotaciones.
Dentro de cada partición también se rechazan IDs/textos repetidos. Train y replay
forman una sola partición. Test y regresión se comprueban contra ambas particiones
de ajuste y entre sí. Estos controles no detectan todas las paráfrasis ni prueban
que los datos no aparecieron en el entrenamiento original del modelo base.

## Ejecución

Desde el repositorio, con el extra de entrenamiento instalado:

```bash
PYTHONPATH=src python scripts/adapt_span_tagger.py stage \
  --baseline builtin:es-clinical \
  --train /datos/train.jsonl --validation /datos/validation.jsonl \
  --replay /datos/replay-train.jsonl \
  --output /modelos/adaptacion-01
```

`--baseline` admite `builtin:<nombre>` registrado o un JSON/gzip compatible. No
se cargan pickles. `--replay` es opcional. Para datasets públicos comprobar la
licencia y los splits originales; para datos privados, preparar y entrenar fuera
del repositorio y de sesiones compartidas, en almacenamiento autorizado.

Guardar el `manifest_sha256` que imprime `stage` en un registro de confianza.
El digest que se pasa a evaluación debe ser el registrado entonces, no uno
recalculado tras recibir artefactos de procedencia desconocida:

```bash
PYTHONPATH=src python scripts/adapt_span_tagger.py evaluate \
  --staged /modelos/adaptacion-01 --manifest-sha256 DIGEST_REGISTRADO \
  --test /datos/test-independiente.jsonl \
  --regression /datos/regresion-independiente.jsonl \
  --evidence-kind independently_annotated --baseline-exposure-verified \
  --output /modelos/evaluacion-01
```

`--baseline-exposure-verified` es una declaración del evaluador: verificó que
las fuentes de entrenamiento, selección y calibración del modelo base no
contienen ninguno de los holdouts. No se debe marcar sin esa comprobación.
`independently_annotated` declara evidencia anotada y revisada de manera
independiente; no convierte datos sintéticos en evidencia de producción.
Sin ambas declaraciones la promoción se bloquea. El CLI devuelve código 1 si
el gate bloquea, 2 ante entrada inválida y 0 si queda elegible para revisión.

La API equivalente está en `deidflow.training.adaptation`:

```python
from deidflow.training.adaptation import (
    AdaptationConfig,
    PromotionCriteria,
    stage_span_adaptation,
    evaluate_adaptation,
    load_adaptation_jsonl,
)

stage_span_adaptation(
    "builtin:es-clinical",
    load_adaptation_jsonl("train.jsonl", split="train"),
    load_adaptation_jsonl("validation.jsonl", split="validation"),
    "candidate-01",
    config=AdaptationConfig(epochs=12, patience=3, seed=1729),
    criteria=PromotionCriteria(),
)
```

## Qué compara el gate

Los dos modelos se evalúan con la misma inferencia, sin márgenes adicionales,
y `Policy.strict()` de `DeidEngine`. No reutiliza perfiles builtin ni extrapola
el resultado a otras políticas, formatos o dominios. La evidencia contiene:

- Recall y precisión exactos por categoría: tipo y ambos límites deben coincidir.
- Fuga real de salida: caracteres gold no cubiertos por una transformación,
  documentos aprobados con fugas e intervalo Wilson del 95%.
- Conservación de contexto: proporción de caracteres no sensibles y no blancos
  transformados; positivos y negativos anotados en ambos holdouts.
- Categorías antiguas en la regresión, estados de aprobación/revisión y soporte
  observado. Sin soporte o sin documentos aprobados suficientes no hay éxito
  por ausencia de mediciones.

Defaults: al menos 100 documentos, 20 negativos y 5 aprobados en cada holdout;
20 spans por categoría; recall exacto ≥95%, precisión exacta ≥90%, recall de
caracteres de salida ≥99%, fuga aprobada 0% y sobre-redacción ≤2%. También se
bloquea cualquier caída de recall/precisión respecto al modelo base, aumento de
fuga aprobada o aumento de sobre-redacción. Son criterios de ingeniería, no
garantías estadísticas de riesgo cero. El intervalo Wilson permite ver la
incertidumbre incluso cuando se observan cero fugas.

Por defecto se exigen todas las etiquetas del candidato en test y todas las del
modelo base en regresión. `PromotionCriteria(target_types=(...))` permite acotar
el objetivo declarado, pero ninguna categoría añadida puede excluirse y las
categorías originales siguen requiriendo regresión. Los umbrales pueden
predeclararse con `--criteria archivo.json`, cuyos campos corresponden a esa
dataclass; no existe override de criterios en `evaluate`.

## Artefactos y límites de reproducibilidad

`stage` escribe `baseline.json`, `candidate.json`, `training.json`, `manifest.json`
y `manifest.sha256`. El manifiesto vincula SHA-256 de artefactos, corpus ordenado,
IDs, grupos, contenido normalizado y anotaciones, configuración, replay y gate.
El candidato recibe una versión propia `es-adapt-<digest>` derivada de sus pesos,
etiquetas y calibración; la versión/metadatos originales quedan bajo
`parent_version`/`parent_metadata`, sin fingir que es el modelo publicado original.

La evaluación escribe `evaluation.json` y `evaluation.sha256`, vinculados al
digest del stage. Incluye métricas y fingerprints, sin textos ni ejemplos crudos.
Se omiten tiempos, fecha y rutas absolutas para reconstruir bytes idénticos con
los mismos datos ordenados, código, versiones de dependencias y semilla.
Registrar también el commit y entorno del experimento en el expediente externo.
El orden de entrenamiento importa. No se promete igualdad entre distintas
versiones de NumPy/Python o cambios de implementación.

Ningún directorio de ejecución existente se sobrescribe. Se crean permisos
exclusivos del usuario (0700/0600 en POSIX; DACL protegida en Windows) antes de
escribir contenido. Un fallo puede dejar un directorio parcial que se debe
inspeccionar; no se considera evaluable sin todos los artefactos y digests.
Los hashes prueban integridad, no autoría ni anonimización: features y textos
hasheados pueden ser objeto de ataques de diccionario. Tratar modelos y
manifiestos procedentes de datos privados como sensibles.

## Demostración reproducible con datos ficticios

```bash
PYTHONPATH=src python scripts/adapt_span_tagger.py demo --output /tmp/demo-adaptacion-01
```

La demo inventa nombres, expedientes y plantillas separadas para cada rol.
Entrena un baseline pequeño para `PERSON`, lo adapta con 64 documentos y 48 de
replay, selecciona/calibra con 32 y evalúa 40 de test y 40 de regresión. No usa
datos reales, no descarga corpus ni modifica los modelos incorporados.
Reduce explícitamente el mínimo a 30 documentos y 10 negativos para mostrar
la mecánica; conserva los demás criterios. Devuelve 0 al ejecutarse aunque la
decisión de promoción sea `BLOCKED`.

Resultado medido de la demo incluida (30 spans por tipo, 10 negativos por holdout):

| Medida | Base | Adaptado |
|---|---:|---:|
| Recall exacto `PATIENT_ID`, test | 0% | 100% |
| Recall/precisión exactos `PERSON`, test | 100% / 100% | 100% / 100% |
| Recall/precisión exactos `PERSON`, regresión | 100% / 100% | 100% / 100% |
| Documentos aprobados con fuga, test | 0/40 | 0/40 |
| Sobre-redacción de contexto, test | 0% | 0% |
| Sobre-redacción de contexto, regresión | 0% | 0% |

La corrida final se repitió sobre `c651b9fe665ec4e2732a51609e791ed0fa4e90ce`.
El [reporte agregado](../benchmarks/results/product-v060-general2/posttraining-demo.json)
vincula manifiesto `f47c9301ca580ee9541ea7cb8228f3fdba14f61f3422b98d18d03b2c7d569c5e`
y evaluación `8b668bf68a6bf8a3b6495eef58e87b22588c104683bcd1329d7df08d264c0006`.
La demostración inicial tenía 1.523% de sobre-redacción de test; correcciones
generales de límites redujeron esa cifra a 0% en ambos modelos, por lo que esa
mejora no se atribuye al entrenamiento.

El tagger aprende una categoría nueva. **No se observó una mejora de fuga en la
salida completa**: las reglas ya cubrían esos expedientes ficticios en el baseline.
El gate bloquea porque la evidencia es ficticia, aunque las métricas de la demo
cumplen. La mejora medida demuestra que el mecanismo entrena; no justifica
reemplazar un builtin ni anunciar mejora clínica/financiera en producción.

No se encontró un corpus público anotado disponible en el entorno local de esta
implementación. La validación de dominio real sigue pendiente de datos públicos
con licencia o datos propios autorizados, con particiones y anotaciones revisadas.
