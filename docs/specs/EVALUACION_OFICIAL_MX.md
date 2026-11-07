# Evaluación oficial de DeidFlow para español mexicano

**Estado: borrador de diseño, ronda 1. No implementado.**

Especificación técnica derivada: [DF-EVAL-MX v0.1.0](BENCHMARK_MX_SPEC.md).
Conserva explícitamente qué recomendaciones siguen pendientes de ratificación.

Este documento distingue requisitos ya expresados por Giovanny, hechos del
código inspeccionado y propuestas pendientes de acuerdo. No autoriza adquirir
documentos personales, descargar corpus, ajustar modelos o ejecutar/publicar
un benchmark. No se fijan todavía umbrales ni tamaños de muestra.

## 1. Acuerdos de partida

Requisitos explícitos de la solicitud:

- Medir capacidad de detección y transformación de datos sensibles en español
  mexicano; declarar los límites de cualquier generalización.
- Cubrir RFC, CURP, CLABE, tarjetas, teléfonos, correos, nombres, direcciones e
  información clínica contextual.
- Incluir ejemplos sintéticos válidos e inválidos, documentos públicos con
  derechos de uso comprobables, alteraciones de formato y OCR, texto
  desordenado, solapamientos, homónimos y ambigüedad.
- Evaluar por separado detección y transformación; medir precision, recall,
  F1, falsos positivos y falsos negativos por categoría.
- Medir conservación de información no sensible y fuga residual real.
- Separar entrenamiento, ajuste y evaluación independiente, evitando
  contaminación por documentos o sus derivados.
- No utilizar documentos personales reales ni enviar documentos personales a
  servicios externos. No implementar todavía el benchmark.
- Documentar decisiones bajo `docs/`, preservando código y dependencias.

No se interpretan las propuestas siguientes como acuerdos del usuario.

## 2. Hechos de la implementación que condicionan el diseño

Inspección de la revisión `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`:

| Módulo o evidencia | Capacidad aprovechable | Límite que debe conservarse explícito |
| --- | --- | --- |
| `src/deidflow/validators/__init__.py` | Comprobaciones locales de RFC, CURP, CLABE y tarjetas; distingue patrón, estructura y checksum | Validez local no confirma existencia o titularidad; tampoco decide por sí sola sensibilidad |
| `src/deidflow/benchmarks/metrics.py` | Matching tipado exacto o por intersección, uno a uno; TP/FP/FN y métricas agregadas | Intersecar un carácter no equivale a proteger la mención completa; faltan salidas completas por entidad para el contrato propuesto |
| `src/deidflow/benchmarks/public_quality.py:179` | Estratos, métricas exactas, cobertura de caracteres e intervalos | Su cobertura es de detección y declara ignorar el tipo predicho; no verifica la salida transformada |
| `src/deidflow/benchmarks/release_gate.py:55` | Conteos por estado y fugas en documentos aprobados | Acredita cobertura desde los mapas de transformación; no basta como oráculo de ausencia en los bytes finales |
| `src/deidflow/benchmarks/context_quality.py:221` | Comprueba sustituciones emitidas, tramos conservados y supervivencia literal; mide contexto e identidad | Es principalmente textual y solo acredita operadores que sabe interpretar; ampliar el alcance exige un diseño de referencia por formato |
| `src/deidflow/benchmarks/synthetic_es.py:533` y `public_quality.py:58` | Taxonomías y equivalencias de corpus existentes | Algunos alias colapsan RFC/CURP/CLABE en categorías genéricas; la evaluación mexicana debe conservar sus métricas individuales y declarar cualquier equivalencia secundaria |
| `src/deidflow/training/adaptation.py:252` | Controles de partición y validación de anotaciones de entrenamiento | Ese cargador rechaza solapamientos; no debe convertirse sin cambios en el contrato de referencia de un benchmark que necesita entidades superpuestas |
| `docs/GENERAL_MODEL_2_AUDIT.md:66` | Procedencia y exposición de las mediciones históricas | Confirma reutilización del test para diagnóstico de reglas: esos casos no deben rebautizarse como ciegos |
| `docs/PUBLIC_CORPORA.md` | Inventario de MEDDOCAN, Gretel y otros corpus, con alcance declarado | España o estilo europeo/sintético no representan por sí solos México; varios corpus ya participaron en los modelos |
| `docs/public-document-sources.json` | Registro de documentos mexicanos públicos para pruebas operativas | No tienen gold completo; permisos de redistribución/entrenamiento no establecidos o restringidos. Una URL pública no es autorización suficiente |

La revisión arquitectónica precedente produjo además regresiones conocidas:
correo retenido en metadatos DOCX, apellido expuesto en un corte del tagger,
IBAN omitido por prosa en mayúsculas y pérdida de «niega diabetes». Deben formar
parte de un conjunto de regresión conocido, nunca del nuevo test ciego.

## 3. Estructura propuesta del benchmark

### A. Validación local de identificadores

Evaluar formato, estructura y checksum como atributos propios. Generar casos
válidos y alteraciones controladas, con referencia independiente de las
funciones que se evalúan. No usar el mismo validador de DeidFlow para producir
los valores, etiquetarlos y demostrar que su propia salida es correcta.

Separar estos atributos de la decisión de sensibilidad. El tratamiento de
identificadores inválidos con apariencia personal se decide en Q2.

### B. Detección sobre texto de referencia

Entrada textual anotada, sin introducir en esta pista errores de extracción
del contenedor. Informar métricas por categoría y estratos; no ocultar los RFC
o CURP detrás de un F1 global dominado por correos.

Conservar RFC, CURP y CLABE como categorías distinguibles en el informe oficial,
conforme a los resultados por entidad solicitados. Cualquier vista comparable
con categorías genéricas de corpus externos debe publicarse como vista aparte,
con un mapeo explícito que no convierta el error de una categoría en acierto de otra.

Propuesta pendiente para discutir después de fijar las políticas:

- Métrica principal: categoría y límites exactos, matching máximo uno a uno.
- Métricas diagnósticas separadas: cobertura completa de la mención y de
  caracteres; solapamiento parcial sin conceder eliminación completa.
- Preservar entidades anidadas o parcialmente cruzadas en las anotaciones.
- Anotar ambigüedad y evidencia, sin inventar identidad real a partir del nombre.

### C. Transformación aislada y extremo a extremo

Dos mediciones distintas para atribuir errores:

1. Transformación con menciones de referencia: medir decisiones de política,
   operadores, offsets y conservación sin cargarles errores del detector.
2. Pipeline completo con predicciones reales: medir lo que efectivamente sale
   del sistema y la decisión de liberación resultante.

El evaluador debe inspeccionar contenido final con una referencia propia:
salida Unicode, valores estructurados, contenido recuperable de Office y,
cuando corresponda, píxeles/texto y metadatos del PDF. Un mapa de offsets,
un hash o una segunda ejecución del mismo detector no bastan por sí solos.

Medir por separado:

- Menciones y caracteres sensibles residuales, por categoría y documento.
- Documentos emitidos con fuga, distinguiendo todos los estados.
- Fugas entre documentos `APPROVED`, junto con cuántos se aprobaron.
- Conservación de spans no sensibles y de contexto requerido: negaciones,
  dosis, importes o relaciones, según la política pendiente de Q3.
- Sobretransformación, sustituciones correctas y conservación de estructura.
- Salidas no emitidas, errores, no soportadas y carga de revisión; bloquear
  todo no debe aparecer como éxito perfecto de transformación.

Una coincidencia literal residual puede ser una alarma útil, pero requiere
atribución a la mención: un homónimo legítimo o un dato permitido no se convierte
automáticamente en fuga. También se necesitan búsquedas de variantes y una
inspección del artefacto, no solo búsquedas literales en texto extraído.

## 4. Matriz de casos propuesta

| Dimensión | Casos que debe contemplar el diseño |
| --- | --- |
| Identificadores MX | RFC de persona física/moral y genéricos; CURP; CLABE; tarjetas; teléfonos de México y correos |
| Validez | Correcto, checksum alterado, estructura imposible, longitud incorrecta, truncado y error OCR; distractores no personales similares |
| Contexto | Con/sin etiqueta, formularios frente a narrativa, nombres compuestos, apellidos y domicilios mexicanos; clínica con negaciones y dosis |
| Ambigüedad | Homónimos, nombres que también son lugares o palabras comunes, alias no demostrados, referencias incompletas |
| Solapamiento | Categorías coincidentes, spans anidados, parcialmente cruzados y límites que incluyen contexto que debe conservarse |
| Perturbaciones | Mayúsculas, diacríticos, Unicode, espacios/separadores, saltos de línea, columnas mezcladas, cortes de ventana y texto desordenado |
| OCR | Ruido textual simulado separado de OCR real sobre imágenes sintéticas; errores de caracteres, resolución, rotación y segmentación registrados |
| Formatos | Texto y sus variantes; datos estructurados; DOCX/XLSX; PDF nativo/escaneado; HTML/correo, informados por separado según alcance que acordemos |
| Canales recuperables | Texto visible, atributos/metadatos, partes ocultas, adjuntos y contenido serializado; casos no inspeccionables explícitos |
| Utilidad | Frases negativas, dosis y unidades, cantidades, estructura y relaciones que la política exige mantener; documentos negativos completos |

Cada perturbación debe conservar el vínculo con su documento de origen. No
repartir variantes OCR o de formato entre entrenamiento y test. Los conteos y
estratos no se fijan antes de acordar el uso y el criterio de verdad.

## 5. Métricas solicitadas

Para cada categoría `e`, bajo la regla de matching que finalmente acordemos:

- `TP_e`: menciones predichas emparejadas correctamente con la referencia.
- `FP_e`: predicciones de esa categoría sin pareja correcta.
- `FN_e`: menciones de referencia de esa categoría sin predicción correcta.
- `Precision_e = TP_e / (TP_e + FP_e)`.
- `Recall_e = TP_e / (TP_e + FN_e)`.
- `F1_e = 2*TP_e / (2*TP_e + FP_e + FN_e)`.

Propuesta: publicar también soporte, conteos, estrato y regla de matching;
informar `N/A` cuando el denominador no permite estimar una magnitud, en vez de
presentar cobertura inexistente como perfección. En NER abierto no hay un
universo natural de verdaderos negativos por span; no llamar «tasa de falsos
positivos» a un cociente cuyo denominador no esté definido. Podemos añadir FP
por documento negativo o por volumen de texto, con denominadores explícitos.

La transformación necesita denominadores propios: menciones que cada política
exige retirar y spans que exige preservar. La misma categoría clínica puede
ser detectada correctamente y conservarse correctamente bajo un perfil; no
confundir esa conservación deliberada con un falso negativo de detección.

Propuesta posterior: intervalos que respeten linajes/grupos documentales, no
tratar cada variante OCR como observación independiente. Cero fugas observadas
debe acompañarse de soporte e incertidumbre; no equivale a ausencia universal.

## 6. Separación y procedencia

Restricción acordada: entrenamiento, ajuste y evaluación deben ser independientes.
Diseño propuesto para lograrlo, pendiente de cerrar:

- Banco de desarrollo/ajuste visible, con evaluación interna de candidatos.
- Banco de regresiones conocidas que incluya los defectos ya inspeccionados.
- Nuevo banco de evaluación independiente, congelado antes de comparar la
  configuración final, con reglas de acceso y renovación por acordar.
- Partición por documento de origen, familia de plantilla, fuente y linaje;
  no solo por semilla, número de fila o hash exacto.
- Auditar coincidencias exactas y cercanas, entidades/identidades sintéticas
  compartidas, plantillas y derivados. Una coincidencia de nombre común exige
  análisis; no prueba por sí sola contaminación ni identidad compartida.
- Comparar con la procedencia conocida de los modelos actuales. Cuando no se
  pueda descartar exposición a un corpus, declararlo y no afirmar que es ciego.
- Fijar código, reglas, modelo, política, versiones, semillas, corpus, referencia,
  perturbaciones y activos OCR mediante manifiestos con hashes.

Un benchmark público reproducible no puede permanecer ciego para siempre.
Debemos acordar custodia, publicación de referencias y renovación del banco;
no se oculta esa decisión bajo la palabra «test».

## 7. Fuentes públicas: criterios, no autorización automática

Propuesta: corpus controlado mexicano de datos ficticios y textos/formatos
públicos sin datos personales reales, más pistas externas de transferencia
claramente separadas. MEDDOCAN o Gretel podrían aportar referencia comparativa
según su licencia y exposición previa, sin presentarse como test mexicano
independiente ni como documentos reales mexicanos.

Antes de incorporar cualquier fuente, registrar URL y versión, licencia y
términos aplicables, permisos de evaluación/anotación/derivación/redistribución,
atribución, idioma/país, estado de datos personales y exposición al entrenamiento.
No confundir permiso de evaluación local con permiso de redistribuir o entrenar.
Excluir fuentes con permisos inciertos hasta resolverlos. No se ha verificado
la vigencia jurídica de términos externos durante esta sesión.

No usar expedientes personales ni consultar registros para confirmar la
titularidad de identificadores sintéticos. Las descargas, anotaciones y corpus
deben diseñarse antes de ejecutar cualquier adquisición.

## 8. Árbol de decisiones y ronda 1

| Pregunta | Propuesta para discutir | Estado |
| --- | --- | --- |
| Q1: uso operativo de v1 | Apoyo supervisado, con liberación automática informada separadamente sin habilitarla | Pendiente de Giovanny |
| Q2: sensibilidad de valores inválidos | Separar sensibilidad de validez; proteger identificadores personales plausibles aunque fallen checksum | Pendiente de Giovanny |
| Q3: tratamiento clínico | Dos perfiles separados: contexto preservado y estricto; detección común, expectativas de transformación diferentes | Pendiente de Giovanny |

Las respuestas abren la siguiente ronda: alcance de formatos y OCR; protocolo
de anotación/adjudicación y ambigüedad; matching y unidades; custodia/publicación
del test; representatividad, soporte, umbrales de aceptación y coste de revisión.
No se han decidido por silencio ni se implementarán antes del acuerdo.

No se necesita un ADR para repetir restricciones explícitas. Se registrarán
ADRs cuando se elija una alternativa con coste real de reversión, por ejemplo
el criterio de verdad para identificadores inválidos o la custodia del test.
