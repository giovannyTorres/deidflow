<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-14 -->
# BMX-14: Detectar fugas en contenido recuperable de DOCX

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-06.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Añadir un inspector de referencia DOCX que compruebe texto y slots recuperables del artefacto, con la regresión conocida del correo oculto en un atributo.

## Criterios de aceptación

- [ ] Inventariar partes/slots admitidos, atributos y metadatos de forma que la omisión del lector del candidato no se replique silenciosamente.

- [ ] El canario en w:tag/@w:val retenido se registra como fuga incluso cuando DeidFlow dice APPROVED.

- [ ] Partes/slots desconocidos o no inspeccionables mantienen cobertura incompleta y el caso visible.

- [ ] Comprobar utilidad/estructura soportada y no modificar el escritor de producción como parte de esta tarea.

## Pruebas y evidencia exigidas

- [ ] Fixture controlado con canario en texto visible, atributo de content control y otra parte conocida.

- [ ] Candidato controlado que declara mapas correctos pero conserva XML sensible produce chequeo de privacidad fallido.

- [ ] Parte desconocida, recurso malformado y documento limpio verifican incompletitud y ausencia de falsos certificados.

## Trazabilidad

AC-06, AC-07, AC-10 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
