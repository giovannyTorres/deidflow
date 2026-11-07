<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-02 -->
# BMX-02: Rechazar paquetes inválidos y preservar anotaciones superpuestas

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Estado de implementación:** completada y verificada. Véase el
[acta de aceptación BMX-02](../../audit/BMX-02.md), con ciclos TDD, cobertura,
revisión independiente, métricas y límites pendientes.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-01.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Extender el recorrido para validar recursos, integridad, referencias y anotaciones antes de evaluar. Un paquete admisible llega al informe; uno inconsistente produce un diagnóstico seguro, sin resultados favorables.

## Criterios de aceptación

- [x] Validar los contratos de manifiesto, fuentes, documentos, unidades, menciones, expectativas y recursos usados por el paquete.

- [x] Rechazar claves duplicadas, no finitos, bool como offset, UTF-8 inválido, referencias rotas, versiones desconocidas y hashes/tamaños/conteos alterados.

- [x] Permitir spans anidados/cruzados legítimos y rechazar duplicados idénticos, contradicciones y coordenadas fuera de rango.

- [x] Las referencias de recursos no escapan del paquete por traversal o enlaces; distinguir error de dataset de respuesta malformada del candidato.

## Pruebas y evidencia exigidas

- [x] Un paquete válido con dos menciones solapadas completa la admisión.

- [x] Casos parametrizados para cada clase inválida y alteración de un byte.

- [x] Traversal, enlace escapado y miembro ZIP duplicado se rechazan sin exponer valores en el error.

## Trazabilidad

AC-01, AC-05 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- La creación original no inició la implementación; la segunda solicitud `/implement` autorizó este incremento.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
