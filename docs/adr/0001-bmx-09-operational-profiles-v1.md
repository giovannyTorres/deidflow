# ADR 0001: perfiles operativos v1 de BMX-09

Estado: **ratificado en alcance operativo; revisión documental pendiente**.
Decisión: `BMX-09-operational-v1`, versión `1.0.0`.
Responsable: solicitante (`requester`). Fecha: `2026-11-06T18:02:28Z`.

## Procedencia y sustitución

La respuesta actual del solicitante resuelve D1–D3: automático desde el inicio,
global y con reentrenamiento/ajuste local fácil; protección de identificadores
personales plausibles atribuibles aunque sean inválidos, revisión de la
ambigüedad y conservación de distractores no personales documentados; perfiles
clínicos contextual y estricto. La respuesta previa ya hizo obligatorios todos
los formatos previstos, incluido OCR. Son resúmenes, no citas literales.

Esta ADR sustituye las recomendaciones y la condición pendiente de D1–D3 de la
sección Implementation Decisions de [DF-EVAL-MX v0.1.0](../specs/BENCHMARK_MX_SPEC.md) y del
[registro histórico](../audit/BMX-09-decisions-for-review.md).
La especificación congelada conserva su SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.
El [recibo JSON](../benchmark-mx/operational-decision-v1.json) representa esta
decisión; no es un paquete de evaluación ni un perfil de calidad.

## D1: automático, global y adaptable localmente

El objetivo es un pipeline **automático desde el inicio**, con alcance global y
reentrenamiento/ajuste local fácil. La ambigüedad no resuelta, la cobertura
incompleta o la falta de operador/inspector impiden una liberación automática
favorable: producen `REVIEW_REQUIRED`, `UNSUPPORTED` o `BLOCKED` según la
causa. La revisión es dirigida; no hay un requisito de revisión humana universal
para todos los resultados. Resolver una revisión exige reverificar el artefacto.

Global y facilidad de adaptación son objetivos de producto pendientes de
evidencia por idioma/localidad y de evaluación de usabilidad. El incremento
actual mantiene el alcance **español de México (`es-MX`)**: no se amplía el
corpus evaluado ni se acredita calidad global. La adaptación será local,
reproducible, con entrenamiento/validación/evaluación separados y promoción
explícita de candidatas, conforme al contrato offline y sin inferencia generativa.

Esta decisión no cambia código ni controles actuales de producción. El perfil
de calidad, umbrales, soporte y custodia siguen sin ratificar (BMX-25):
`quality_profile_ratified: false`; el benchmark permanece `DESCRIPTIVE_ONLY`.
Ratificar el objetivo automático no aprueba una versión ni acredita su seguridad.

## D2: sensibilidad y validez separadas

- Identificador personal plausible atribuido por el contexto: `remove`, aunque
  falle patrón, estructura o checksum.
- Atribución o sensibilidad ambigua: `review_required`; nunca negativo ni
  aprobación automática por omisión.
- Distractor documentado no personal: `preserve`. La evidencia describe su
  función no personal; un checksum o score del candidato no bastan.

Las reglas se aplican a ambos perfiles. La referencia separa validez,
sensibilidad, certeza y evidencia; las menciones de detección son las mismas
entre perfiles, con expectativas de transformación distintas.

## D3: entidades, contexto y precedencia

| Entidad/contexto | `contextual-v1` | `strict-v1` | Procedencia |
| --- | --- | --- | --- |
| `RFC`, `CURP`, `CLABE`, `PAYMENT_CARD`, `PHONE`, `EMAIL`, `PERSON` atribuibles | `remove` | `remove` | D2/D3 del solicitante |
| `ADDRESS`: dirección personal completa | `remove` | `remove` | Derivación conservadora de ingeniería |
| `EXACT_DATE`: fecha personal exacta, incluido nacimiento/atención | `remove` | `remove` | Derivación conservadora de ingeniería |
| `AGE`: edad sin granularidad acordada | `review_required` | `review_required` | Derivación; granularidad pendiente |
| `DIAGNOSIS`, `MEDICAL_CONDITION`, `MEDICATION`, `TREATMENT`, `CLINICAL_OBSERVATION` | `preserve` | `remove` | D3 del solicitante |
| Negación, dosis/unidad, cantidad clínica y relación clínica con el sujeto | `preserve` | `remove` con el hecho clínico completo | D3; delimitación derivada |
| Relación explícita/contexto no clínico admitido sin identificadores originales | `preserve` | `preserve` | D3/contrato de contexto |
| Otro cuasiidentificador sin regla o atribución ambigua | `review_required` | `review_required` | Derivación conservadora |
| Distractor documentado no personal | `preserve` | `preserve` | D2 del solicitante |

Dirección, fecha y edad **no fueron ratificadas individualmente**. Son valores
ejecutables conservadores v1, identificados como derivaciones de ingeniería,
no citas ni aprobaciones individuales. La edad queda en revisión hasta acordar
granularidad. No se generalizan edades/direcciones ni se desplazan fechas sin
reglas y verificadores posteriores explícitos. Una fecha/dirección documentada
no personal sigue D2; si es ambigua requiere revisión.

El contextual preserva diagnósticos, medicación, negación, dosis y relaciones
mientras retira identificadores. Las relaciones usan referencias estables sin
inferir identidades/alias. El estricto retira los hechos clínicos completos,
incluido el contexto que los reconstruiría. Retener clínica no la convierte en
información no sensible ni equivale a anonimato.

Precedencia: `review_required` > `remove` > `preserve`. La incertidumbre
impide aprobación automática; en contenido confirmado la protección
identificadora gana a la conservación clínica. Se preserva el contexto exterior
a los intervalos mínimos necesarios. Un conflicto restante invalida la
configuración, sin elegir silenciosamente.

## Operadores y formatos

Para `remove`: `placeholder`, `redact`, `suppress` solo con retirada
completa verificable. Para `preserve`: `keep`, con preservación exacta.
Para `review_required`: ningún operador obtiene crédito automático; una
candidata privada no se aprueba hasta resolver y reverificar. `mask`,
`pseudonym`, `indexed`, `generalize` y `date_shift` no acreditan retirada
completa v1 y necesitan otra política y verificador explícitos.

| Formato/celda obligatoria | Retirada admisible | Verificación exigida |
| --- | --- | --- |
| Texto | `placeholder`, `redact`, `suppress` | Bytes emitidos, mapas y contexto |
| CSV, TSV, JSON, JSONL | Los mismos | Archivo serializado, celdas, cabeceras, claves/valores |
| DOCX | Los mismos | Partes, texto, atributos, comentarios/metadatos retenidos |
| XLSX | Los mismos | Celdas, fórmulas, shared strings, comentarios/metadatos |
| HTML | Los mismos | DOM, atributos y slots retenidos admitidos |
| EML | Los mismos | Cabeceras, cuerpos, MIME y adjuntos admitidos |
| PDF nativo | `redact` físico verificado | Contenido recuperable y región visual; sin original recuperable |
| PDF escaneado y OCR de imagen | `redact` visual verificado | Referencia visual, píxeles, OCR real local y artefacto reconstruido |

Todos los previstos son obligatorios; ninguno opcional. Permitir un operador
no demuestra soporte implementado. Un placeholder editable no acredita
redacción física de PDF. Soporte ausente deja incompleta la celda y sin
conclusión favorable; bloquear todos los documentos tampoco satisface
conservación ni éxito conjunto.

## Escenarios y seguimiento

Identificador atribuible inválido: retirar; número de ejercicio documentado no
personal: conservar; clínica con negación/dosis: conservar contextual y retirar
estricto; PDF sin soporte: sin aprobación. No se incorporan datos personales
reales ni se fabrica gold, independencia o evaluación con esta decisión.

BMX-09 documenta ratificación del solicitante con revisión técnica pendiente.
BMX-10–12 conservan su bloqueo hasta la actualización del coordinador después
de la revisión; no se ejecutan desde esta ADR.
