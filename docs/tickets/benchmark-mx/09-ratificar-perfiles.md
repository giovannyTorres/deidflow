<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-09 -->
# BMX-09: Ratificar perfiles operativos, sensibilidad y conservación

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** decisión/revisión humana. **Etiqueta propuesta:** `ready-for-human`; no aplicada.

**Bloqueado por:** Ninguna (puede comenzar cuando se autorice la ejecución).

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Revisión humana; depende de insumos.

## Estado humano actual

Formatos confirmados: todos los previstos, incluido OCR. El solicitante pidió
ajustar D1–D3 antes de ratificar; sigue pendiente su definición concreta.
[Decisiones y escenarios preparados](../../audit/BMX-09-decisions-for-review.md).
No hay ratificación ni cierre de esta tarea.

## Qué entrega

Resolver con el responsable las decisiones D1–D3 y el alcance obligatorio por formato, dejando perfiles documentados y versionados antes de producir referencia de calificación.

## Criterios de aceptación

- [ ] Registrar si v1 respalda uso supervisado, automático o solo descriptivo, sin interpretar silencio como aprobación.

- [ ] Resolver explícitamente tratamiento de identificadores plausibles inválidos frente a distractores no personales.

- [ ] Acordar expectativas clínicas/otros cuasiidentificadores y operadores permitidos por formato; no convertir retención clínica en afirmación de no sensibilidad.

- [ ] Definir celdas obligatorias/opcionales; conservar recomendación, decisión, responsable y fecha sin fabricar conformidad.

## Pruebas y evidencia exigidas

- [ ] Revisión de escenarios: CURP etiquetada con checksum malo, número inocuo similar, negación/dosis y PDF sin soporte del operador.

- [ ] Comprobar que cada escenario tiene una expectativa no contradictoria por perfil.

- [ ] Revisión documental de completitud y de los puntos aún pendientes; no pruebas ejecutadas del benchmark.

## Trazabilidad

AC-04, AC-08, AC-13 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
