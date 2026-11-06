# BMX-12: recetas Unicode, pista de desarrollo

Esta rama prepara un incremento sobre `f2e4751d280a100e5af450337d70db78a8fefa03`.
No es un PR pequeño contra master ni acredita que sus dependencias estén
fusionadas. **Auditoría Claude: pendiente.** No se autoriza ninguna fusión.

La comparación ejecuta motores locales separados: master
`44d04b16fb1ec545161c4ef0c14f516c7b0d9d29` y candidata Unicode
`3de9d732dca9a6df106a757836f0c8194be73916`. No modifica detectores, políticas,
pesos, dependencias ni perfiles para mejorar los resultados.

## Contrato de las recetas

Las nueve recetas predeterminadas se conservan. Las dos nuevas se solicitan
explícitamente; el generador se identifica como `mx-perturbations-1.1.0`.
Las suites históricas conservan sus recibos anteriores; el corredor actual
requiere la versión del generador actual.

Las dos recetas seleccionan únicamente menciones de PERSON, ADDRESS, RFC,
CURP, CLABE, PAYMENT_CARD, EMAIL y PHONE. No editan las palabras clínicas ni
los distractores no personales sin mención sensible. Esta selección v1 no
promete cobertura de todos los tipos de identificador de la taxonomía.

- `format_chars.v1`: inserta U+00AD, U+200B, U+200D, U+2060 o U+FEFF entre
  caracteres alfanuméricos de las menciones seleccionadas. Para una frontera
  original `b`, el índice en esa lista ordenada es `(seed + b) % 5`.
- `fullwidth.v1`: convierte los caracteres ASCII gráficos U+0021–U+007E de
  las menciones seleccionadas a U+FF01–U+FF5E. Conserva espacios, acentos y
  todo el texto que queda fuera de la selección.

Ningún control se inserta en un extremo de mención, vector, expectativa por
intervalo o región inspeccionada. Cada inserción pertenece al mapa del carácter
anterior. Así, una mención anidada o cruzada conserva su superficie completa
sin adquirir controles fuera de su referencia. Los intervalos no editables
pueden permanecer iguales y `changed_units` informa lo observado.

Los originales permanecen exactos. Los derivados conservan raíz, grupo,
plantilla y partición; registran semilla, parámetros, mapas y linaje. La validez
cambia a `unknown` solo cuando cambia la superficie, conservando
`not_applicable`; los estados desconocidos y los valores sin cambio no se
promueven. Los derivados siguen en borrador, sin revisión acreditada.

## Admisión independiente

El loader genérico valida estructura, referencias y coherencia de los vectores
con el mapa declarado. La admisión de la suite añade un verificador independiente
para las dos recetas nuevas: reconstruye texto y mapas desde el paquete original
suministrado, usando un barrido de eventos independiente del generador.

Se comprueban todos los caracteres y mapas, IDs deterministas, anotaciones,
expectativas, vectores, parámetros, procedencia y cobertura. También se comprueba
el caso sin vectores de validación. La verificación no importa `_parts`, `_edit`,
`_derive` ni el helper de edición Unicode. Un error impide ejecutar candidatos y
publicar informes; el mensaje externo no reproduce la entrada.

## Qué mide la comparación

La detección usa `run_perturbation_suite` con pares limpios/perturbados y estratos
separados. La transformación recibe gold explícito y se informa como
`transformation_gold_supplied`; no mide la detección del motor.

Las seis sondas H1/H2 son regresiones ficticias expuestas, con intervalos completos
escritos antes de la ejecución. Conservan la configuración solicitada:
`DeidEngine(country='ES')` y `Policy.strict(require_ner=False)`. Utilizan un esquema
propio porque el contrato DF-EVAL-MX exige país MX. U+200C se comprueba en pruebas
focalizadas; no se agrega a la lista de cinco controles de la receta.

El verificador inspecciona la salida real y los mapas de origen. Exige retirar
cada carácter del intervalo sensible completo mediante una sustitución constante
permitida. Una sustitución parcial del correo falla aunque desaparezca el literal
completo y el rescan del motor dé cero hallazgos. Se separan residuo confirmado,
remoción no verificable y salidas `APPROVED` con residuo confirmado. La retirada
completa no exige que una CURP incierta obtenga autorización de liberación.

Cada motor se ejecuta en su propio proceso con `-I -B`, raíz explícita y pins de
fuentes, módulos cargados, modelos y dependencias. Se verifican antes y después.
Los informes conservan agregados y hashes; no textos, valores, coordenadas
individuales ni salidas crudas. El guard de sockets de Python no es un sandbox
del sistema operativo.

Todo el material es ficticio y pertenece a regresión conocida. No se puntuaron
particiones de test intactas ni se acredita independencia, calidad de despliegue,
adopción de modelos o anonimato. No hay métricas inventadas para Gretel ni
consultas de red.

## Integración pendiente

La integración requiere primero especificación/tickets/ADR, los incrementos
verticales del arnés, BMX-10/BMX-11 y la base de BMX-12 en master. El tamaño del
lote original obliga a dividirlo más; esta preparación no cambia ese requisito.
La comparación puede usar la candidata Unicode fijada sin fusionarla.

La entrega conserva commits pequeños, evidencia focalizada y los bloqueos
externos. CI, revisión externa de Claude, hilos resueltos y aprobación de Giovanny
siguen siendo requisitos para cualquier fusión. Las comprobaciones integradas
completas las coordina el responsable del lote por separado.

## Resultados observados

Las seis sondas H1/H2 dieron 0/6 retiradas completas en la base y 6/6 en la
candidata. La base conservó residuo confirmado y devolvió `APPROVED` en los seis
casos. La candidata no conservó residuo confirmado: cinco casos quedaron
`APPROVED` y la CURP quedó `REVIEW_REQUIRED`. La sonda adicional U+200C, fuera del
denominador de seis, pasó de residuo con `APPROVED` a retirada completa.

Los siguientes son conteos exactos por corpus y receta. No se calcula F1 agrupado
entre recetas, estratos ni corpora. En identificadores hay 27 menciones declaradas;
una ambigua se excluye del soporte confirmado de 26. El corpus contextual tiene
47 menciones confirmadas. Las cifras limpias siguen mostrando limitaciones del
motor; recuperar ese comportamiento frente a ruido Unicode no acredita calidad
suficiente de detección.

| Corpus / receta | Base limpia TP/FP/FN | Base perturbada TP/FP/FN | Candidata limpia TP/FP/FN | Candidata perturbada TP/FP/FN |
| --- | --- | --- | --- | --- |
| Identificadores / format_chars | 23/10/3 | 0/9/26 | 23/10/3 | 23/10/3 |
| Identificadores / fullwidth | 23/10/3 | 1/9/25 | 23/10/3 | 23/10/3 |
| Contextual / format_chars | 2/3/45 | 1/3/46 | 2/3/45 | 2/3/45 |
| Contextual / fullwidth | 2/3/45 | 1/3/46 | 2/3/45 | 2/3/45 |

La transformación con gold suministrado retiró 26/26 objetivos en identificadores
y 18/18 en contexto, tanto limpios como perturbados, en ambos motores. Los
requisitos de revisión siguen informándose por separado: esta cifra de retirada
no convierte todo el perfil en aprobado. No se alteró el gold para producirla.

En los 36 documentos de identificadores cada receta cambió 27 unidades y dejó
intactos los nueve distractores. En los diez documentos contextuales cambió nueve
unidades. Ambas suites contienen los cinco controles pedidos; los histogramas,
los resultados por entidad y los pins están en el recibo sanitizado.

Para conservar incrementos revisables, la extensión se divide después de esas
bases: primero recetas/admisión/pruebas, después comparador/evidencia/pruebas.
Cada futuro PR deberá partir de master con sus dependencias ya integradas y
contar con su propia auditoría y aprobación. Los commits de preparación no
sustituyen esos pasos.

El CLI prepara una caché privada de bytecode vacía antes de importar el evaluador;
rechaza módulos DeidFlow precargados. Cada worker hace lo mismo antes de importar
su candidato. Se impiden escrituras de bytecode y se comprueba que las cachés
siguen vacías. `-B` por sí solo no impediría leer `.pyc` existentes. El recibo fija
también los módulos del evaluador y sus hashes antes/después.

Los paquetes derivados existen únicamente como recursos temporales privados.
Se eliminan de la zona de trabajo antes de publicar: la carpeta de comparación
solo conserva informes agregados. Los mapas y el gold pueden regenerarse desde
el manifiesto original, la semilla y los helpers fijados; no se publican sus
coordenadas individuales en los informes.

## Revisión y comprobaciones locales

El incremento de recetas/admisión y sus regresiones existentes pasó 42 pruebas
focalizadas antes de la revisión. La revisión de especificación encontró dos
casos límite: tipos JSON de offsets sin vectores y cobertura de unidad vacía.
Ambos se reprodujeron en rojo y quedaron corregidos; las 15 pruebas de recetas
pasan. El grupo focalizado completo de ese código y el comparador inicial pasó
50 pruebas en 59.83 s.

La revisión posterior encontró paquetes crudos dentro de la carpeta publicada y
lectura posible de bytecode previo. Se corrigieron y se comprobó la publicación
con motores reales: solo informes agregados, sin JSONL de entradas ni paquetes
fuente. Las seis pruebas finales del comparador pasan con caché externa vacía,
y el guard de caché del worker queda registrado en cero entradas antes/después.
Ruff, formato y mypy focalizados pasan. No se ejecutó aquí la suite integrada,
cobertura, microbenchmark ni build; los coordina el responsable del lote.

La revisión interna Matt de Standards y Spec abarca el delta desde `f2e4751`.
Se corrigieron también dos juicios menores de nombres/agrupación de datos.
No es una auditoría externa de Claude ni una autorización de fusión. Los recibos
roja/verde y sus hashes se registran sin copiar textos de las pruebas.

## Recibos y reproducción

[Comparación sanitizada](comparison.json) · [Verificación y pins](verification.json).
El código revisado es `12e9d061debc1a13452ee384e8c4e7b0a664471b`.
El SHA-256 de la comparación es
`2b69ad79c95b086da7896310d35bdb8722b2aba08cf97f98e04332275d6fe73f`.
Las revisiones finales de Standards y Spec no dejaron hallazgos pendientes;
la revisión de Spec fue de código y no inventa una revisión de la corrida aún
pendiente en ese momento. El recibo final se comprobó después de su ejecución.

Los 221 archivos publicados de la corrida final son `report.json` agregados.
Los informes por estrato completos permanecen localmente en
`/tmp/deidflow-bmx-unicode-evidence/comparison-actual-v4/`; sus informes padres
están ligados por hash en `comparison.json`. Las corridas v1–v3 son repeticiones
históricas de desarrollo y no sustituyen la evidencia final v4. Solo el recibo
final sanitizado se incorpora al repositorio.

Con dependencias locales ya instaladas y destinos nuevos, reproducir desde la
raíz de esta preparación:

```sh
TASK_UNICODE_CACHE="$(mktemp -d /tmp/deidflow-bmx-eval-cache.XXXXXX)"
PYTHONPATH="$PWD/src" /workspace/deidflow/.venv/bin/python -B \
  -X "pycache_prefix=$TASK_UNICODE_CACHE" scripts/compare_bmx_unicode.py \
  --baseline-root /workspace/deidflow-unicode-base \
  --fixed-root /workspace/deidflow-unicode-fixed \
  --source examples/benchmark-mx-identifiers \
  --source examples/benchmark-mx-contextual/contextual \
  --seed 17 --output /tmp/deidflow-bmx-unicode-comparison-new
rmdir "$TASK_UNICODE_CACHE"
```

El CLI añade su propio bootstrap de caché vacía antes de importar DeidFlow y
verifica las revisiones exactas predeterminadas. Los manifiestos, helpers,
fuentes, modelos y dependencias quedan fijados en el recibo. Tiempos operativos
y hashes de informes con fecha pueden cambiar entre repeticiones; los hashes de
las suites, anotaciones y resultados tipados deterministas conservan su contrato.
