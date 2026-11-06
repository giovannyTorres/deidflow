<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-11 -->
# BMX-11: Evaluar nombres, direcciones, clínica y homónimos con referencia adjudicada

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-05, BMX-08, BMX-09.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Estado del lote

BMX-09 ratificada y revisada: se inicia la continuación secuencial autorizada
del lote. Se conservan las dependencias y los criterios originales.
[Revisión humana pendiente](../../audit/BMX-09-decisions-for-review.md).

## Qué entrega

Preparar casos ficticios contextuales que permitan medir tanto detección como conservación, con identidad y ambigüedad explícitas en lugar de adivinadas.

## Criterios de aceptación

- [ ] Cubrir nombres/direcciones mexicanos, formularios/narrativa, negaciones, dosis/cantidades y relaciones requeridas.

- [ ] Conservar spans anidados/cruzados y evidencia de límites; separar panel ambiguo no resuelto de métricas primarias.

- [ ] Homónimos se evalúan por mención; vinculación entre documentos solo donde la entrada aporta evidencia suficiente.

- [ ] Registrar adjudicación y guías reales; no inventar revisores ni usar al candidato como anotador de referencia.

## Pruebas y evidencia exigidas

- [ ] Casos con/sin punto en narrativa clínica, nombres que son lugares/palabras comunes y roles incompatibles.

- [ ] Mismo nombre para personas distintas, continuidad explícita y alias indeterminado.

- [ ] Transformación aislada comprueba contexto; auditoría impide cruce de familias/identidades vinculadas entre particiones.

## Trazabilidad

AC-05, AC-08 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
