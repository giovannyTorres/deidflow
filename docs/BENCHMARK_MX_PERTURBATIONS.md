# Perturbaciones textuales es-MX

BMX-12 genera pistas descriptivas de regresión conocida. Cada receta conserva
los registros originales y añade un hijo por documento en un paquete propio.
Así se respeta el límite de manifiesto de 64 KiB, sin ampliar presupuestos ni
tratar los derivados como observaciones independientes. Solo se admiten fuentes
de texto en `known_regression`; entrenamiento, test ciego y etiquetas de origen
reservadas `perturbation:` se rechazan.

La inferencia sigue siendo local, gratuita y sin descargas. El ruido OCR de esta
pista es una sustitución textual simulada: no ejecuta Tesseract ni acredita OCR
real. Los perfiles y resultados permanecen sin ratificación de calidad y en
`DESCRIPTIVE_ONLY`. Se conservan las decisiones de sensibilidad y contexto de
[ADR 0001](adr/0001-bmx-09-operational-profiles-v1.md).

## Recetas versión 1

| Receta | Operación real |
| --- | --- |
| `uppercase.v1` | Mayúsculas Unicode, incluida expansión de `ß` a `SS`. |
| `nfd.v1` | `unicodedata.normalize("NFD", texto)` completo, incluido Hangul. |
| `crlf.v1` | Convierte saltos aislados a CRLF y conserva pares existentes. |
| `separators.v1` | Sustituye cada espacio por tabulador, espacio, barra y espacio. |
| `ocr_simulated.v1` | Confusiones declaradas `O/o→0`, `I/l→1`, `S→5`. |
| `columns.v1` | Rota dos bloques en un corte de espacio que no atraviese ningún objetivo. |
| `near_cut.v1` | Sitúa la primera mención junto a 64, 256, 1024 o un corte posterior, con desplazamiento −1/0/+1. |
| `long_low_density.v1` | Añade 8192 puntos de código de texto neutro en cada extremo. |
| `high_density.v1` | Añade una copia de la unión de intervalos objetivo, con separadores; duplica todas sus referencias. |

Se registran receta, versión, semilla y parámetros por unidad. Solo `near_cut`
usa `random.Random(seed).choice`; las demás operaciones son deterministas y
conservan el descriptor de generación de los originales. Los IDs nuevos usan
SHA-256 sobre la huella del paquete, receta, semilla, ID original y número de
copia. La repetición se garantiza dentro del mismo entorno Unicode/Python.

Una receta puede no cambiar alguna unidad: se informa `changed_units` y no se
presenta una unidad idéntica como evidencia perturbada. Las dos densidades
informadas son menciones por 1000 puntos de código y fracción de caracteres
cubierta por la unión de menciones. La densidad se mide; copiar texto completo
no se usa como sustituto de aumentarla. Un caso sin objetivos puede no cambiar.

## Referencia, coordenadas y linaje

Se puntúa el texto emitido, sin una normalización posterior. El mapa explícito
asigna cada punto de código original a su intervalo de salida; admite expansión,
reordenamiento y dos copias. Se proyectan menciones anidadas/cruzadas, expectativas
por intervalo, vectores de validación y cobertura inspeccionada. Nunca se busca
una superficie con `str.find` para reconstruir sus coordenadas.

NFD se aplica al texto completo. Se acumulan las longitudes por carácter y se
comprueba que cada objetivo y rango inspeccionado proyectado coincide con NFD
de su intervalo original. Si la reordenación de marcas combinantes impide esa
representación, se rechaza el derivado. CRLF interpreta los caracteres vecinos
para conservar también intervalos que terminan dentro de un par existente.
Las columnas eligen cortes fuera de todas las menciones, expectativas y vectores.

Los hijos conservan `root_document_id`, grupo, familia, partición y panel, y
señalan al padre inmediato. Se reconstruyen los SHA de texto/fuente y todos los
hashes de recursos y perfiles mediante `write_package_records`. La fuente de
varias unidades usa el hash enmarcado exigido por el cargador. Los recursos
binarios y los perfiles originales se copian sin cambios.

Las menciones hijas son `synthetic_fixture`, con `reviews=[]`, y los documentos
hijos quedan en `draft`. No se afirma que sus nuevos valores hayan sido
revisados. Las relaciones explícitas conservan el ID de identidad original y
remiten a los IDs de mención hijos, incluidas relaciones entre documentos y las
copias densas; no se fusionan homónimos ni se resuelven alias.

Cuando cambia el valor de un objetivo, patrón/estructura/checksum pasan a
`unknown`, salvo `not_applicable`. El original conserva su oráculo. Los vectores
hijos usan `synthetic_derivation` y una evidencia binaria nueva con hash, mapa y
enlace al vector padre. El cargador exige un documento hijo real, proyección
válida, validez coherente y ausencia de revisión/identidad inventada. Este
contrato no convierte una derivación en referencia independiente.

El evaluador de suite liga la evidencia de los vectores nuevos al hash de la
fuente admitida, receta, semilla y versión del índice. Conserva sin reinterpretar
la evidencia histórica de los vectores que ya estaban en la fuente.

El texto añadido está declarado como relleno sintético no personal. La cobertura
mantiene las limitaciones originales y añade `SYNTHETIC_DERIVATION_NOT_REVIEWED`;
no convierte una categoría originalmente no exhaustiva en exhaustiva.

## Uso público

```python
from deidflow.benchmarks.perturbation_package import (
    generate_perturbation_suite,
    run_perturbation_suite,
)

source = "examples/benchmark-mx-contextual/contextual"
digest = "89dcd192cda75e6d9465742d4e4890181823eb596ec49117f65d985dd1e2296c"
suite = generate_perturbation_suite(
    source,
    manifest_sha256=digest,
    destination="/tmp/mx-perturbations",
    seed=17,
    # Omitir recipes ejecuta las nueve. Un ejemplo acotado:
    recipes=("nfd.v1",),
)
report = run_perturbation_suite(
    source,
    manifest_sha256=digest,
    suite="/tmp/mx-perturbations",
    index_sha256=suite["index_sha256"],
    candidate="rules.mx",
    profile="detection-descriptive-v1",
    output="/tmp/mx-perturbation-reports",
)
```

Los destinos deben ser nuevos y estar fuera de la fuente y la suite. No se
sobrescribe una salida existente. Se construyen los paquetes en un temporal
propio, se admiten antes de publicarlos y se publica el índice completo al final
mediante rename. La reserva exclusiva del destino y la limpieza se limitan a
directorios creados por esta operación; un fallo no borra datos ajenos.

La suite limita la entrada a 50 000 puntos de código y 512 unidades; también
respeta los límites de registros, recursos, manifiesto y paquete existentes.
El índice tiene un máximo de 2 MiB. La evaluación admite hasta 512 pares de
reportes y limita incrementalmente el agregado a 16 MiB. Estos límites acotan
la admisión de salida; no son una garantía de RSS del proceso.

## Lectura de resultados

`run_package_benchmark(..., strata=("nombre",))` filtra documentos que contengan
cualquiera de las etiquetas solicitadas. Primero admite **todo** el paquete;
solo después filtra y ejecuta la candidata. Rechaza tuplas vacías, duplicados,
etiquetas desconocidas y selecciones sin casos. `strata=None` conserva el formato
de resultado anterior.

`run_perturbation_suite` admite todas las recetas antes de invocar la candidata.
Escribe un par limpio/perturbado por receta para todos los casos y por cada
estrato original. Ambos lados ejecutan la candidata real y conservan sus
soportes, exclusiones, errores, métricas y limitaciones. El agregado contiene
estos resultados separados y rutas de sus reportes. Los estratos pueden
solaparse; no se suman sus soportes.

El índice diferencia casos serializados y casos únicos. Los originales repetidos
en varios paquetes se deduplican por ID dentro de la fuente fijada por hash.
Cada ID único del mismo `root_document_id` recibe el mismo peso, y los pesos de
ese origen suman uno. Esto incluye variantes que ya existían en la fuente, como
la narrativa con/sin puntos de BMX-11. Los pesos son contabilidad del linaje:
no se aplican a los reportes separados ni se publica un F1 combinado, una mejora
global por añadir variantes o un bootstrap de falsa independencia.

El [ejemplo incluido](../examples/benchmark-mx-perturbations/suite.json) contiene
solo NFD sobre la referencia contextual. La [auditoría BMX-12](audit/BMX-12.md)
registra las nueve recetas sobre identificadores, contextual, estricto y ambiguo.
