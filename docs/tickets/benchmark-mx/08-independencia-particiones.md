<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-08 -->
# BMX-08: Auditar particiones por grupos, linajes y exposición

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-02.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Admitir como independiente solo un paquete con auditoría verificable de grupos y exposición, distinguiendo entrenamiento, ajuste, calibración, regresión, transferencia y test ciego.

## Criterios de aceptación

- [ ] Construir/comprobar la clausura de documento fuente, linaje, familia de plantilla e identidad sintética vinculada sin unir documentos solo por idioma/proveedor.

- [ ] Comprobar igualdad original/normalizada y similitud según perfil versionado explícito; conflictos no resueltos impiden acreditar independencia.

- [ ] Variantes OCR/de formato no cruzan particiones; no usar semillas o hashes diferentes como prueba suficiente.

- [ ] Exposición desconocida o histórica se declara; casos ya inspeccionados permanecen en known_regression o external_transfer.

- [ ] La auditoría produce conteos y motivos seguros, no contenido de gold ciego.

## Pruebas y evidencia exigidas

- [ ] Duplicado exacto, NFKC/casefold/espacios equivalente, derivado OCR y plantilla compartida entre particiones se detectan.

- [ ] Perfil de similitud ausente/conflicto pendiente no obtiene independencia acreditada.

- [ ] Nombres comunes sin identidad vinculada no fusionan todo el corpus; fuente previamente usada no se presenta como ciega.

## Trazabilidad

AC-01, AC-14 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
