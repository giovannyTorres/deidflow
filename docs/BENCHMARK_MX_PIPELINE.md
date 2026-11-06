# Pipeline textual y liberación observada

`deidflow.benchmarks.pipeline_runner.run_pipeline_benchmark` recibe paquete,
digest SHA-256 del manifiesto, candidato, perfil y salida nueva. El perfil es
`pipeline-descriptive-v1`; `rules.mx` llama al motor real `DeidEngine` offline,
sin NER ni descargas. El candidato recibe texto y Policy, nunca spans gold.
La Policy operacional se construye de las expectativas explícitas del perfil;
este alcance descriptivo no acredita custodia estricta.

Para pruebas locales de confianza se admite `PipelineCandidate(id, sha, run,
detect=None)`: run recibe texto y Policy y devuelve el Result público existente.
La detección original es una observación separada opcional. Importante:
`Result.findings` del motor contiene **residuales de salida**, no detecciones
originales. No se reutiliza como predicción contra el gold de entrada. Con el
motor integrado se mide `scan_text` original por separado; en un callback sin
esa observación, los conteos de detección son nulos con soporte conservado y
`ORIGINAL_DETECTIONS_UNAVAILABLE`. No se repite el detector para certificar
ausencia de fuga: la salida se inspecciona con referencia, mapas y contenido.

Se inspecciona toda salida textual observable, cualquiera que sea ReleaseStatus.
Una salida bloqueada o en revisión puede contener una fuga y aparece en su
estado. Ninguna salida implica ningún éxito conjunto y riesgo de emitidos
indefinido, nunca ausencia de fuga demostrada. Los errores/malformaciones
mantienen casos, menciones y conservación requeridos; no se publica la excepción.

Se agregan los fragmentos por documento con orden conservador ERROR,
UNSUPPORTED, BLOCKED, REVIEW_REQUIRED, APPROVED. Basta un fragmento emitido para
contar el documento como observable, pero se requieren todos para inspección
completa/éxito conjunto. Una aprobación agregada exige todos los fragmentos
aprobados. La regla está versionada como `worst_fragment_state.v1`.

Los conteos de emitidos N, fugas confirmadas L y no verificados sin fuga U dan
límites empíricos L/N y (L+U)/N, también entre aprobados emitidos. Sin emitidos
ambos son null con razón y denominador cero. No son intervalos poblacionales ni
una estimación de despliegue; se refieren exclusivamente al fixture observado.
Los mapas inválidos dejan riesgo incierto, aunque una copia literal única puede
confirmar fuga independientemente de ellos. Se reutiliza la inspección BMX-05
para conservación, retirada completa, sobretransformación y contexto.

El informe separa `verdicts.execution`, `technical_conformity` y `quality` del
estado de liberación del candidato. Una fuga demostrada o pérdida de contexto
es FAIL técnico; una capacidad/observación pendiente es INCOMPLETE. La calidad
es siempre DESCRIPTIVE_ONLY sin perfil de calidad ratificado. Este incremento
es texto/regresión conocida: no acredita los formatos obligatorios de primera
versión, aislamiento nativo, independencia ni aprobación profesional.

Los artefactos retornados por output_path, safe_jsonl y audit_path se leen con
límite de bytes, sin seguir symlinks ni bloquearse en FIFO. Se buscan residuales
en el texto decodificable; formatos distintos de .txt, rutas no legibles o
canales sin inspector quedan incompletos. No se concede retirada si aparece
residuo en otra salida. Conservación combina máscaras por carácter y obligaciones
por span entre todas las salidas, sin multiplicar los denominadores. Un mapa
malformado conserva la salida observable y se registra como error del candidato.
Las capacidades obligatorias desconocidas dejan documentos pendientes y
conformidad incompleta, aunque el recorrido textual conocido haya ejecutado.
