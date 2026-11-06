<!-- deidflow-benchmark:DF-EVAL-MX:0.1.0:BMX-25 -->
# BMX-25: Ratificar calidad, soporte y custodia antes de abrir el test

**Destino:** GitHub Issues de `giovannyTorres/deidflow`.

**Estado de publicación:** borrador; no existe número/URL de issue verificado.

**Tipo:** decisión/revisión humana. **Etiqueta propuesta:** `ready-for-human`; no aplicada.

**Bloqueado por:** BMX-09, BMX-24.

Los IDs BMX son referencias locales, no números de GitHub. Al publicar, enlazar los bloqueos nativos o sustituirlos por números reales.

**Fuente:** DF-EVAL-MX v0.1.0. No hay issue padre publicado identificado.

**SHA-256 de la especificación:** `898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

**Alcance estimado:** Revisión humana; depende de insumos.

## Qué entrega

Fijar el perfil de calidad y la gobernanza del banco independiente antes de conocer sus resultados, sin fabricar porcentajes de aprobación profesional.

## Criterios de aceptación

- [ ] Acordar mínimos de soporte, métricas/estratos obligatorios, umbrales/dirección, incertidumbre, conservación y carga de revisión.

- [ ] Resolver protocolo de similitud y sus parámetros antes del test, además del perfil estadístico propuesto.

- [ ] Acordar responsable de custodia, restricciones de acceso, congelamiento, exposición y política de publicación/renovación.

- [ ] Registrar decisiones y hashes; sin ratificación conservar DESCRIPTIVE_ONLY y no declarar resueltas las preguntas previas.

## Pruebas y evidencia exigidas

- [ ] Revisión documental usando resultados de desarrollo/regresión, nunca del banco ciego aún sin abrir.

- [ ] Escenario de recall alto con fuga inaceptable no puede compensarse con F1 agregado.

- [ ] Escenarios de soporte insuficiente, ausencia de aprobados y publicación de gold tienen una decisión previa explícita.

## Trazabilidad

AC-13, AC-14 de DF-EVAL-MX v0.1.0.

## Restricciones y fuera de alcance

- Esta creación de tareas no inicia la implementación.
- El trabajo futuro se limita al sistema de evaluación; no corregir detectores, políticas ni transformadores de producción para hacer pasar el benchmark.
- Solo datos ficticios o fuentes públicas no personales con permisos comprobados; nunca documentos personales reales ni envío a servicios externos.
- Evaluación local, sin descargas/inferencia/telemetría remotas ni dependencias obligatorias nuevas. Cualquier adquisición o publicación requiere autorización de su tarea.
- No fabricar ratificación, gold, revisores, activos, independencia o resultados; los casos expuestos permanecen como regresión conocida.
- Aplicar las instrucciones vigentes del repositorio y conservar trabajo concurrente.

## Cierre

Cerrar solo con criterios y pruebas satisfechos, adjuntando evidencia sanitizada. Un requisito externo pendiente mantiene la tarea abierta; una omisión no se cuenta como prueba aprobada.
