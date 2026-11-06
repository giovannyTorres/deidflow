# BMX-10: corpus ficticio de identificadores

Implementación acotada sobre `907ec9e6d2a2c4148c6298d84b36111680e3bcd3`.
Ticket: [BMX-10](../tickets/benchmark-mx/10-corpus-identificadores.md).
Contrato y comandos: [corpus de identificadores](../BENCHMARK_MX_IDENTIFIERS.md).

Se entrega un generador público local, escritor compartido y ejemplo de 36
casos, ocho familias y seis entidades. Hay 27 menciones y 36 vectores;
26 casos requieren retirada, nueve preservación y uno revisión. Las cuatro
configuraciones descriptivas contienen 144 expectativas en total. Grupos/panel
se asignan antes de renderizar; el seed solo selecciona plantillas. Todos los
casos están expuestos como `known_regression`; particiones vacías explícitas.
No se añadió dependencia ni se cambió lógica de producción.

El recibo operativo ratificado se incorpora con SHA verificado como
`evidence-9`. Las configuraciones ejecutables son técnicas, no ratificadas
individualmente, y la calidad permanece `DESCRIPTIVE_ONLY`. No se afirma que
el usuario haya dejado pendientes D1–D3, ni que aprobara estas configuraciones
o la calidad de un candidato.

TDD en el seam autorizado: primero falló la importación del generador; tras
el primer recorrido reproducible/admitido pasó. La siguiente prueba falló por
cubrir solo RFC y pasó al ampliar las seis entidades con recorridos reales de
detección/validez. La frontera del escritor falló al filtrar un error de ruta y
pasó al sanearlo. También se ejercitan la no sobrescritura, rechazo real de
digest adulterado, pin del recibo, cambio de seed sin mover grupos/etiquetas,
re-serialización de registros cargados y preservación del límite de independencia.
Logs: `/tmp/deidflow-batch/BMX-10/{generator,coverage,writer}-{red,green}.log`.

La [evidencia de referencia](BMX-10-vectors.json) registra 27 comprobaciones
numéricas con stdnum/hoja CLABE y nueve casos de teléfono/correo inspeccionados
por otro agente con sintaxis independiente. Cero desacuerdos entre las
referencias declaradas y esos checks acotados. Las etiquetas de sensibilidad
siguen el contexto y D2, no las predicciones del candidato. `reviews:[]` no
inventa revisores humanos; `adjudicated` expresa una referencia ficticia resuelta
por su autor mediante esas comprobaciones, sin validación humana de despliegue.

Se corrigió un error real del oráculo anterior: `XEXX` tiene dígito ordinario
válido; el rechazo completo de stdnum era por homoclave. El fixture BMX-04
actual es `1.0.1`, con una discrepancia `XAXX`, y se conserva la
[fe de erratas](BMX-04-erratum.md) junto con los recibos históricos intactos.

El ejemplo BMX-10 tiene manifest SHA-256
`ed2a387e84ab9a0b5764a803e59ea8f173e5c2eceaea00debd2b26064a1c1dba`.
La repetición produce los mismos bytes/hashes; otro seed cambia los textos sin
cambiar referencias ni grupos. La detección completa 36 documentos y conserva
falsos positivos de distractores y falsos negativos de valores truncados o
malformados. La validez completa 36 vectores: una discrepancia de checksum RFC
por la excepción `XAXX`; PHONE/EMAIL muestran sus predicciones desconocidas.
La auditoría registra ocho componentes, cero cruces, cero grupos separados y
`NO_BLIND_TEST`, con `independence_accredited:false`.

Verificación focalizada: 32 pruebas de corpus/validez pasan. Ruff/formato y mypy
Python 3.12 pasan; el chequeo mypy con el target configurado 3.11 encontró
primero un stub instalado de NumPy que usa sintaxis 3.12, por lo que se usó el
comando Python 3.12 ya documentado por el entorno. Logs e informes en
`/tmp/deidflow-batch/BMX-10/`. Suite completa, cobertura, microbenchmark y wheel
quedan para la integración del lote; no se presentan como ejecutados aquí.
Las revisiones frescas Standards/Spec del commit se registrarán en la entrega
de integración; no se inventa su resultado en esta acta de implementación.
