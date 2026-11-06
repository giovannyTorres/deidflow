<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-06 -->
# BMX-06: Evaluar la salida real del pipeline textual y sus estados

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Estado de implementación:** implementada, revisada y verificada en integración BMX-03–08.
Evidencia: [acta BMX-06](../../audit/BMX-06.md).

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-03, BMX-05.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Medir el pipeline real de detección/transformación con el motor existente, comparando la salida contra referencia y manteniendo aprobación, revisión, bloqueo y ausencia de salida separados.

## Criterios de aceptación

- [x] Informar fugas por mención/documento, conservación, resultado conjunto y conteos por estado.

- [x] Sin aprobados, la fuga entre aprobados es indefinida; sin salida no hay éxito conjunto ni fuga cero certificada.

- [x] Inspeccionar todas las salidas observables y no acreditar eliminación únicamente por mapas o por repetir el detector.

- [x] Los tres ejes de veredicto del evaluador no se confunden con ReleaseStatus; sin perfil ratificado no se emite aprobación de calidad.

## Pruebas y evidencia exigidas

- [x] Candidato que bloquea todo: cero éxito conjunto y denominador de aprobados cero.

- [x] Candidato que emite dato residual con APPROVED, REVIEW_REQUIRED o BLOCKED conserva evidencia y estado propios.

- [x] Candidatos que cambian solo un sufijo, copian el valor en otra zona o lanzan error no mejoran métricas por exclusión del caso.

## Trazabilidad

AC-06, AC-08, AC-09, AC-13 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- La solicitud actual autorizó implementar este incremento dentro del lote BMX-03 a BMX-12.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
