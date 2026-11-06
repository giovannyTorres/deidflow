<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-04 -->
# BMX-04: Medir validez de identificadores con vectores independientes

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-03.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Añadir la pista local de patrón, estructura y checksum de RFC, CURP, CLABE y tarjetas, con vectores ficticios cuya referencia no depende únicamente de los validadores evaluados.

## Criterios de aceptación

- [ ] Separar los tres atributos y distinguir invalid, valid, not_applicable y unknown.

- [ ] Mantener sensibilidad de referencia independiente de la validez; un checksum malo no transforma automáticamente el caso en negativo de detección.

- [ ] Registrar origen/versión de los vectores y su comprobación independiente; no consultar titularidad ni registros reales.

- [ ] El informe mantiene métricas de validación separadas de detección y transformación.

## Pruebas y evidencia exigidas

- [ ] Vectores válidos y alteraciones de un dígito con respuestas esperadas calculadas por referencia independiente.

- [ ] Fechas imposibles, truncados, longitudes y separadores; not_applicable no cuenta como checksum fallido.

- [ ] El mismo valor inválido se evalúa como sensible o distractor según la referencia explícita, sin usar el score del candidato.

## Trazabilidad

AC-04 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
