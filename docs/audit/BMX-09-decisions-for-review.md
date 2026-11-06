# BMX-09: decisiones preparadas para ajuste y ratificación

Estado: **pendiente de ajustes humanos, no ratificado**. Fecha de registro:
2026-11-06 UTC. Responsable de la decisión: solicitante de esta sesión.
Origen: respuestas explícitas «Mantener BMX-03 a BMX-12», «Quiero ajustar las
decisiones antes de ratificar» y «Todos los previstos: texto, estructurados,
Office, HTML, EML, PDF y OCR».

La selección del bloque no aprueba los perfiles. La selección de formatos sí
resuelve su obligatoriedad; no prueba que existan operadores/inspectores.
Las decisiones restantes están pendientes, no se deducen del silencio.

| Decisión | Recomendación anterior, editable | Acuerdo actual |
| --- | --- | --- |
| D1: uso operativo v1 | Apoyo supervisado; liberación automática separada | Ajuste concreto pendiente |
| D2: identificador plausible inválido | Proteger o escalar aunque falle checksum; preservar distractor documentado no personal | Ajuste concreto pendiente |
| D3: clínica y cuasiidentificadores | Dos perfiles: contexto conservado y estricto, con mismas menciones de detección y expectativas distintas | Ajuste concreto pendiente |
| Formatos de primera versión | Todos los previstos | Confirmado por el solicitante el 2026-11-06 |

Para D1 falta indicar si se respalda solo descripción, uso supervisado o
automático y qué revisión se exige. Esa decisión operativa no ratifica un perfil
de calidad ni autoriza liberar una versión: sin umbrales y soporte ratificados,
todos los resultados siguen DESCRIPTIVE_ONLY.

Para D2 falta separar explícitamente remove de review_required para un
identificador que el contexto atribuye a una persona pero cuyo checksum falla.
También falta confirmar qué evidencia permite clasificar un valor como
distractor no personal; validez técnica e identidad no son equivalentes.

Para D3 falta concretar qué debe retirarse o conservarse de diagnósticos,
medicación, negación, dosis, cantidades y relaciones, y cómo se tratan
dirección, edad, fecha y otros cuasiidentificadores. Conservar clínica por utilidad
no significa que deje de ser información sensible.

## Matriz obligatoria confirmada; operadores propuestos sin ratificar

| Celda obligatoria | Protección propuesta | Conservación/verificación requerida | Estado del benchmark |
| --- | --- | --- | --- |
| Texto | Placeholder, redact o suppress íntegros | Mapas y contenido real; contexto según D3 | Recorridos descriptivos BMX-03–08 |
| Estructurados | Sustitución/supresión por campo y contenido | Esquema, claves, celdas y valores retenidos | Pendiente BMX-13 |
| Office DOCX | Sustitución/supresión en partes admitidas | Texto, atributos, comentarios, metadatos y partes retenidas | Pendiente BMX-14 |
| Office XLSX | Sustitución/supresión por celda/slot | Fórmulas, shared strings, comentarios y metadatos | Pendiente BMX-15 |
| HTML | Sustitución/supresión por slot | DOM, atributos, texto y contenido retenido | Pendiente BMX-16 |
| EML | Sustitución/supresión por parte | Cabeceras, cuerpos, MIME y adjuntos admitidos | Pendiente BMX-17 |
| PDF nativo | Redacción física/verificada, sin original recuperable | Contenido recuperable y región visual | Pendiente BMX-18 |
| PDF escaneado/OCR | Redacción visual y extracción local verificadas | Referencia visual, OCR real local y artefacto reconstruido | Pendiente BMX-19/20 |

No hay celdas opcionales aprobadas en esta primera versión. Un operador o
inspector obligatorio ausente deja la celda sin aprobar; no basta con devolver
APPROVED, bloquear todos los documentos o producir un placeholder. Pseudónimos,
generalización, desplazamientos de fecha y máscaras requieren reglas/verificadores
explícitos antes de aceptar sus resultados; una máscara parcial no acredita
retirada completa. Las propuestas de esta tabla no habilitan operadores.

## Escenarios para decidir sin documentos personales reales

| Escenario ficticio | Decisión que falta | Regla invariable del arnés |
| --- | --- | --- |
| CURP etiquetada con checksum alterado | Retirar o exigir revisión, según D2 | No convertir invalidez en etiqueta negativa automáticamente |
| Número de ejercicio no personal parecido | Evidencia/expectativa de preservación, según D2 | No usar checksum como única referencia de sensibilidad |
| «niega diabetes», medicamento y «500 mg» | Qué conservar en cada perfil y qué retirar, según D3 | Si se exige conservación y se pierde, falla conservación y éxito conjunto |
| PDF sin operador o inspector requerido | Alcance operativo, según D1 | Celda obligatoria incompleta; no aprobación favorable |

Los perfiles definitivos registrarán versión, acciones, precedencia ante
solapamientos, operadores, verificadores, estados aceptables, responsable y
fecha de ratificación. No se escriben perfiles ratificados ni gold de
calificación hasta resolver estos puntos. BMX-10 y BMX-11 siguen bloqueadas;
BMX-12 depende de ambas. No se inició su implementación.
