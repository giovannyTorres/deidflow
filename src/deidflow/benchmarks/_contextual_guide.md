# Guía de referencia contextual ficticia MX, versión 1.0.0

Esta guía describe doce literales originales de DeidFlow, Apache-2.0. Todos
los nombres, domicilios y expedientes son ficticios. No se consultan documentos
personales ni predicciones del candidato para anotar. Diez casos confirmados
forman una regresión conocida; dos desafíos no resueltos se entregan aparte.
No es una muestra natural, un test ciego ni evidencia de calidad de despliegue.

## Coordenadas y cobertura

Se anota el texto original sin normalizar: puntos de código Unicode de Python,
base cero e intervalos semiabiertos [start,end). Se conservan acentos, comillas
y CRLF. `surface` debe ser exactamente `text[start:end]`; el registro conserva
los 24 caracteres previos y posteriores disponibles para auditar el límite.
La variante sin puntos omite solamente los puntos del literal narrativo.
Ambas narrativas conservan familia y grupo, sin fingir muestras independientes.

En los casos confirmados, la inspección completa se limita a PERSON, ADDRESS,
DIAGNOSIS, MEDICAL_CONDITION, MEDICATION, TREATMENT y CLINICAL_OBSERVATION.
No se infieren categorías ausentes: edad/etapa vital, lugares aislados, roles,
organizaciones y palabras generales quedan fuera del alcance declarado.
`recién nacida` describe una etapa vital y no se etiqueta como enfermedad.
Patrón, estructura y checksum son `not_applicable` para estas categorías.

## Límites y categorías

- PERSON: nombre completo escrito, incluidas partículas internas. Excluir
  roles, etiquetas de campo, honoríficos y puntuación externa. Un nombre corto
  cuenta si el texto lo atribuye expresamente a una persona; no se exige que
  conste su identidad completa. Se anotan también las menciones repetidas en
  una pregunta explícita sobre la identidad de esa persona.
- ADDRESS: desde el tipo de vía hasta la última localidad del domicilio.
  Incluir número, interior, colonia, abreviaturas y puntuación interna.
  Excluir la etiqueta `Domicilio:`, el punto final y `(localidad ficticia)`.
  Un nombre dentro de la vía no es otra mención PERSON sin referente personal.
- DIAGNOSIS: expresión de enfermedad, incluido subtipo, incluso cuando aparece
  negada. La anotación de `diabetes` en `niega diabetes` registra una referencia
  lingüística; no atribuye diabetes al paciente.
- MEDICAL_CONDITION: síntoma o signo, con su calificador (`dolor leve`,
  `dolor torácico`, `fiebre`). No duplicar la enfermedad DIAGNOSIS bajo esta
  etiqueta. Negar un síntoma no elimina su mención lingüística.
- MEDICATION: nombre del medicamento. Dosis, vía y frecuencia pertenecen al
  régimen TREATMENT que lo contiene; conservar ambos spans anidados.
- TREATMENT: régimen completo indicado, incluidas dosis, unidades, vía,
  frecuencia o descripción de ejercicios. `Continúa el tratamiento indicado`
  es una referencia explícita de continuidad terapéutica y se anota completa.
- CLINICAL_OBSERVATION: afirmación de síntoma o polaridad completa. Incluir
  `sin`, `niega`, `no presenta` y el sujeto relacional cuando está dentro de
  la frase (`Su madre refiere dolor leve`, `el paciente no presenta dolor`).
  Conservar además el síntoma o diagnóstico anidado. Una etiqueta de campo
  no forma parte del span.

No se fuerzan límites de tokens. Spans diferentes anidados y cruzados se
conservan. Se rechaza un duplicado exacto de unidad/tipo/intervalo.

## Identidad y casos especiales

La igualdad de letras nunca basta para vincular personas. Las dos `Rosa del
Valle` tienen IDs distintos: el texto dice que son personas distintas y distingue
recién nacida de médica. Las dos notas de `Elena Itzel Castañeda` sí aportan
continuidad observable por título y por la frase `es la misma paciente`;
sus menciones comparten ID, grupo y familia, con evidencia `explicit_reference`.

José de la Paz y Pepe son menciones PERSON confirmadas. La relación entre sus
nombres sigue indeterminada: no se asigna ID ni a su posible alias ni a las
repeticiones. No se exige una fusión ni una separación de identidad. Esa
incertidumbre de vínculo se registra aparte de la certeza de detectar nombres.

`Esperanza Sierra` es PERSON; `esperanza de mejorar` es una palabra común.
`Calle Esperanza` pertenece al ADDRESS. Estos últimos textos no son PERSON.

El caso `crossed_mentions` es deliberadamente artificial: el texto define que
la cadena `Ana María Sol` codifica dos personas distintas, `Ana María` y
`María Sol`, compartiendo los caracteres `María`. Se anotan los dos spans
cruzados de la cadena y las dos menciones explicativas posteriores, cada una
con el ID ficticio correspondiente. La mención aislada del segmento `María`
es metalingüística, no una tercera persona. Este caso verifica mecánica de
spans; no se anuncia como dificultad natural ni se exige al detector inferir
una codificación que no estaría declarada en la entrada.

En `uncertain_referent`, `Sol` podría ser persona, calle o firma comercial:
se conserva una hipótesis PERSON ambigua. En `uncertain_boundaries` se
conservan las hipótesis cruzadas `Ana María` y `María Sol`, sin resolver el
número de personas ni sus límites. No tienen IDs y requieren revisión.
Estas tres hipótesis quedan en un paquete de desafío separado, con cobertura
inspeccionada pero sin categoría exhaustiva; no alimentan métricas primarias.

## Expectativas y adjudicación

Los paquetes contextual y estricto contienen las mismas menciones de detección.
En ambos se retiran PERSON y ADDRESS completos. El contextual conserva todas
las menciones clínicas, incluidas observaciones y regímenes completos que
protegen negación, dosis, cantidades y atribución. El estricto retira esas
mismas menciones clínicas completas. Lo que queda fuera de los spans
retirados sigue sujeto a conservación exacta. Las etiquetas de campo se
conservan. Los desafíos exigen `review_required`; el transformador automático
no los convierte en éxito conjunto. La precedencia es review_required,
remove, preserve, conforme al recibo operativo D3.

Se permiten para remove placeholder, redact y suppress; preserve usa keep.
No se acredita generalización, identidad estable ni anonimato. Los cuatro
perfiles técnicos conservan `ratified:false`; el recibo operativo ratificado
se adjunta aparte y la calidad sigue DESCRIPTIVE_ONLY.

El ledger distingue autoría sintética, revisión real de agentes y comprobaciones
mecánicas. Sus actores, fechas, decisiones y desacuerdos deben corresponder
a acciones realmente realizadas. La procedencia de mención sigue siendo
`synthetic_fixture`, nunca `human_review`. Los IDs r-hex deben existir en ese
ledger y estar ligados a los hashes exactos de esta guía y de la referencia.
Sin esas revisiones los casos se mantienen draft. Un agente revisor no es
un humano y una comprobación de integridad no autentica a un editor externo.
