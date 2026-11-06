<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-01 -->
# BMX-01: Evaluar un correo de un paquete local a un informe reproducible

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** Ninguna (puede comenzar cuando se autorice la ejecución).

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Ejecutar una pista de detección mínima con el reconocedor existente: un caso EMAIL positivo y un documento negativo conocidos producen un informe descriptivo con identificadores opacos, conteos y configuración explícita. Este corte fija la seam paquete/candidato/perfil → informe y no afirma aislamiento estricto ni cobertura de otras capacidades.

## Criterios de aceptación

- [ ] El recorrido carga un paquete sintético mínimo versionado y usa el detector real sin modificarlo.

- [ ] El informe identifica candidato, dataset, pista, perfil y alcance EMAIL; la calidad permanece DESCRIPTIVE_ONLY sin ratificación.

- [ ] Dos ejecuciones conservan conteos/decisiones y no sobrescriben resultados; timestamps y medidas operativas se separan.

- [ ] Los documentos, valores y nombres originales no aparecen en el resumen; ninguna adquisición o descarga se ejecuta.

## Pruebas y evidencia exigidas

- [ ] Fixture positivo/negativo con conteos exactos conocidos.

- [ ] Repetición en dos destinos nuevos y comparación de campos deterministas.

- [ ] Destino ya existente rechazado y canario ausente del resumen.

## Trazabilidad

AC-12, AC-13 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
