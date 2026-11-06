<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-03 -->
# BMX-03: Puntuar detección mexicana con matching exacto y errores por entidad

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-02.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Evaluar un paquete textual multientidad y publicar filas independientes RFC, CURP, CLABE, tarjetas, teléfonos, correos, personas, direcciones y categorías clínicas declaradas; mantener cobertura parcial como diagnóstico separado.

## Criterios de aceptación

- [ ] Matching de máxima cardinalidad uno a uno con clave caso/unidad/tipo/inicio/fin y desempate canónico.

- [ ] Deduplicar predicciones idénticas sin borrar spans solapados distintos; error de tipo/límite produce los FP/FN correspondientes.

- [ ] Informar TP/FP/FN, precision/recall/F1, soporte, micro/macro y exclusiones explícitas; sin denominador usar null y razón.

- [ ] Conservar offsets Unicode originales y no rescatar errores mediante equivalencias guiadas por el gold.

- [ ] Predicción malformada se registra como error del candidato; no se convierte en resultado perfecto ni desaparece del alcance.

## Pruebas y evidencia exigidas

- [ ] TP=1, FP=1, FN=1 da precision=recall=F1=0.5.

- [ ] Ejemplos exactos, parciales, cruzados, repetidos y de etiqueta errónea; una predicción no acierta dos menciones.

- [ ] Diacríticos, caracteres fuera de BMP y saltos CRLF mantienen índices; categorías sin soporte siguen visibles.

## Trazabilidad

AC-02, AC-03, AC-05 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
