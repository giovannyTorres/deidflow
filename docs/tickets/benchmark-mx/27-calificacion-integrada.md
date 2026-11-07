<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-27 -->
# BMX-27: Emitir una calificación local reproducible y comprobar empaquetado

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-14, BMX-15, BMX-17, BMX-20, BMX-26.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Cerrar el recorrido completo con la matriz de capacidades obligatorias, informe verificable y compatibilidad de distribución. La aceptación del arnés no exige fingir que el candidato actual pasa calidad.

## Criterios de aceptación

- [ ] Ejecutar la matriz ratificada con cuatro pistas separadas y todas las referencias/versiones; conservar fallos, omisiones y ámbitos.

- [ ] Verificar que los inspectores disponibles se aplican también a adjuntos admitidos; ninguna capacidad pendiente se presenta como PASS.

- [ ] Emitir ejecución/conformidad/calidad y códigos de salida conforme al contrato; una ejecución válida puede informar FAIL del candidato.

- [ ] Repetir conteos/decisiones deterministas y reconstruir cocientes desde resultados seguros.

- [ ] Mantener wheel base sin dependencias obligatorias nuevas ni cambios en interfaces de producción; registrar perfiles/activos y alcance del inventario de dependencias.

- [ ] No publicar corpus, resultados, paquetes ni promover modelos automáticamente; preparar la evidencia para revisión.

## Pruebas y evidencia exigidas

- [ ] Recorrido de aceptación completo con fixtures y candidato real; los cuatro defectos conocidos se reportan sin arreglar el producto dentro del benchmark.

- [ ] Casos de éxito, incumplimiento, entrada inválida y ejecución incompleta comprueban códigos 0/2/3 y calidad descriptiva cuando corresponda.

- [ ] Dos ejecuciones con mismos insumos/versiones, canarios de logs y revisión de cada capacidad obligatoria.

- [ ] Smoke del wheel sin extras, importación offline y pip check de perfiles declarados; no instalar dependencias silenciosamente.

## Trazabilidad

AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-07, AC-08, AC-09, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
