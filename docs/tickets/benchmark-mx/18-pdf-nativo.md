<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-18 -->
# BMX-18: Verificar PDF nativo y reconstrucción visual con gold controlado

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-06.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Evaluar PDFs sintéticos con referencia textual y geométrica, inspeccionando la reconstrucción y el contenido recuperable en vez de confiar en la extracción del candidato.

## Criterios de aceptación

- [ ] Registrar página, escala, rotación y regiones originales; distinguir operadores válidos de PDF de marcadores textuales.

- [ ] Verificar regiones y gramática/contenido retenido del artefacto final con evidencia de referencia.

- [ ] Una zona no comprobable, geometría no soportada o capacidad faltante queda UNVERIFIABLE/INCOMPLETE.

- [ ] No acreditar ausencia visual únicamente porque un OCR o extractor no devuelve el identificador.

## Pruebas y evidencia exigidas

- [ ] PDF generado localmente con canario en región conocida y cantidad que debe preservarse.

- [ ] Candidato oculta el canario de la extracción pero mantiene glifos visibles: detectar fuga o verificación incompleta.

- [ ] Salida reconstruida correcta, región incompleta y geometría no soportada conservan estados y denominadores.

## Trazabilidad

AC-06, AC-10 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
