# Ejecución local aislada

`deidflow.benchmarks.isolation.run_isolated_case` ejecuta un programa Python
local fijado por SHA-256. Recibe `input_payload`, `case_id` opaco,
`required_mentions`, `output` nuevo, `IsolationLimits`, activos opcionales
`LocalAsset(asset_id, path, sha256)` y, en custodia estricta, `reference_root`.
El programa lee `/inputs/input.json` y activos individuales `/assets/asset-*`.
Responde en stdout exactamente un JSON:

```json
{"status":"COMPLETED","counts":{"completed_documents":1,"completed_mentions":0}}
```

Solo contadores enumerados y acotados se publican. Soporte requerido procede
del arnés, nunca del candidato; toda salida conserva documento/menciones
requeridos aun ante error, activo ausente, timeout o respuesta malformada.
Los contadores son observaciones declaradas por ese programa; esta frontera de
ejecución no sustituye matching, referencia ni verificadores de las otras pistas.

Esta es una entrada de proceso separada. Los callbacks de confianza BMX-01–06
siguen siendo entradas en proceso y no se acreditan automáticamente como
custodia estricta. Para usar este aislamiento con una pista, su programa debe
recibir únicamente el input autorizado; en custodia estricta la puntuación del
gold se hace fuera del candidato. Esta API no monta el paquete ni el cwd.

Se requieren Linux, bubblewrap y strace ya instalados, namespaces de usuario,
PID, red y montaje permitidos, y trazado de un hijo permitido. No se instala
nada ni se modifica la política del sandbox o del entorno. Ausencia/fallo de
esa capacidad produce UNSUPPORTED sin acreditación. Se montan solamente
runtime estándar readonly, script genérico, input y activos por hash. El espacio
temporal es independiente; entorno heredado vacío y Python `-I -S -B` evita
plugins/site/user y escritura de bytecode. No se montan home, workspace, gold,
proxies o credenciales. Se rechaza el solapamiento del directorio de referencia
con runtime o activos autorizados. Un activo requiere presencia y hash local.

El namespace de red impide acceso a la red del host. strace externo al namespace
del candidato registra syscalls nativas desde exec del intérprete, incluidos
hijos. Los intentos posteriores a esa frontera hacen LOCAL_POLICY_VIOLATION
aunque una excepción se capture. Se excluye únicamente el bootstrap de red de
bubblewrap anterior al exec; importación/carga/inferencia del programa quedan
dentro. El trazado incompleto/truncado no acredita ejecución estricta. La prueba
de aceptación incluye socket Python, libc y subproceso: no solo mocks Python.

Límites duros heredados por proceso: RLIMIT_AS (espacio de direcciones, no RSS ni
cgroup agregado), RLIMIT_CPU, RLIMIT_FSIZE, core=0 y descriptores; watchdog de
tiempo de pared mata el grupo de procesos y bubblewrap termina su namespace.
Un ENOMEM observado sigue produciendo RESOURCE_LIMIT aunque se capture. Bytes
de input/script/activo, total, salida y trazas se acotan realmente al leer.
Expansión, miembros, profundidad y píxeles tienen máximos de admisión explícitos;
sus mediciones aquí son declaradas por el llamador. No se confunden con un
decoder/inspector real de Office/PDF/OCR ni con límites duros de píxeles.

Stdout, stderr y trazas viven en un temporal privado que se borra. Resumen y
errores solo incluyen códigos, conteos, límites, identificadores opacos y
capacidad acreditada. No publican programa, texto, paths, variables, trazas ni
excepciones. La calidad permanece DESCRIPTIVE_ONLY.

Cambios persistentes del entorno preparados para revisión, no aplicados: si
otro host no dispone de capacidades, necesitaría aprovisionar bubblewrap y
strace, permitir namespaces de usuario/PID/red/montaje y ptrace de hijos, y
exponer un runtime Python local readonly. En este host ya están disponibles;
la tarea no cambia paquetes, permisos, servicios ni configuración de nube.
