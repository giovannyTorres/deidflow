<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-17 -->
# BMX-17: Verificar MIME, cabeceras y adjuntos admitidos

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-13, BMX-16.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Añadir evaluación de mensajes ficticios y sus adjuntos mediante inspectores disponibles; informar explícitamente los tipos que aún no pueden verificarse.

## Criterios de aceptación

- [ ] Inspeccionar cabeceras, cuerpos alternativos y adjuntos soportados sin contactar cuentas reales.

- [ ] Resolver adjuntos mediante capacidades disponibles, comenzando por texto/HTML/datos estructurados; otros quedan no verificados hasta disponer de inspector.

- [ ] Mantener procedencia de cada parte y estados de revisión; no eximir residuales solo porque parezcan marcadores.

- [ ] Límites y contenido MIME defectuoso/adjunto opaco degradan cobertura sin ocultar el caso.

## Pruebas y evidencia exigidas

- [ ] Canarios en cabecera, texto, alternativa HTML y adjunto CSV.

- [ ] Adjunto sin inspector produce INCOMPLETE en una celda obligatoria, no ausencia de fugas.

- [ ] Cabecera regenerada legítima frente a metadato de fuente que imita marcador; ningún envío de correo se realiza.

## Trazabilidad

AC-06, AC-10, AC-11 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
