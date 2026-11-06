<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-26 -->
# BMX-26: Congelar un banco independiente con trazabilidad de exposición

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-07, BMX-12, BMX-23, BMX-25.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Preparar bajo custodia el banco de evaluación final con grupos disjuntos, referencia adjudicada, soporte y configuración congelados antes de medir al candidato.

## Criterios de aceptación

- [ ] Todas las celdas obligatorias ratificadas tienen datos/soporte o una conclusión formal de insuficiencia; no se reciclan fixtures expuestos como ciegos.

- [ ] Guardar hashes, versiones, linajes, referencias y evidencias de auditoría/permiso; comprobar conflicto exacto y cercano.

- [ ] El candidato no accede al gold ciego; capacidad ausente de custodia/aislamiento se declara y no se suplanta con hashes.

- [ ] Registrar congelamiento y accesos; al usar un caso para ajustar reglas, migrarlo a regresión y renovar el banco para la próxima calificación.

## Pruebas y evidencia exigidas

- [ ] Auditoría de grupos, derivados, valores vinculados y exposición contra todos los recursos declarados.

- [ ] Introducir deliberadamente un derivado cruzado, caso expuesto o hash alterado impide el congelamiento acreditado.

- [ ] Revisión de soporte/custodia y lectura autorizada; el test no se ejecuta para elegir su propio perfil.

## Trazabilidad

AC-01, AC-11, AC-12, AC-14 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
