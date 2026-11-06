<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-19 -->
# BMX-19: Revisar y registrar activos locales de OCR sin descargas automáticas

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** decisión/revisión humana. **Etiqueta propuesta:** `ready-for-human`; no aplicada.

**Bloqueado por:** Ninguna (puede comenzar cuando se autorice la ejecución).

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Revisión humana; depende de insumos.

## Qué entrega

Dejar disponibles los binarios, idiomas y licencias necesarios para la integración OCR real, o documentar exactamente qué requisito externo falta.

## Criterios de aceptación

- [ ] Identificar versión/hash de Tesseract y datos de español/inglés requeridos, así como términos y procedencia.

- [ ] Usar activos locales revisados; cualquier adquisición es una acción separada autorizada, nunca inferencia con descarga automática.

- [ ] Registrar configuración, rutas locales privadas sin secretos y evidencia de ejecución básica del activo.

- [ ] Si falta un activo o permiso, mantener el requisito pendiente sin inventar una prueba ejecutada.

## Pruebas y evidencia exigidas

- [ ] Revisión de hashes/licencias y consulta local de versiones/idiomas.

- [ ] Prueba con imagen enteramente ficticia cuando los activos estén disponibles.

- [ ] Checklist que diferencia activo configurado de integración evaluada por el benchmark.

## Trazabilidad

AC-10, AC-11 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
