<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-12 -->
# BMX-12: Evaluar perturbaciones textuales sin romper linaje ni referencia

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-10, BMX-11.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Generar derivados deterministas de formato/ruido textual, vinculados a su origen y evaluables como pistas separadas del texto limpio y del OCR real.

## Criterios de aceptación

- [ ] Cubrir mayúsculas, Unicode, separadores, saltos, columnas/texto desordenado, confusiones OCR simuladas y posiciones de corte/longitud/densidad.

- [ ] Actualizar referencia y coordenadas de manera controlada; no normalizar el texto puntuado.

- [ ] Todos los derivados permanecen con su grupo/partición y registran receta, versión y semilla.

- [ ] No describir ruido textual como resultado de Tesseract ni aumentar el peso de un origen por tener más variantes.

## Pruebas y evidencia exigidas

- [ ] Repetición de recetas conserva hashes y anotaciones dentro de rango.

- [ ] Derivado mal asignado entre particiones es rechazado por auditoría.

- [ ] La misma mención cerca de cortes, con CRLF/diacríticos y texto desordenado tiene referencia trazable y métricas por estrato.

## Trazabilidad

AC-05, AC-12, AC-14 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
