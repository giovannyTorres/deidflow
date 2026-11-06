<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-24 -->
# BMX-24: Informar soporte, intervalos por grupo y límites de riesgo residual

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** tarea técnica. **Etiqueta propuesta:** `ready-for-agent`; no aplicada.

**Bloqueado por:** BMX-06, BMX-08.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Una sesión de trabajo con contexto fresco; dividir si excede el alcance acotado.

## Qué entrega

Añadir agregación estadística reproducible que respete grupos y denominadores, incluida la incertidumbre cuando no se observan fugas o falta verificación.

## Criterios de aceptación

- [ ] Remuestreo por grupos con método, nivel, réplicas y semilla explícitos; no tratar variantes como independientes.

- [ ] Publicar soporte y conteos; pesos predefinidos separados de conteos no ponderados.

- [ ] Con cero fugas no usar bootstrap degenerado como prueba de riesgo cero; límite conservador solo bajo hipótesis documentadas.

- [ ] Para N emitidos, L con fuga y U no verificados sin fuga confirmada, informar L/N y (L+U)/N como límites empíricos separados del intervalo estadístico.

## Pruebas y evidencia exigidas

- [ ] Repetir semilla/perfil y comparar resultados; duplicar variantes no multiplica el número de grupos.

- [ ] N=0, cero fugas con n independiente y supuesto no defendible dan resultados/razones esperados.

- [ ] Ejemplo N=10,L=1,U=2 produce límites empíricos 0.1 y 0.3; verificar también subconjunto aprobado.

## Trazabilidad

AC-09, AC-10, AC-12 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
