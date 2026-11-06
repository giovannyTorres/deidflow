# Transformación textual aislada

`deidflow.benchmarks.transformation_runner.run_transformation_benchmark`
recibe `package`, `manifest_sha256`, `candidate`, `profile`, `output` igual que
las pistas anteriores. Perfil admitido: `transformation-descriptive-v1`.
Candidato integrado: `transform.text`, que llama realmente a `transform_text`
con spans de referencia, sin invocar al detector. No cambia producción.

Un candidato local de confianza puede usar `TransformationCandidate(id, sha,
transform)`; su callback recibe texto, tupla de Findings de referencia y Policy,
y devuelve `TransformationOutput(text, tuple[SourceMap, ...], release_status)`.
La identidad del callback es declarada por el llamador, no autenticada.
No cargar plugins por nombre, ejecutar comandos ni descargar activos.

Las expectativas existentes son el contrato. `remove` exige protección completa;
`preserve` exige los caracteres de contexto; `generalize` queda `UNVERIFIABLE`
sin un verificador del operador; `review_required` conserva la necesidad humana.
Estos perfiles son propuestas explícitas no ratificadas. No anticipan BMX-09.
Estados de liberación permitidos también se contrastan con las expectativas.

Los solapamientos se conservan. La precedencia declarada resuelve solamente las
intersecciones entre acciones distintas; las regiones no solapadas mantienen su
obligación. Sin precedencia las contradicciones se rechazan al cargar el paquete.
Se publica el número de caracteres afectados por precedencia.

Un mapa válido tiene spans de entrada ordenados/disjuntos, salida ordenada,
límites correctos y huecos/sufijo iguales al texto realmente emitido. El nombre
del operador no certifica el contenido. Se verifican exactamente suppress,
redact y placeholder; los demás requieren verificadores posteriores. Una copia
literal única superviviente es fuga incluso con mapa inválido. Una máscara
parcial o copia bajo otro nombre no acredita retirada. Una coincidencia con
homónimos sin atribución suficiente queda incierta, sin conceder eliminación.
Un marcador que ya existía en otra región de entrada sigue siendo texto fuente;
su mera presencia no invalida una sustitución distinta.

Se cuentan menciones completas, contexto requerido y unión de caracteres de
conservación. Fuera de las expectativas no preservadoras, los caracteres deben
mantenerse. El mapa permite atribuir caracteres conservados incluso dentro de
una transformación de longitud igual. Un mapa inválido deja conservación sin
verificar, no la convierte en sobretransformación demostrada. Éxito conjunto
requiere todas las obligaciones y conservación, salida observable y verificable;
la aprobación de producción se mantiene como estado separado. Errores conservan
el denominador requerido y no publican el texto de la excepción.

Los informes incluyen conteos, retención con denominador explícito y
`DESCRIPTIVE_ONLY`. Solo se ejecuta regresión conocida en texto. Esta pista no
acredita aislamiento de proceso, detección, artefactos de otros formatos,
calidad profesional, identidad estable ni anonimato.
