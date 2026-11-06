# Auditoría de independencia declarada

`deidflow.benchmarks.independence.audit_independence(package,
manifest_sha256=..., similarity=SimilarityProfile(...))` devuelve un informe
determinista sin textos ni valores del gold. Primero admite todo el paquete
con los mismos contratos y hashes de BMX-02. Una violación estructural produce
INVALID_RUN, incluida una variante OCR que cruza las restricciones de su linaje.

Construye clausura de grupo declarado, documento fuente, root documental,
familia de plantilla, hash de fuente, hash binario de artefacto original e
identidad explícitamente vinculada. Las
identidades requieren la evidencia sintética/referencia ya validada del paquete;
un nombre común o compartir idioma/proveedor no crea identidad. También une
documentos con texto exactamente igual o equivalente tras NFKC, casefold y
espacios. Esa normalización es solo de auditoría: no cambia offsets ni texto
de puntuación. Un componente repartido entre particiones o entre varios grupos
declarados bloquea la acreditación hasta corregir su asignación.

El perfil explícito versionado usa `nfkc-casefold-ws.word-trigram-jaccard.v1`,
umbral inicial declarado 0.85 y presupuesto de 100 000 comparaciones. Se registra
configuración y SHA-256. Se comparan documentos entre particiones/paneles; una
coincidencia cercana no resuelta bloquea, sin convertir similitud en identidad.
No se ajusta el perfil mirando el test. Debe fijarse antes de abrirlo y
conservarse con el recibo de ejecución. Su ausencia o agotamiento del presupuesto
no significa «sin duplicados»: se informa el motivo y no se acredita.

Los conteos separan train, validation, calibration, blind_test, known_regression
y external_transfer. Para el contrato blind_test se exige congelación unexposed
y exposición declarada false a entrenamiento, ajuste y evaluación previa, más
candidate_exposure unexposed. Cualquier desconocido/histórico impide acreditarlo.
Sin banco ciego se informa NO_BLIND_TEST; no se rebautizan fixtures conocidos.

`independence_accredited` se limita expresamente al alcance
`DECLARED_PACKAGE_RELATIONSHIPS_AND_EXPOSURE`: aprueba comprobaciones del paquete
y sus declaraciones, no autentica esas declaraciones, al custodio, historial de
pesos ni accesos. Los límites constan también en el JSON. La custodia real y el
perfil de calidad son tareas separadas; quality permanece DESCRIPTIVE_ONLY.
Un fixture de pruebas con declaraciones ficticias pasa únicamente ese contrato;
no es evidencia ciega de DeidFlow. Todos los materiales de este incremento ya
inspeccionados siguen siendo regresión conocida.

Ante una coincidencia sospechosa: resolver el linaje/grupo y mover juntos sus
derivados; conservar la decisión y una nueva versión del paquete. Si se usa el
caso para ajustar, mantenerlo como regresión y renovar evidencia independiente.
Cambiar semilla, hash, extensión o formato no resuelve la dependencia.
