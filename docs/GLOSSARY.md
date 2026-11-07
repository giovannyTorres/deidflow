# DeidFlow

Lenguaje de la desidentificación y de su evaluación. Las decisiones de diseño
del benchmark se registran aparte; este archivo define términos.

## Lenguaje

**Detección de datos sensibles**:
Identificación de menciones sensibles y de su categoría dentro de un documento.
No acredita que el documento transformado esté libre de información residual.
_Evitar_: anonimización, saneado completo.

**Transformación de datos sensibles**:
Cambio de las menciones que una política exige proteger, conservando la
información que esa política exige mantener.
_Evitar_: detección, reescritura libre.

**Identificador sintético válido**:
Valor ficticio que cumple las reglas de formato, estructura y comprobación
aplicables. Su validez no prueba expedición oficial, existencia o titularidad.
_Evitar_: identidad verificada, cuenta real confirmada.

**Anotación de referencia**:
Descripción revisada de las menciones presentes y del comportamiento esperado
conforme al alcance de evaluación acordado.
_Evitar_: predicción del detector, verdad inferida automáticamente.

**Fuga residual**:
Permanencia de información que la política de evaluación exige retirar en el
documento transformado o en otro contenido recuperable de su artefacto.
_Evitar_: mero span no detectado, ausencia de hallazgos como prueba de ausencia.

**Conservación de contexto**:
Preservación de la información y las relaciones que la política de evaluación
exige mantener, incluidas negaciones y cantidades cuando corresponda.
_Evitar_: parecido semántico general, conservación de longitud.

**Regresión conocida**:
Caso previamente inspeccionado o usado para diagnosticar o corregir el sistema.
Es evidencia de estabilidad, no una observación independiente sin exposición.
_Evitar_: test ciego intacto.

**Linaje documental**:
Relación entre un documento de origen y sus variantes de formato, contenido
equivalente o degradación. Sus derivados no son muestras independientes.
_Evitar_: documentos independientes por tener archivos o hashes distintos.
