<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-05 -->
# BMX-05: Verificar protección y conservación con menciones de referencia

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-02.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Ejecutar transformación textual aislada usando el gold y un perfil explícito; comprobar sustitución real, conservación y mapas de salida sin atribuir fallos del detector a esta pista.

## Criterios de aceptación

- [ ] Evaluar remove, preserve, generalize y review_required bajo expectativas explícitas, incluso si son propuestas aún no ratificadas.

- [ ] Los mapas se contrastan con el contenido realmente emitido; copiar el original o conservar un sufijo no acredita retirada completa.

- [ ] Medir contexto requerido, retención no sensible, sobretransformación y resultado conjunto; operador sin verificador produce UNVERIFIABLE.

- [ ] Rechazar expectativas contradictorias sin precedencia declarada y conservar spans superpuestos admitidos.

## Pruebas y evidencia exigidas

- [ ] Transformador correcto frente a candidatos controlados que copian original, falsean mapas o dejan máscara parcial.

- [ ] Perfiles explícitos opuestos sobre el mismo contenido clínico; pérdida de «niega diabetes» reduce conservación y éxito conjunto.

- [ ] Marcador literal presente en la entrada y solapamientos con contexto que debe preservarse.

## Trazabilidad

AC-06, AC-08 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
