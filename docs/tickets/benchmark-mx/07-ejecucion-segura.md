<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-07 -->
# BMX-07: Ejecutar con aislamiento local, límites y diagnósticos sin datos

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-01.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Hacer ejecutable y verificable la restricción local del arnés, con límites por proceso/caso y capacidades de aislamiento declaradas; mantener los fallos en el informe.

## Criterios de aceptación

- [ ] Prohibir y registrar intentos de red durante carga e inferencia, incluidos subprocesos; no confundir bloqueo de sockets Python con aislamiento nativo.

- [ ] Configurar límites de bytes/expansión, miembros, profundidad, píxeles, tiempo y memoria; distinguir admisión de límite duro.

- [ ] En custodia estricta el candidato solo accede a entradas/activos autorizados, no al gold; capacidad ausente se informa y bloquea acreditación estricta.

- [ ] Timeout, activos ausentes o respuestas malformadas mantienen el caso y su soporte en el informe; no instalar activos ni alterar el sandbox.

- [ ] Resumen y mensajes de error usan códigos permitidos y no contienen valores, nombres originales, secretos o variables de entorno.

## Pruebas y evidencia exigidas

- [ ] Adapter y subproceso controlados intentan red, incluso capturando la excepción: la condición local no pasa.

- [ ] Proceso intenta leer una referencia fuera de sus entradas; verificar la restricción real o declarar capacidad no acreditada.

- [ ] Timeout, expansión excesiva y memoria admitida versus límite duro producen estados correctos.

- [ ] Canarios en texto, nombre de archivo y excepción no llegan a logs/resumen.

## Trazabilidad

AC-10, AC-11 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
