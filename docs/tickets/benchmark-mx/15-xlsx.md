<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-15 -->
# BMX-15: Verificar celdas y copias recuperables en XLSX

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-13.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Extender el evaluador estructurado a XLSX sin limitarse a la cuadrícula visible, verificando canales recuperables y contexto tabular conservado.

## Criterios de aceptación

- [ ] Inventariar hojas/celdas y copias/atributos/partes soportadas; inspeccionar salida serializada.

- [ ] Distinguir regiones obligatorias verificadas de contenido desconocido; no declarar limpieza por no extraerlo.

- [ ] Medir retirada, estructura y cantidades requeridas manteniendo la política de revisión propia de XLSX.

- [ ] No cambiar comportamiento de producción ni degradar validaciones para hacer pasar el caso.

## Pruebas y evidencia exigidas

- [ ] Canarios en celda, cadena compartida/comentario o metadato admitido y copia oculta controlada.

- [ ] Cantidad y estructura preservadas; parte opaca provoca incompletitud.

- [ ] Relectura del artefacto detecta una copia residual aunque la primera localización se haya saneado.

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
