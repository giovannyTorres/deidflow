<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-23 -->
# BMX-23: Evaluar anotaciones públicas admitidas sin mezclarlas con el test ciego

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-03, BMX-08, BMX-22.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Importar únicamente datos locales autorizados y anotados, validarlos y publicar sus métricas con geografía, alcance y exposición correctos.

## Criterios de aceptación

- [ ] Consumir anotaciones ya adjudicadas y SourceRecords con permisos; no descargar durante la evaluación.

- [ ] Preservar categorías mexicanas y documentar vistas comparables secundarias sin alias guiados por gold.

- [ ] Fuentes expuestas/al entrenamiento o sin independencia comprobada aparecen como external_transfer/known_regression, no blind_test.

- [ ] Mantener licencia, atribución y restricciones de redistribución en el paquete/informe; falta de soporte no fabrica precision/recall.

## Pruebas y evidencia exigidas

- [ ] Importación local autorizada produce métricas y procedencia esperadas.

- [ ] Fuente sin permiso, offsets erróneos o gold incompleto se rechazan o quedan fuera de calificación.

- [ ] Fuente extranjera o expuesta nunca se suma automáticamente al resultado mexicano independiente.

## Trazabilidad

AC-03, AC-14 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
