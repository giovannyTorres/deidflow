> **Registro histórico de la rama de implementación.** Este texto describe
> el trabajo conservado en [`f2e4751`](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-12.md),
> no una implementación incorporada a `master` ni una auditoría o CI de esta PR.
> Los enlaces fijados al commit permiten consultar evidencia que no se copia aquí.
> Consulte el [estado de esta revisión](benchmark-spec/README.md).

# BMX-12: perturbaciones textuales con referencia trazable

Implementación acotada sobre `70465c7b68cf3f57b0b6d5cb4c5f074b07ec5f73`,
después del cierre verificado de BMX-10 y BMX-11. Ticket:
[BMX-12](../tickets/benchmark-mx/12-perturbaciones.md). API, límites y
reproducción: [perturbaciones](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/BENCHMARK_MX_PERTURBATIONS.md).

Se entregan nueve recetas versionadas: mayúsculas, NFD completo, CRLF,
separadores, confusiones OCR simuladas, rotación real de columnas, posiciones
próximas a cortes, longitud/baja densidad y duplicación de objetivos/alta
densidad. Cada receta escribe su propio paquete admitido, con originales
intactos y un hijo por caso. No se aumentaron los presupuestos del cargador.
La pista solo admite texto de regresión conocida; no fabrica custodia de un
test ciego, ejecución OCR real, anotaciones revisadas ni muestras nuevas
independientes. No se modificaron detectores, políticas, transformadores ni
dependencias de producción.

Un mapa por punto de código conserva objetivos repetidos, anidados y cruzados,
expectativas por intervalo, vectores, cobertura y relaciones explícitas. La
proyección de NFD comprueba las superficies normalizadas, también en cobertura
parcial; límites no representables se rechazan. CRLF usa los caracteres vecinos
del intervalo. Columnas no corta ningún objetivo. Alta densidad duplica las
referencias completas y su cierre de identidad, no el texto entero como
sustituto de aumentar la densidad.

Los valores cambiados pasan a validez `unknown`, conservando `not_applicable`.
Las menciones hijas son `synthetic_fixture` con `reviews:[]`, y sus documentos
son `draft`. Los binarios, perfiles, revisiones y estados originales permanecen
sin cambios. Los vectores derivados requieren método `synthetic_derivation`,
evidencia nueva con hash, padre real, coordenadas proyectadas y validez coherente.
El cargador rechaza evidencia reutilizada, padres/particiones corruptos,
mapas/IDs malformados y revisiones o identidades inventadas.

El filtro público `strata: tuple[str, ...] | None` admite primero el paquete
completo y rechaza selecciones inválidas antes de invocar la candidata. `None`
conserva la forma previa. La suite admite todas las recetas antes de medir y
publica resultados reales limpios/perturbados por receta y estrato. Los estratos
pueden solaparse. Deduplica originales repetidos al contar casos únicos y asigna
el mismo peso a todos los IDs únicos de cada raíz, incluidos hijos que ya
existían en BMX-11. Los pesos por raíz suman uno; son contabilidad, no un F1
mezclado ni un bootstrap de falsa independencia.

TDD comenzó con un rojo real por ausencia del módulo público, antes de escribir
su implementación; siguió una primera admisión reproducible en verde. Ese
output inicial se conservó después desde el transcript y está etiquetado como
copia, sin fabricar un log redirigido original. Se extendieron después Unicode,
vectores, recetas, evaluación real, seguridad del destino y presupuestos. Los
fixtures mecánicos de prueba tienen límites literales explícitos, estado draft
y ningún revisor atribuido; no se confunden con la referencia revisada de BMX-11.

Una revisión previa de solo lectura reprodujo mediante nuevas pruebas tres
faltas: etiquetas reservadas que mezclaban pistas, intervalos CRLF representables
rechazados y cobertura NFD parcial trasladada a otra marca combinante. Se
corrigieron en red/green. También se corrigió la declaración del algoritmo
aleatorio: solo near_cut usa realmente `random.Random`; las demás recetas
conservan la generación original y registran su semilla en receta/evidencia.

La prueba pública de presupuesto amplía un fixture mecánico a 42 entidades y
55 etiquetas, con 504 pares previstos. Antes de la corrección se ejecutaban
1008 callbacks y luego se rechazaba el agregado sobredimensionado. Ahora se
codifica y presupuesta cada par antes de incorporarlo, se detienen los callbacks
restantes y no queda salida. El índice, evidencia y serialización final usan
el mismo codificador incremental acotado del escritor. Esto prueba admisión
acotada de salida; no afirma un límite duro de RSS.

Verificación del commit autor `52284a4`: **235 pruebas focalizadas** de perturbaciones, procedencia,
admisión, corpus, independencia y validación. Ruff, formato y mypy Python 3.12
pasan en los cuatro módulos modificados y sus tres archivos de pruebas.
No se ejecutó suite completa, cobertura, microbenchmark ni wheel en este paso;
pertenecen a la integración final del lote. Se conservan los cambios previos de
AGENTS.md, CLAUDE.md y docs/agents/ fuera de este incremento.

La [evidencia sanitizada](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-12-vectors.json) registra todas las recetas,
hashes, soportes, densidades y métricas sin valores fuente. Su SHA-256 es
`76d4d62ea2301b0f5fca26b24c49cb74a0b7b2719aa3a397cae38fa898a2acd0`.
El fingerprint histórico de fuentes Python de la candidata y el evaluador del
recorrido en `52284a4` es
`713dd6c45bc29ecb13aedf4e32a3e1df8eea78b2c814dcfdc3129a2a5499a0a8`.
Las cuatro suites se generaron dos veces con igualdad de bytes/hashes, y se
midieron con `rules.mx`, `detection-descriptive-v1`, semilla 17:

| Fuente | Casos serializados | Casos únicos | Pares limpio/perturbado |
| --- | ---: | ---: | ---: |
| Identificadores | 648 | 360 | 144 |
| Contextual | 180 | 100 | 99 |
| Estricto | 180 | 100 | 99 |
| Ambiguo | 36 | 20 | 27 |

Son **369 pares y 738 reportes reales** completados en `52284a4`. Las auditorías de las 36
combinaciones fuente/receta informan cero cruces entre particiones y conservan
`NO_BLIND_TEST` e `independence_accredited:false`. Los soportes ambiguos siguen
excluidos de métricas exhaustivas conforme al scorer vigente. Los errores de
rules.mx se conservan; no se ajustó la candidata ni la referencia para mejorar
sus cifras.

CRLF registra cero unidades cambiadas en estas fuentes porque sus saltos ya
están en CRLF o no hay saltos; la prueba literal LF sí verifica su conversión.
Contextual/estricto pasan de 29.6717 menciones por 1000 puntos de código a
0.2841 en baja densidad y 37.8727 en alta. Identificadores pasa de 9.6017 a
0.0456 y 15.3409, respectivamente; ambiguo, de 12.8205 a 0.0909 y 23.4375.
Son características del corpus sintético, no conclusiones de calidad.

El [ejemplo acotado](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/examples/benchmark-mx-perturbations/suite.json)
contiene solo NFD contextual, 20 casos serializados/únicos y 278949 bytes.
Índice SHA-256 `4e43b838336aa659e0d0e1e7807dca0fbcfde0d8386a9afa45cb539f5503e506`;
paquete `b54a1ab29cbbeffe4c9f5078b42d6e5748224577b229d1fcd27cc5ecdd2bc19a`.

Logs y reportes completos de esta sesión:
`/tmp/deidflow-batch/BMX-12/`. Los originales finales están en `runs-verified/`;
`reproduce.py` y `reproduce-verified.log` reproducen y registran el recorrido.
`tdd-transcript-copy.txt` identifica la copia inicial; `draft-*`, `budget-*`,
`provenance-selection-*`, `boundaries-*` y `report-budget-*` conservan los
recorridos posteriores reales. `focused-static-verified.txt` conserva los
comandos finales. `runs/` corresponde a un recorrido anterior; `runs-final/`
fue interrumpido al aparecer los dos defectos de frontera. Ninguno sustituye
los recibos finales ni se presenta como evidencia del código corregido.

La revisión fresca de Standards/Spec del commit queda registrada abajo por el
coordinador. Este acta no inventa su resultado ni ratifica calidad, independencia
ciega, generalización global, OCR real o facilidad de ajuste local.

## Delta de revisión

La revisión de Standards señaló un Data Clumps menor: la tupla devuelta por
`_edit` se repartía en cuatro diccionarios paralelos. `EditResult` mantiene ahora
texto, mapas de copias, rangos de relleno y parámetros juntos por unidad, con
tipos explícitos. Se regeneraron los 36 paquetes y los cuatro índices; todos
conservan los hashes publicados, incluido el ejemplo NFD contextual.

La revisión también encontró que el SHA de origen de una evidencia nueva solo
se validaba sintácticamente. Dos pruebas públicas cambiaron ese SHA y una
versión coherente del generador, reconstruyendo paquete, manifiesto, índice y
todos sus pins. Ambas fallaron realmente antes del arreglo y ahora se rechazan
antes de cualquier callback. La suite liga la evidencia de los vectores añadidos
al SHA de la fuente admitida, receta, semilla y versión del índice; comprueba
cantidad, método y pertenencia a unidades hijas nuevas. Una regresión pública
con `rules.mx` confirma que el prefijo y la evidencia histórica de una fuente
con derivaciones previas permanecen intactos. Esto no autentica declaraciones
de procedencia ni inventa revisión de referencia.

Verificación del delta: **238 pruebas focalizadas**, Ruff, formato y mypy Python
3.12 pasan. Logs `review-binding-{red,green}.txt`, `review-focused-static.txt` y
`review-hash-conformance.txt` en el directorio temporal indicado. Los 738 reportes
históricos no se volvieron a ejecutar por este refactor y cierre de admisión;
conservan su fingerprint original. La integración y revisión final del nuevo
commit corresponden al coordinador.

## Standards

Revisión independiente /root/bmx12_standards del diff
70465c7...3901470: **0 infracciones escritas y 0 juicios heurísticos pendientes**.
El juicio Low Data Clumps inicial se resolvió con EditResult: texto, mapas,
cobertura y parámetros permanecen juntos por unidad. La admisión vincula solo
los vectores nuevos a su origen, receta, semilla y versión, y preserva el ledger
histórico del origen. No quedaron hallazgos adicionales del baseline Fowler.

## Spec

Revisión independiente /root/bmx12_spec del mismo diff contra BMX-12,
AC-05/12/14 y ADR 0001: **0 faltantes/parciales, ampliaciones o errores**.
Reejecutó las dos manipulaciones con pins reconstruidos y la regresión del
ledger histórico: 3 pasan. Confirmó rechazo antes del callback y atribución
correcta de los 738 reportes a 52284a4.

Resultado por eje: Standards 0 pendientes, peor ninguno; Spec 0 pendientes,
peor ninguno. Código final revisado: 390147079908a7221098ca84af4befd3f48c88ff.
La suite integrada se ejecutó después; su resultado se registra por separado.

## Integración final del lote

Incremento verificado posteriormente con la suite completa, cobertura, estáticos,
microbenchmark y comparación fuente/wheel. Los resultados focalizados y hashes
anteriores conservan su fecha y alcance; no se atribuye retrospectivamente la
corrida final a esos commits. [Salud integrada vigente](BATCH_NEXT10.md) y
[recibo estructurado](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BATCH_NEXT10_CONTINUATION_HEALTH.json).
