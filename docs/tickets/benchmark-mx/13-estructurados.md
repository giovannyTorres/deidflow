<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-13 -->
# BMX-13: Verificar salidas CSV/TSV y JSON/JSONL reales

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-06.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Extender el pipeline a datos estructurados con localizadores estables y comprobación de valores, esquema, índices y metadatos que puedan conservar información.

## Criterios de aceptación

- [ ] La pista inspecciona el archivo serializado real, no solo el DataFrame u objeto anterior a escribir.

- [ ] Comprobar fila/celda/ruta, datos sensibles en cabeceras/claves y conservación de valores/estructura exigidos.

- [ ] Mantener scope por formato, cobertura y capacidades; contenido no inspeccionado no recibe éxito.

- [ ] Límites, formatos malformados y salida ausente se informan con denominadores y estados correctos.

## Pruebas y evidencia exigidas

- [ ] Canario en celda, cabecera y clave/valor JSON; comprobar también una cantidad no sensible preservada.

- [ ] JSON con claves duplicadas/no finitos, fila desigual y archivo truncado.

- [ ] Duplicación de un valor sensible fuera de la celda original no pasa por confiar en el mapa de la primera transformación.

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
