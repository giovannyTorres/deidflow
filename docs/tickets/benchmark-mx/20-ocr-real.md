<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-20 -->
# BMX-20: Medir OCR real y privacidad del pipeline de imágenes sintéticas

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-12, BMX-18, BMX-19.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Comparar referencia visual, texto OCR observado, detección y salida transformada usando únicamente imágenes ficticias y activos OCR locales fijados.

## Criterios de aceptación

- [ ] Separar extracción, detección sobre texto observado y resultado extremo a extremo.

- [ ] Un dato omitido por el OCR pero visible en salida permanece fuga del pipeline o verificación insuficiente.

- [ ] Registrar motor/idiomas/hashes, degradaciones y coordenadas; distinguir ruido simulado de OCR real.

- [ ] Activos ausentes, timeout o salida vacía injustificada no se registran como integración aprobada.

## Pruebas y evidencia exigidas

- [ ] Imagen limpia, ruido/resolución/rotación controlados y omisión OCR de una mención con gold visual.

- [ ] Motor e idioma ausentes, timeout y OCR vacío con página no blanca.

- [ ] Informe de una ejecución real local con activos fijados y la misma receta repetida; si no puede ejecutarse, la tarea no se da por integración completada.

## Trazabilidad

AC-10, AC-11, AC-12 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
