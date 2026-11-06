# Especificación técnica: benchmark local de DeidFlow para español mexicano

**Identificador:** DF-EVAL-MX · **Versión de especificación:** 0.1.0.

**Estado:** propuesta técnica implementable del arnés; pendiente de ratificación
del perfil operativo y de los umbrales de calidad. No implementada.
Publicación documental de revisión; no supone ratificación ni calificación operativa.

Esta especificación desarrolla los requisitos de la solicitud y el borrador de
diseño previo. No presenta como acuerdos las respuestas que no se recibieron en
la ronda de preguntas. Las decisiones técnicas de este documento son propuestas
normativas para la futura implementación; no son resultados de evaluación.

## Problem Statement

DeidFlow necesita evidencia reproducible sobre detección y transformación de
información sensible en español mexicano. Las pruebas existentes cubren muchas
regresiones, pero un F1 de detección, una cobertura de código alta o un estado
`APPROVED` no demuestran por sí mismos ausencia de información residual ni
conservación del contexto.

Los instrumentos actuales tienen alcances distintos: matching de spans,
cobertura de detección, cobertura declarada por mapas de transformación y
comprobación de sustituciones/contexto realmente emitidos. Algunos corpus ya
participaron en entrenamiento o diagnóstico; otros son de España, sintéticos
de estilo europeo o documentos públicos sin anotación exhaustiva. No se deben
combinar esos resultados como si fueran un test mexicano independiente.

La evaluación debe distinguir errores del detector, de la política, del
transformador, de la extracción y de la verificación del formato. También debe
mostrar el coste de revisión, los casos no evaluados y la incertidumbre de sus
conclusiones.

## Solution

Construir un arnés de evaluación completamente local que consuma un paquete de
datos versionado, una configuración congelada del sistema evaluado y un perfil
de evaluación explícito. Producirá resultados agregados e inspeccionables para
cuatro pistas separadas:

1. **Validación:** formato, estructura y checksum de identificadores.
2. **Detección:** menciones y categorías sobre texto de referencia.
3. **Transformación aislada:** operadores y política usando menciones de
   referencia, sin atribuirles errores del detector.
4. **Pipeline completo:** documento de entrada, salida real, cobertura del
   artefacto, utilidad y decisión de liberación.

La ejecución evaluará una configuración; no entrenará, ajustará, promoverá ni
reparará automáticamente el sistema. Un fallo de calidad debe conservarse en
el informe, no desaparecer mediante cambios de configuración posteriores a la
observación del test.

El resultado será un panel por entidad, formato, estrato, pista y perfil; no un
único número que permita esconder un identificador mal protegido detrás de
miles de correos correctamente procesados.

## User Stories

1. Como mantenedor, quiero repetir una evaluación con los mismos datos y pesos
   para obtener los mismos conteos y decisiones de calidad.
2. Como evaluador, quiero medir RFC, CURP y CLABE por separado para no perder
   errores mexicanos dentro de categorías genéricas.
3. Como evaluador, quiero medir tarjetas, teléfonos, correos, nombres,
   direcciones y categorías clínicas con soporte y errores por entidad.
4. Como evaluador, quiero separar validez matemática y sensibilidad para no
   tratar automáticamente un identificador defectuoso como dato inocuo.
5. Como anotador, quiero conservar offsets del texto original para evaluar
   espacios, Unicode, saltos y errores OCR sin alterar las coordenadas.
6. Como anotador, quiero representar entidades anidadas y parcialmente
   superpuestas para no simplificar artificialmente la referencia.
7. Como anotador, quiero marcar ambigüedad y adjudicación para no convertir una
   interpretación dudosa en verdad indiscutible.
8. Como evaluador, quiero separar texto limpio, ruido textual simulado y OCR
   real para atribuir correctamente sus fallos.
9. Como evaluador, quiero probar homónimos sin exigir que el sistema adivine
   identidades que no están demostradas en la entrada.
10. Como usuario clínico, quiero comprobar conservación de negaciones, dosis y
    cantidades cuando el perfil exige preservarlas.
11. Como responsable de privacidad, quiero inspeccionar contenido recuperable
    del artefacto final, incluidos metadatos y partes ocultas.
12. Como responsable de privacidad, quiero distinguir fuga en una candidata
    para revisión de fuga en una salida aprobada automáticamente.
13. Como usuario, quiero que bloquear todos los documentos no equivalga a una
    transformación perfecta.
14. Como desarrollador, quiero aislar el transformador con menciones correctas
    antes de atribuirle los falsos negativos del detector.
15. Como mantenedor, quiero conservar regresiones conocidas sin presentarlas
    como un conjunto ciego nuevo.
16. Como custodio, quiero impedir que documentos, plantillas o derivados crucen
    entrenamiento, ajuste y evaluación independiente.
17. Como custodio, quiero registrar exposición previa del modelo y de los
    desarrolladores para declarar el alcance real de la independencia.
18. Como revisor de datos, quiero comprobar permisos de evaluación, anotación,
    derivación y redistribución por fuente antes de incorporarla.
19. Como operador, quiero ejecutar sin Internet, APIs de inferencia, telemetría
    ni descargas automáticas de modelos o corpus.
20. Como operador, quiero límites de tamaño, memoria y tiempo con resultados
    explícitos cuando un caso no puede completarse.
21. Como evaluador, quiero precisión, recall, F1, FP y FN con denominadores y
    reglas de matching explícitos, incluso cuando una métrica es indefinida.
22. Como responsable de una versión, quiero que un umbral se fije antes de
    abrir el test y no se ajuste para hacer pasar un candidato ya medido.
23. Como responsable de una versión, quiero separar validez de la ejecución,
    conformidad del arnés y calidad del candidato.
24. Como auditor, quiero verificar hashes, configuración, activos, anotaciones
    y resultados sin recibir documentos originales, claves o valores sensibles
    en los logs públicos.
25. Como implementador, quiero reutilizar los instrumentos existentes a través
    de sus interfaces, evitando una dependencia obligatoria nueva o cambios en
    las interfaces de producción sin una necesidad demostrada.

## Implementation Decisions

### 1. Requisitos confirmados y decisiones propuestas

Se consideran confirmados los requisitos explícitos: español mexicano,
categorías solicitadas, casos válidos/inválidos, fuentes públicas legalmente
utilizables, perturbaciones, solapamientos, homónimos, conservación, medición
residual, separación de pistas y particiones, ejecución local y ausencia de
implementación en esta tarea.

| Decisión | Propuesta técnica de v0.1 | Condición de uso |
| --- | --- | --- |
| D1: uso operativo | Calificación de apoyo supervisado; liberación automática como resultado separado | No autoriza liberación automática ni sustituye validación de despliegue |
| D2: valores inválidos | Separar sensibilidad y validez; proteger o escalar identificadores personales plausibles aunque fallen checksum | Cada mención debe tener referencia explícita; un distractor no personal sigue siendo negativo |
| D3: clínica | Dos perfiles: contexto preservado y estricto | Los dos usan las mismas menciones de detección, pero expectativas de transformación diferentes |
| D4: matching principal | Categoría y límites exactos, emparejamiento máximo uno a uno | Solapamiento/cobertura se informan como diagnósticos distintos |
| D5: formato inicial | Núcleo textual y expansión por capacidades de formato declaradas | Un formato no implementado no recibe un resultado positivo ficticio |
| D6: calidad de versión | Perfil de calidad versionado, ratificado y congelado antes del test | Sin él solo se emite evaluación descriptiva, nunca una aprobación profesional |

D1–D3 proceden de recomendaciones aún no respondidas explícitamente. No se
crean ADRs aceptados para ellas. La implementación del arnés puede recibirlas
como configuración obligatoria; la calificación operativa exige ratificación.

### 2. Arquitectura y responsabilidades

Se establece una seam principal de prueba: **paquete de evaluación + descriptor
del candidato + perfil explícito → informe verificable**. Las pruebas del arnés
deben cruzar esta interfaz observable. Las seams internas se usarán únicamente
para aislar fuentes reales de variación, como adapters de formato y OCR.

| Módulo lógico | Responsabilidad | Debe evitar |
| --- | --- | --- |
| Cargador de paquetes | Validar esquema, recursos, hashes, límites y relaciones de anotación | Descargar datos o aceptar referencias inconsistentes |
| Auditor de independencia | Comprobar grupos, duplicados, linajes, exposición y autorización de uso | Equiparar hashes distintos con independencia |
| Adaptador del candidato | Invocar validadores, detección, transformación o pipeline configurados | Consultar el gold para mejorar predicciones o cambiar parámetros |
| Ejecutor local | Aislar casos, prohibir red, imponer límites y registrar resultados | Reintentar con otros umbrales hasta conseguir aprobación |
| Evaluador de referencia | Calcular matching, privacidad, conservación y completitud | Acreditar eliminación solo por mapas o por el propio detector |
| Inspectores de artefactos | Inventariar contenido recuperable según formato y verificar expectativas | Convertir contenido desconocido o ilegible en ausencia de fuga |
| Agregador y calificador | Publicar conteos, estratos, intervalos y veredictos reproducibles | Excluir silenciosamente casos difíciles o inventar soporte |

Reutilización prevista:

- La interfaz de detección del motor y los adapters NLP existentes, sin cambiar
  los reconocedores para acomodar este benchmark.
- El matching uno a uno del evaluador existente, extendiendo su informe por
  categoría y aclarando semánticas que actualmente se agregan.
- Los controles de partición de adaptación como precedente; su cargador de
  entrenamiento no será el cargador general de evaluación porque rechaza
  solapamientos que aquí son válidos.
- El evaluador de contexto como precedente para comprobar bytes emitidos y
  tramos preservados, sin trasladar sus restricciones particulares de gold a
  todo el benchmark.
- La transformación textual existente como seam para la pista aislada.

No se introduce un sistema genérico de plugins ni se reorganiza la biblioteca
completa. Si un formato necesita una seam adicional, debe justificarse por su
capacidad real de extracción/transformación y probarse con al menos los adapters
de producción y de referencia correspondientes.

### 3. Paquete versionado y estructura de datasets

El paquete será autocontenido para evaluación offline. Sus recursos se
identificarán por roles lógicos y referencias relativas declaradas en un
manifiesto; el lector no dependerá de rutas absolutas de una máquina.

| Recurso lógico | Formato | Contenido |
| --- | --- | --- |
| Manifiesto | JSON UTF-8 | Versiones, recursos, hashes, alcance, particiones y perfiles |
| Fuentes | JSONL UTF-8 | Procedencia, derechos, geografía, uso permitido y exposición |
| Documentos | JSONL UTF-8 | Identidad de casos, grupos, linaje, formato y referencias a unidades/artefactos |
| Unidades textuales | JSONL UTF-8 | Texto original de referencia y localización dentro del documento |
| Menciones | JSONL UTF-8 | Spans o regiones, categorías, validez, certeza e identidad ficticia cuando exista |
| Expectativas | JSONL UTF-8 | Acciones y contexto requerido por perfil y mención |
| Artefactos | Binarios por hash | Documentos, imágenes y recursos locales autorizados |
| Anotación y adjudicación | JSONL UTF-8 | Revisión de referencia, desacuerdos y resolución |
| Auditoría de particiones | JSON | Grupos y coincidencias examinadas, exposición y conflictos |

Cada recurso declarado tendrá hash SHA-256, tamaño y número de registros
esperados. El manifiesto raíz llevará versión de esquema y versión del dataset;
el hash del manifiesto se entrega al ejecutor como referencia de confianza.
Un hash comprueba integridad, no identidad jurídica del editor.

Las particiones son `train`, `validation`, `calibration` y `blind_test`. Los
paneles `known_regression` y `external_transfer` son recursos/paneles separados;
no se suman al resultado de `blind_test`. Una partición puede estar vacía solo
si el manifiesto lo declara y su función no se utiliza. El ejecutor no crea ni
reparte automáticamente las particiones durante una evaluación final.

No se fija una proporción universal de partición. El manifiesto debe declarar
soporte requerido por entidad y estrato; un perfil de calificación debe fijar
sus mínimos antes del congelamiento. No alcanzar soporte genera evidencia
insuficiente, no una categoría eliminada del informe.

Habrá dos niveles de datos: fixtures pequeños para verificar el arnés y corpus
de calificación. Un fixture que cubre una entidad no acredita tamaño de muestra
para una conclusión de calidad. No se generan corpus en esta tarea.

### 4. Contratos de datos

#### 4.1 Reglas comunes

- JSON estricto: rechazar claves duplicadas, números no finitos, versiones no
  soportadas y campos no reconocidos fuera de un espacio de extensiones
  versionado.
- Identificadores opacos únicos; ningún identificador de registro contiene
  nombres, correos, documentos de identidad o nombres de archivos originales.
- Referencias relativas deben permanecer dentro del paquete: rechazar traversal,
  enlaces que escapan del recurso autorizado y miembros ZIP duplicados.
- Strings UTF-8 válidos. Los offsets se calculan sobre puntos de código Unicode
  del texto original, base cero e intervalo semiabierto; no bytes ni unidades
  UTF-16. No normalizar texto antes de puntuar límites.
- Ordenación canónica por identificadores y por coordenadas para serializar
  resultados. La representación canónica tendrá versión y reglas explícitas
  de serialización: claves ordenadas, separadores compactos, caracteres Unicode
  emitidos en UTF-8 sin escapes ASCII innecesarios, sin BOM ni números no
  finitos. Los recursos binarios se hashean en sus bytes originales. El hash
  del manifiesto se registra fuera del contenido que ese mismo hash resume,
  para evitar autorreferencia.

#### 4.2 Manifiesto

| Campo | Tipo / restricción |
| --- | --- |
| `schema_version`, `dataset_version`, `taxonomy_version`, `annotation_version` | Strings versionados obligatorios |
| `dataset_id`, `created_at` | ID opaco y timestamp UTC; no intervienen como semilla implícita |
| `resources` | Mapa de roles a referencia relativa, hash, tamaño y conteo |
| `partitions` | Relación de casos/grupos por partición; sin duplicados cruzados |
| `panels` | Regresión conocida y transferencia externa identificadas separadamente |
| `scope` | Idioma, país objetivo, entidades, formatos y estratos obligatorios/opcionales |
| `profiles` | Referencias y hashes de políticas/expectativas de evaluación |
| `generation` | Versión de generador, algoritmos de aleatoriedad, semillas, recursos y reglas de perturbación, si aplica |
| `freeze` | Hashes congelados y fecha de congelamiento; estado de exposición y custodia |
| `annotation_coverage` | Categorías exhaustivas, zonas inspeccionadas y limitaciones conocidas |

#### 4.3 Fuente y permisos

| Campo | Tipo / restricción |
| --- | --- |
| `source_id`, `revision`, `content_sha256` | Identidad y versión exactas |
| `origin_kind` | `synthetic`, `licensed_public_nonpersonal` o `external_transfer` |
| `language`, `country`, `domain` | Procedencia declarada; no inferida por el país objetivo del benchmark |
| `origin_reference`, `terms_reference` | Referencia de origen y copia/localización de términos revisados |
| `license`, `attribution` | Licencia y obligaciones; `unknown` no autoriza uso |
| `permissions` | Evaluación, anotación, derivación, entrenamiento y redistribución como permisos separados |
| `permission_review` | Fecha, evidencia y estado de la revisión; no dictamen jurídico inventado |
| `personal_data_status` | Para el núcleo autorizado: ficticio o comprobado no personal; si es incierto, excluir |
| `exposure` | Entrenamiento, ajuste, evaluación previa y exposición conocida/desconocida del candidato |

Un origen público o una licencia de acceso no garantizan ausencia de datos
personales ni permiten todos los usos. Las fuentes con términos inciertos no
entran al paquete oficial. Una fuente permitida solo para evaluación no se
redistribuye ni se usa para entrenamiento. No se selecciona automáticamente un
documento del registro público existente como si ya tuviera autorización y gold.

#### 4.4 Documento, unidad y linaje

| Campo | Tipo / restricción |
| --- | --- |
| `case_id`, `source_id`, `root_document_id` | Identidad del caso, fuente y origen anterior a perturbaciones |
| `group_id`, `template_family_id` | Grupo de independencia y familia documentada; sin fallback automático a ID de fila |
| `parent_case_id`, `variant_id` | Relación explícita de derivados; sin ciclos |
| `partition`, `panel` | Pertenencia declarada y validada |
| `format`, `strata`, `capabilities_required` | Tipo de artefacto y condiciones de evaluación |
| `artifact_ref`, `artifact_sha256` | Recurso original, si el caso no es solo textual |
| `unit_ids` | Unidades textuales o regiones que pertenecen al caso |
| `perturbation_recipe` | Operaciones, parámetros, semilla y versión; vacía para referencia sin perturbación |
| `annotation_state` | `adjudicated`, `draft` o `unresolvable`; solo adjudicados en métricas primarias oficiales |

Una unidad textual contiene `unit_id`, `case_id`, `text`, `text_sha256`,
`content_role` y `locator`. El localizador identifica párrafo, celda, ruta
estructurada, parte/atributo, cuerpo MIME o región de página, según formato.
No utiliza sin verificar los IDs de fragmentos que produzca el candidato.

Las coordenadas visuales declaran página, sistema de coordenadas, dimensiones,
rotación y escala. El texto OCR observado y la referencia visual original son
unidades distintas con alineación explícita; no se sustituyen uno por otra.

#### 4.5 Menciones y ambigüedad

| Campo | Tipo / restricción |
| --- | --- |
| `mention_id`, `unit_id` | Identidad y unidad de referencia |
| `entity_type` | Categoría de la taxonomía, obligatoria para menciones objetivo |
| `start`, `end` | Enteros no booleanos, dentro de la unidad, no vacíos; opcionales solo cuando el contrato visual usa una región explícita |
| `region_ref` | Localización visual anotada para pistas que la requieren |
| `certainty` | `confirmed` o `ambiguous`; referencia adjudicada del alcance |
| `validity` | Patrón, estructura y checksum como valores separados `valid`, `invalid`, `not_applicable` o `unknown` |
| `sensitivity_reference` | Justificación categórica y de contexto; no derivada del score de DeidFlow |
| `entity_id`, `identity_evidence` | Identidad ficticia opcional y evidencia observable de vinculación; desconocido se representa explícitamente |
| `annotation_provenance` | Método, revisiones y versión del manual de anotación |

Se permiten spans anidados y parcialmente cruzados. Se rechazan duplicados
idénticos por tipo/unidad/span, offsets fuera de rango, referencias inexistentes
y contradicciones de adjudicación. No se exigen límites del tokenizer del
candidato. Los separadores internos de un identificador forman parte del span;
la etiqueta del campo y la puntuación externa quedan fuera salvo que la guía
versionada de la categoría establezca una excepción.

Taxonomía mínima distinguible: `RFC`, `CURP`, `CLABE`, `PAYMENT_CARD`, `PHONE`,
`EMAIL`, `PERSON` y `ADDRESS`; clínica desglosada al menos en `DIAGNOSIS`,
`MEDICAL_CONDITION`, `MEDICATION`, `TREATMENT` y `CLINICAL_OBSERVATION` cuando
formen parte del alcance declarado. Otras categorías se declaran expresamente;
no se tratan como texto negativo por falta de anotación.

La referencia declara exhaustividad por categoría/unidad. Solo las categorías
exhaustivamente anotadas permiten puntuar FP sin reservas. Predicciones fuera
del alcance aparecen como tales en el informe. Una equivalencia con categorías
genéricas de corpus externos es una vista secundaria versionada, no una
conversión guiada por el gold que rescate errores de tipo en la vista mexicana.

#### 4.6 Expectativas por perfil

Cada expectativa relaciona perfil, caso/mención o span de contexto, acción
requerida (`remove`, `preserve`, `generalize` o `review_required`), operadores
permitidos, condiciones de verificación, cobertura requerida y estados de
liberación aceptables. El formato limita los operadores: por ejemplo, censura
física de PDF no se equipara a insertar un marcador editable.

Los perfiles deben declarar el tratamiento de datos clínicos y
cuasiidentificadores. Retener clínica deliberadamente no convierte esa clínica
en información no sensible universal. Las expectativas contradictorias sobre
el mismo contenido hacen inválida la configuración, salvo una precedencia
documentada y explícita del perfil; no se elige silenciosamente una acción.

`remove` exige retirada completa conforme al contrato. Una máscara que deja
cuatro dígitos visibles no obtiene crédito de retirada completa. Generalizar,
desplazar fechas o agrupar edades exige un predicado de utilidad/privacidad
específico; sin un verificador definido, se informa `unverifiable`.

#### 4.7 Descriptor del candidato y contrato de ejecución

El descriptor identifica revisión de código y estado modificado, reglas,
pesos y configuración NLP, selección de países, política, adapters, versiones
de dependencias relevantes y activos OCR con hashes. Debe poder representar
reglas solas, reglas más modelos incorporados y packs de dominio como
configuraciones separadas. No se mezclan sus resultados ni se altera el score
para un caso particular.

El adaptador recibe el caso y la configuración, nunca las etiquetas de
`blind_test` que no necesita para ejecutar. Devuelve predicciones, referencias
a salidas, estado original de DeidFlow, incidencias sanitizadas, tiempos y
evidencia de capacidades ejecutadas. En transformación aislada se suministran
las menciones de referencia por diseño, sin llamar después a ese resultado
«detección real».

El ejecutor crea un espacio local exclusivo por ejecución, no sobrescribe
resultados y procesa casos en orden determinista. Separa semilla del generador,
perturbaciones y estadística; no utiliza aleatoriedad del proceso global ni
fecha actual como valores implícitos. Las claves de sesiones son locales y no
se guardan en el informe; si afectan a bytes de salida, se declaran como
parámetro confidencial reproducible suministrado por el custodio, sin publicarlo.

#### 4.8 Registro de ejecución por caso

| Campo | Tipo / restricción |
| --- | --- |
| `run_id`, `case_id`, `candidate_id`, `profile_id`, `track` | Identificadores y pista explícitos; nunca deducirlos del nombre de archivo |
| `input_fingerprints` | Hashes de entrada, configuración, perfil y versión del evaluador |
| `attempt_status` | `completed`, `candidate_error`, `timeout` o `capability_missing` |
| `release_status` | Estado original de DeidFlow o `null` si la pista no lo produce |
| `predictions` | Lista de unidad, categoría, inicio, fin, detector/procedencia, score y confianza opcional |
| `outputs` | Referencias locales, tipo de artefacto, hash bruto y hash canónico si corresponde |
| `verification` | Zonas/canales requeridos, inspeccionados, no verificables y evidencia de los inspectores |
| `case_assertions` | Chequeos de expectativas de referencia con `PASS`, `FAIL` o `UNVERIFIABLE`; no equivalen a aprobación profesional |
| `diagnostics` | Códigos permitidos y conteos; sin mensajes arbitrarios del candidato |
| `measurements` | Latencia, memoria y condiciones de medición con unidades explícitas; no finitos prohibidos |

Los offsets predichos deben referirse a la unidad original, ser enteros no
booleanos y quedar dentro de rango. Score/confianza son finitos en [0,1];
confianza ausente permanece `null`. Una respuesta malformada del candidato es
`candidate_error`, no un fallo del dataset ni una predicción vacía favorable.
Los mapas que el candidato devuelva son evidencia no confiable hasta su
comprobación; no tienen autoridad para declarar exhaustividad.

#### 4.9 Celda de métrica y resumen

Cada celda de métrica contiene `metric_id`, versión de definición, candidato,
perfil, pista, partición/panel, entidad, formato y estrato; `value`, `numerator`,
`denominator`, `undefined_reason`; soporte de documentos, grupos y menciones;
casos requeridos, ejecutados, fallidos y no verificados; e intervalo con método,
nivel y semilla cuando aplica. Los conteos son enteros no negativos; cualquier
agregado ponderado se identifica aparte, sin reemplazar los conteos crudos.

El resumen enlaza estas celdas, los tres ejes de veredicto y las incidencias
que explican cada incumplimiento. Sus campos deben tener un esquema versionado
validable por máquina. Un lector puede reconstruir los cocientes desde los
conteos sin acceder a documentos originales. No se usa el nombre de una
métrica como descripción suficiente de su denominador.

### 5. Diseño de casos y referencia independiente

El plan de cobertura exige, por cada categoría aplicable, casos positivos,
negativos completos, distractores parecidos, entradas inválidas plausibles,
formatos alterados y combinaciones con contexto no sensible. No se exige el
producto cartesiano de todas las dimensiones: el manifiesto declara las celdas
obligatorias y justifica las no aplicables.

| Familia | Cobertura exigida |
| --- | --- |
| RFC | Persona física/moral, genéricos publicados, checksum, fechas, separadores y contexto fiscal |
| CURP | Estructura, fechas/entidades, checksum, truncado y confusiones OCR |
| CLABE y tarjetas | Longitudes, checksum, agrupaciones y distractores numéricos no personales |
| Teléfonos y correos | Convenciones mexicanas, códigos, extensiones, separadores y límites con prosa |
| Personas/direcciones | Acentos, compuestos, abreviaturas, colonias/calles/números, campos y narrativa |
| Clínica | Negación, dosis/unidades, antecedentes y relaciones con el sujeto; perfiles de conservación/remoción |
| Ambigüedad/solapamiento | Menciones anidadas/cruzadas, homónimos, palabras comunes, nombres de lugares y roles incompatibles |
| Formato/volumen | Unicode, saltos, columnas mezcladas, texto desordenado, cortes de ventanas, documentos largos y densos |
| Artefactos | Contenido visible, metadatos, atributos, partes ocultas, adjuntos y duplicaciones recuperables |

Los identificadores sintéticos se comprobarán mediante especificaciones y
vectores de referencia independientes del candidato. El generador y la
referencia no usarán únicamente el mismo validador de DeidFlow para acreditar
su corrección. Validez estructural nunca afirma titularidad, expedición o que
el valor no pueda coincidir accidentalmente con un registro existente.

La anotación de entradas naturales públicas admitidas requiere dos revisiones
independientes y adjudicación de desacuerdos antes de congelar el test. Las
anotaciones sintéticas deterministas deben auditarse con vectores independientes
y revisión de casos límite. Se registra qué comprobaciones son humanas y cuáles
son mecánicas; no se fabrican revisores o acuerdos.

Casos ambiguos no resueltos permanecen en un panel de desafío con soporte y
tasas de revisión propios; no entran al denominador exacto principal como si
fueran negativos. Tampoco cuentan como éxito de privacidad: un caso requerido
sin referencia suficiente impide calificar esa celda del alcance.

Homónimos se puntúan por mención. La consistencia entre documentos solo se
puntúa donde la entrada proporciona evidencia observable suficiente de misma
o distinta identidad. La mera igualdad del nombre no obliga a fusionar; la
verdad secreta de un generador no debe exigir al candidato resolver lo
indecidible. La vinculación ambigua se informa separadamente.

### 6. Extracción, OCR y formatos

Separar las siguientes condiciones:

1. Texto limpio anotado: mide detección sin errores del lector.
2. Texto con ruido OCR simulado: mide robustez ante una perturbación conocida,
   sin describirla como medición de un motor OCR real.
3. Imagen sintética con referencia visual y OCR local real: mide extracción y
   detección sobre texto observado, además de resultado extremo a extremo.
4. Artefacto transformado: mide el contenido que continúa siendo recuperable.

Las referencias visuales deben conservar las menciones originales aunque el
OCR las omita. Un identificador que desaparece de la extracción, pero permanece
visible en el PDF de salida, es una fuga del pipeline, no un éxito del detector.

Los adapters de formato se entregarán incrementalmente para texto, datos
estructurados, Office, PDF, HTML y correo. Cada ejecución lista cuáles soporta
y cuáles exige su perfil. La ausencia de Tesseract, datos de idioma o pesos
locales produce `NOT_EVALUATED` con razón y soporte pendiente; si la capacidad
era obligatoria, la calificación queda incompleta.

Los inspectores de referencia no confiarán únicamente en los mismos campos
que el lector del candidato decide extraer. Para Office deben inventariar
partes y slots retenidos, incluidos atributos/metadatos. Para correo, cuerpos,
cabeceras y adjuntos admitidos. Para PDF, contenido recuperable y regiones
visuales, con geometría declarada y comprobación de la reconstrucción real.
OCR independiente o búsqueda literal son señales adicionales, no prueba única
de ausencia visual. Si no se puede comprobar una zona obligatoria, se mantiene
`unverifiable`; no se emite un cero de fuga certificado.

### 7. Métricas de detección y validación

#### Matching y conteos

La clave exacta es caso, unidad, categoría, inicio y fin. Deduplicar predicciones
idénticas, conservando su procedencia. Emparejar con máxima cardinalidad uno a
uno; resolver empates por orden canónico. Una predicción no puede acertar dos
menciones distintas. Distintos spans solapados permanecen en la evaluación.

Por entidad y estrato: `TP` es el número de parejas exactas; `FP`, predicciones
sin pareja; `FN`, referencias sin pareja. Error de tipo implica FN de la
categoría correcta y, si la categoría predicha pertenece al alcance puntuable,
FP de esta. Error de límite implica FP y FN bajo matching exacto.

| Métrica | Definición |
| --- | --- |
| Precision | TP / (TP + FP) |
| Recall | TP / (TP + FN) |
| F1 | 2TP / (2TP + FP + FN) |
| Falsos positivos y negativos | Conteos absolutos por entidad, estrato y configuración |
| Micro | Suma de TP/FP/FN del alcance explícito antes de calcular cocientes |
| Macro | Media de métricas definidas por categoría; declarar categorías excluidas e incompletas |
| Cobertura diagnóstica | Menciones/caracteres cubiertos completamente y cobertura parcial, informadas aparte |
| Negativos | Documentos negativos con al menos un FP / documentos negativos; FP por volumen con unidad declarada |

Denominador cero produce `null` y `undefined_reason`, no 1.0 ni un cero que
parezca medido. Las categorías oficiales sin soporte no desaparecen del
informe. No hay un universo natural de TN por span en NER abierto; no publicar
una tasa clásica de FP sin definir ese universo.

La pista de validación compara por separado patrón, estructura y checksum con
la referencia independiente. `not_applicable` no es un fallo de checksum. No
convertir el score de una regla en probabilidad calibrada ni mezclar esta pista
con el recall de protección de valores inválidos.

La vista de intersección es diagnóstica: exige categoría y emparejamiento uno
a uno, pero no concede eliminación completa por tocar un único carácter.
Los resultados por formato, validez, ruido, posición/corte, longitud, fuente y
familia documental se mantienen separados. No elegir después de observar el
test los estratos que hacen lucir mejor al candidato.

### 8. Métricas de transformación y liberación

La unidad de referencia es la mención o región que el perfil exige proteger o
preservar. La política determina el denominador, no las detecciones obtenidas.

| Métrica | Numerador / denominador |
| --- | --- |
| Retirada completa | Menciones obligatorias demostrablemente retiradas / menciones obligatorias |
| Fuga por mención | Menciones obligatorias con residuo atribuible / menciones obligatorias |
| Fuga por documento emitido | Documentos emitidos con residuo / documentos emitidos inspeccionados completamente |
| Fuga entre aprobados | Documentos `APPROVED` con residuo / documentos `APPROVED` inspeccionados completamente |
| Verificación completa | Documentos con todos los canales obligatorios inspeccionados / documentos del alcance |
| Retención no sensible | Caracteres no sensibles preservados / caracteres que debían preservarse, con unión de spans |
| Contexto requerido | Spans de negación/dosis/cantidad/relación preservados / spans requeridos |
| Sobretransformación | Caracteres que debían preservarse y fueron modificados / caracteres requeridos |
| Éxito conjunto | Documentos con salida verificable, protección satisfecha y contexto requerido conservado / todos los documentos requeridos |
| Estados/carga | Conteos y proporciones de aprobación, revisión, bloqueo, no soportado, error y ausencia de salida |
| Identidad | Consistencia y colisiones por pares con evidencia suficiente; indeterminados aparte |

Un documento sin salida no obtiene éxito conjunto; tampoco se afirma fuga
cero a partir de su inexistencia. Un documento con salida y verificación
incompleta no entra silenciosamente como documento seguro: reportar su estado
y producir límites inferior/superior del riesgo entre emitidos: si N es el
total emitido, L los documentos con fuga confirmada y U los no verificados
sin fuga ya confirmada, los límites empíricos son L/N y (L+U)/N. Se distinguen
de los intervalos estadísticos. Aplicar el mismo cálculo al subconjunto de
aprobados. Si no hay aprobados, su riesgo es indefinido y se informa
el denominador cero junto con la carga de revisión.

Inspeccionar todas las salidas observables del candidato, incluso candidatas
asociadas a revisión o bloqueo, manteniendo los estados separados. Mapas de
transformación solo aportan evidencia tras comprobar tramos de entrada/salida,
operador y contenido realmente emitido. No conceder retirada a una sustitución
que copia el original bajo otro nombre.

Las búsquedas de supervivencia literal y variantes registradas se combinan con
localización y atribución: un homónimo permitido o una cifra en otro contexto
no es automáticamente la misma mención filtrada. Si la atribución es
indecidible, declarar incertidumbre en lugar de una conclusión favorable.

### 9. Incertidumbre y soporte

Publicar conteos antes de porcentajes. Las variantes de un mismo linaje no son
observaciones independientes. Los intervalos agregados usarán remuestreo por
grupos de independencia y semilla registrada; propuesta técnica inicial: 2000
réplicas y nivel 95%, definidos en el perfil estadístico versionado.

Los paneles principal y de perturbaciones se presentan por separado; no
multiplicar el peso de un documento porque tenga más versiones OCR. Cualquier
agregado ponderado requiere pesos predefinidos y debe conservar también los
conteos no ponderados.

Con cero fugas, un bootstrap degenerado en cero no autoriza riesgo cero. Se
publicará un límite superior conservador bajo un modelo de independencia
explícito; para n unidades Bernoulli independientes sin fugas, el límite
unilateral 95% es `1 - 0.05^(1/n)`. Si esa hipótesis no es defendible, el límite
poblacional será no estimable y la conclusión se limitará al corpus observado.
No interpretar documentos sintéticos correlacionados como n casos reales
independientes de despliegue.

### 10. Independencia, custodia y contaminación

La asignación de particiones ocurre antes de generar derivados. Cada grupo es
la clausura de relaciones conocidas entre documento original, el mismo
documento fuente, familia de plantilla, identidad sintética vinculada y
variantes OCR/de formato. Ningún componente de esa relación cruza particiones.
Compartir el proveedor de un corpus o el idioma no convierte por sí solo todos
sus documentos en un único grupo; se audita el origen documental y el linaje.

Comprobar IDs, grupos, hashes originales, igualdad de texto normalizado para
auditoría y coincidencias cercanas entre particiones. La normalización de
auditoría no cambia el texto que se puntúa. El perfil de auditoría debe fijar
el algoritmo, parámetros y versión de detección de similitud antes de abrir
el test; coincidencias sospechosas requieren resolución documentada. Si no
hay perfil o quedan conflictos, no se acredita independencia.

Nombres comunes, terminología clínica y etiquetas de formulario no constituyen
por sí solos identidad compartida. Se audita su coincidencia sin fusionar
automáticamente todo el corpus. Los identificadores sintéticos vinculados y
sus derivados sí conservan el mismo grupo.

El banco ciego se congela con su referencia y el descriptor del candidato
antes de la evaluación final. La custodia usa archivos y permisos locales;
no exige un servicio externo. Se registran accesos y evaluaciones por digest.
En un perfil de custodia estricta, el proceso del candidato recibe únicamente
las entradas y activos necesarios; no acceso al directorio de anotaciones
ciegas. Deben acreditarse las restricciones del entorno en vez de asumir que
separar dos funciones de Python aísla el gold.
Si el evaluador es también quien ajusta reglas, se declara esa limitación;
los hashes y los logs no prueban por sí solos que nadie leyó el test.

Los casos usados para ajustar modelos, reglas, umbrales o parsers pasan a
`known_regression`. Corregir sobre un fallo abierto del test no conserva ese
banco como test ciego intacto para la siguiente afirmación de generalización.
Las nuevas calificaciones requieren un banco independiente renovado.

Los corpus públicos ya usados por los modelos se mantienen como transferencia
o regresión. Exposición desconocida se declara como tal; no se inventa una
garantía de no exposición a los pesos históricos. Publicar la referencia puede
ser útil para reproducibilidad, pero termina su condición de ciego para futuros
ajustes; la versión y sus conclusiones históricas no se reescriben.

### 11. Resultado, reproducibilidad y veredictos

El informe contiene: versiones y hashes; ámbito y procedencia; candidato y
perfil; decisiones de configuración; corpus y partición; casos ejecutados,
omitidos y fallidos; métricas por entidad/estrato/pista; incertidumbre y soporte;
errores por clase; veredictos y limitaciones. También registra entorno, CPU,
memoria observada, plataforma, aceleración y activos utilizados.

Los conteos, decisiones y hashes de artefactos deterministas deben repetirse
con iguales entradas y versiones. Tiempos, RSS y timestamps no tienen que ser
idénticos y quedan separados de las métricas deterministas. Si una biblioteca
serializa metadatos variables, se registran hash bruto y representación
canónica versionada, sin ocultar partes donde pueda residir información sensible.

Hay tres ejes de estado distintos del estado de liberación de DeidFlow:

- **Ejecución:** `COMPLETED`, `INCOMPLETE` o `INVALID_RUN`.
- **Conformidad técnica:** `PASS`, `FAIL` o `INCOMPLETE` contra las capacidades
  obligatorias y pruebas de integridad/verificación.
- **Calidad del candidato:** `PASS`, `FAIL`, `INSUFFICIENT_EVIDENCE` o
  `DESCRIPTIVE_ONLY`. Este último es obligatorio sin perfil de calidad ratificado.

El perfil de calidad, si existe, especifica entidad/estrato/pista, métricas y
dirección de cada umbral, mínimos de soporte, límites de confianza aplicables,
máxima fuga permitida, conservación mínima y presupuesto de revisión. Debe
estar aprobado y congelado antes de abrir el banco final. Esta especificación
no inventa esos números ni permite que un F1 agregado compense una fuga que el
perfil define como inaceptable.

Una ejecución válida puede concluir que el candidato falla. Los errores del
candidato no invalidan la referencia: se reportan y penalizan su completitud;
no se eliminan para mejorar métricas. Las métricas de casos completados llevan
su alcance explícito y no bastan para calificar el total si faltan casos
obligatorios. Los fallos del arnés o del dataset sí producen `INVALID_RUN`.

Semántica de salida del futuro comando: 0 cuando completa la evaluación sin
fallos de los criterios configurados; 2 cuando detecta incumplimiento del
candidato o del perfil; 3 para entrada/configuración inválida o ejecución
incompleta. Son códigos del evaluador, no traducciones de `ReleaseStatus`.
Una corrida descriptiva completada puede salir con 0, pero el informe debe
seguir diciendo `DESCRIPTIVE_ONLY`, sin insinuar calidad profesional aprobada.

### 12. Privacidad y ejecución local

- Prohibido usar expedientes o documentos personales reales para este alcance.
  Una fuente pública se revisa también por contenido personal; si lo contiene,
  no se incorpora como núcleo no personal por el mero hecho de ser pública.
- Ninguna fase de evaluación, carga o inferencia puede contactar Internet, APIs
  externas, telemetría o un servicio de modelos. Los activos deben existir
  localmente y corresponder a los hashes declarados.
- La eventual adquisición autorizada de fuentes se separa de la ejecución;
  esta especificación no realiza ni autoriza descargas concretas.
- Registrar intentos de red y hacer fallar la ejecución correspondiente incluso
  si una biblioteca captura internamente el error. Un bloqueo de sockets de
  Python no se anuncia como aislamiento de procesos nativos: la calificación
  offline estricta requiere denegación de red a nivel de proceso/entorno y una
  prueba de esa capacidad. Si no existe, declararla no acreditada.
- Logs públicos y resultados agregados no contienen texto de entrada/salida,
  spans con valores, nombres de archivos originales, claves, tokens, recibos
  secretos ni variables de entorno. Los identificadores de casos son opacos.
- Los detalles de diagnóstico autorizados permanecen en un espacio local de
  acceso restringido, separados del resumen; tampoco se publican por defecto.
- Sesiones y claves de reversibilidad se gestionan por los mecanismos cifrados
  existentes; no se persisten mapas de identidad en claro para evaluar.
- Los límites por ejecución incluyen bytes de entrada/expansión, miembros de
  archivos, profundidad, píxeles, tiempo y memoria. El perfil distingue límite
  de admisión de límite duro de proceso. No se interpreta un timeout o una
  capacidad de aislamiento ausente como éxito o ausencia de fugas.
- El arnés no altera el sandbox del usuario, no desactiva TLS, no instala
  dependencias o modelos automáticamente y no sustituye credenciales.
- El benchmark será una capacidad de desarrollo opcional. El wheel base de
  DeidFlow conserva su funcionamiento sin dependencias obligatorias nuevas.

## Testing Decisions

### Interfaz principal y alcance de pruebas

La aceptación se prueba desde la seam paquete/candidato/perfil → informe,
preferentemente usando las interfaces públicas existentes. Los tests deben
comprobar comportamiento y evidencia, no nombres de funciones internas, orden
privado de llamadas o una estructura accidental del código.

Las pruebas del arnés usan fixtures pequeños con respuestas conocidas, candidatos
deterministas y artefactos controlados. La validación del candidato real se
informa aparte: que el arnés detecte un fallo esperado es una prueba aprobada
del arnés, no una aprobación de DeidFlow.

### Familias de pruebas requeridas

| Familia | Casos y resultado observable |
| --- | --- |
| Contratos | Duplicados, NaN/Infinity, bool como offset, Unicode inválido, límites, referencias rotas, traversal, recursos alterados y versiones incompatibles se rechazan |
| Matching | TP/FP/FN exactos, tipos erróneos, límites parciales, predicciones duplicadas y solapamientos legítimos sin doble crédito |
| Denominadores | Sin gold, sin predicciones, sin aprobados y sin soporte generan valores/razones correctos, no perfección ficticia |
| Independencia | Copia exacta, texto normalizado equivalente, familia/identidad/linaje compartido y variante OCR cruzada bloquean la acreditación del test |
| Validez | Vectores independientes correctos, checksum incorrecto, fecha imposible, truncado y etiqueta explícita dañada |
| Operadores | Copia del original, copia en otra parte, máscara parcial, marcador falso y generalización no verificada no reciben crédito de eliminación completa |
| Conservación | Negaciones, dosis, importes, orden y estructura protegida se mantienen cuando el perfil lo exige |
| Formatos | Canario en atributo DOCX, partes ocultas, celda/JSON, MIME/adjuntos y región PDF donde el extractor omite el dato |
| OCR | Motor ausente, idioma ausente, salida vacía no justificada, ruido simulado y OCR real diferenciados |
| Identidad | Mismo nombre con evidencia de distintas personas; continuidad explícita; alias y homónimo indeterminados sin inferencia obligatoria |
| Localidad | Carga e inferencia sin red; intento de red de adapter y de subproceso identificado; activos faltantes declarados |
| Repetición | Dos ejecuciones del mismo paquete/configuración producen los mismos conteos y decisiones; cambian solo campos operativos permitidos |
| Aislamiento de fallos | Timeout, error de adapter y salida incompleta mantienen el caso en el informe y degradan el veredicto correspondiente |
| Privacidad | Canarios colocados en texto, nombres de archivos y errores no aparecen en logs/resumen ni mensajes de fallo |

Como referencia de regresión se incorporan, con sus resultados conocidos y sin
introducirlos en el nuevo banco ciego: metadatos DOCX que conservan un correo,
apellido retenido en el corte del tagger, IBAN seguido por texto en mayúsculas
y eliminación indebida de «niega diabetes». La implementación del evaluador
no debe corregir reglas de producción ni ajustar los datos para que esos casos
parezcan resueltos.

Los precedentes reutilizables son las pruebas existentes de matching uno a uno,
spans y offsets, contexto real emitido, recibos de revisión, contaminación de
particiones, seguridad de contenedores y wheel sin extras. Las pruebas OCR
reales deben aprovisionarse por separado; una omisión no es un test aprobado.

### Criterios de aceptación verificables

| ID | Criterio |
| --- | --- |
| AC-01 | El paquete completo se valida antes de evaluar; modificar un byte de un recurso o cruzar un grupo obligatorio produce `INVALID_RUN` o independencia no acreditada, nunca un informe oficial favorable |
| AC-02 | Un fixture con TP=1, FP=1, FN=1 produce precision=recall=F1=0.5 para esa entidad; una predicción no puede acertar dos menciones |
| AC-03 | Las categorías RFC, CURP y CLABE tienen filas independientes, soporte y TP/FP/FN; no se rescatan mediante alias genéricos guiados por el gold |
| AC-04 | Un identificador con checksum incorrecto no recibe automáticamente etiqueta negativa: se respeta la sensibilidad de referencia y se informa la validez separada |
| AC-05 | Los spans superpuestos válidos se cargan y puntúan; el cargador de entrenamiento no impone su restricción de no solapamiento al dataset de evaluación |
| AC-06 | Una sustitución que conserva el identificador o lo duplica en otro canal no obtiene retirada completa solo por disponer de SourceMap |
| AC-07 | El canario de metadatos DOCX se identifica en el artefacto retenido; si el candidato devuelve `APPROVED`, se informa fuga aprobada y falla la condición de privacidad correspondiente |
| AC-08 | Si el perfil contextual exige «niega diabetes» y se pierde, la conservación y el éxito conjunto fallan aunque el nombre haya sido retirado |
| AC-09 | Un candidato que bloquea todo tiene cero documentos de éxito conjunto y denominador de aprobados cero; no obtiene una tasa certificada de fugas igual a cero |
| AC-10 | Toda capacidad obligatoria no ejecutada o zona sin verificar impide la conformidad completa; la salida lista razones y soporte pendiente |
| AC-11 | El arnés genera y verifica informes sin red y sin activos remotos; ningún canario o secreto aparece en logs públicos |
| AC-12 | Con iguales paquetes, versiones y configuración se repiten conteos, asignaciones y veredictos; los resultados anteriores no se sobrescriben |
| AC-13 | Sin perfil de calidad ratificado el informe dice `DESCRIPTIVE_ONLY`; un hash o el código 0 del comando no se presentan como aprobación profesional |
| AC-14 | El informe distingue regresión conocida, transferencia y test independiente; no agrupa evidencia histórica expuesta con el nuevo banco ciego |
| AC-15 | El wheel base y las interfaces de producción conservan sus contratos; cualquier dependencia opcional propuesta requiere necesidad, licencia y coste documentados |

Estos criterios aceptan el funcionamiento del sistema de evaluación. No fijan
una promesa arbitraria de recall/precision para los modelos actuales. Su
calificación futura requiere el perfil de calidad y soporte acordados.

## Out of Scope

- Implementar el arnés, generar/adquirir datasets, entrenar o ajustar modelos en
  esta tarea.
- Corregir los defectos de detección/transformación o rediseñar la biblioteca
  de producción como parte de la futura implementación del benchmark.
- Documentos personales reales, consultas de titularidad, scraping de fuentes
  con derechos inciertos o envío de documentos a servicios externos.
- LLMs, inferencia remota, anotación externa automática, descargas de modelos,
  instalación automática de dependencias o publicación automática de resultados.
- Declarar anonimato, cumplimiento normativo o representatividad poblacional
  mexicana a partir de fixtures sintéticos o corpus extranjeros.
- Promoción automática de candidatos o autorización de liberación profesional
  basada únicamente en F1, cobertura o ausencia de fugas observadas.
- Publicar issues, commits, PRs o el entorno como consecuencia de redactar esta
  especificación.

## Further Notes

La entrega propuesta es incremental: primero contratos y fixtures del arnés;
después detección/transformación textual; después inspectores de artefactos y
OCR; finalmente custodia, corpus independiente y perfil de calificación. Cada
incremento declara su alcance real y no usa `PASS` para capacidades pendientes.

Antes de calificar una versión de DeidFlow quedan por ratificar D1–D3, el
alcance obligatorio por formato, el protocolo estadístico y de similitud,
custodia/publicación del banco, permisos de fuentes concretas, soporte y
umbrales. La ausencia de esas decisiones no impide implementar el arnés con
configuración explícita; sí impide emitir una aprobación operativa que las
suponga resueltas.

La especificación se publica como documentación de revisión. El borrador de diseño
anterior permanece como historial de hechos y preguntas; no se ha convertido
silenciosamente en un registro de acuerdos contestados.

Referencia de diseño previa: [Evaluación oficial MX](EVALUACION_OFICIAL_MX.md).
Vocabulario: [glosario de DeidFlow](../GLOSSARY.md).
