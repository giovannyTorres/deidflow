<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-10 -->
# BMX-10: Preparar corpus sintético mexicano de identificadores y negativos

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-04, BMX-08, BMX-09.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Estado del lote

BMX-09 ratificada y revisada: se inicia la continuación secuencial autorizada
del lote. Se conservan las dependencias y los criterios originales.
[Revisión humana pendiente](../../audit/BMX-09-decisions-for-review.md).

## Qué entrega

Producir un paquete de identificadores mexicanos completamente ficticios con validez comprobada independientemente, negativos difíciles, familias diferenciadas y soporte reportado.

## Criterios de aceptación

- [ ] Cubrir RFC física/moral/genéricos, CURP, CLABE, tarjetas, teléfonos mexicanos y correos con variantes válidas/inválidas y distractores.

- [ ] Etiquetas y sensibilidad siguen perfiles ratificados; no derivar gold de las predicciones del candidato.

- [ ] Asignar grupos/particiones antes de derivados y registrar semillas, algoritmos, procedencia y vectores de validez.

- [ ] Emitir soporte por entidad/estrato y errores reales de admisión; un fixture no se presenta como muestra de despliegue ni cuenta existente.

## Pruebas y evidencia exigidas

- [ ] Repetir generación y comparar hashes/conteos.

- [ ] Auditoría independiente de vectores y casos negativos; pasar el paquete por validación, pista de validez y detección.

- [ ] Comprobar separación de grupos, metadatos de licencia/procedencia y ausencia de consultas de titularidad.

## Trazabilidad

AC-03, AC-04, AC-12 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
