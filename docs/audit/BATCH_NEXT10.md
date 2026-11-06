# Integración incremental del benchmark: siguientes diez tareas

Base del lote: `69942cc8fe6e9fae9130ab2bdb8fb703991eb03c`.
Objetivo solicitado: diez tareas una por una, TDD, revisión Matt Pocock y
salud del repositorio, sin datos personales reales ni nuevas dependencias de
producción, manteniendo API y privacidad, sin publicar PyPI.

Orden confirmado por el solicitante: BMX-03 a BMX-12, una por una.
Se respeta el grafo; BMX-09 es una decisión humana y BMX-10/11/12 dependen de
esa ratificación. La consulta sobre D1–D3 y formatos está pendiente; seleccionar
el bloque numérico no se registra como aprobación de esos perfiles. El solicitante
eligió todos los formatos previstos, incluido OCR, y pidió ajustar D1–D3 antes
de ratificarlos; está pendiente su definición concreta.

Salud inicial: Ruff y formato pasan (229 archivos), mypy pasa (68 módulos),
pip check pasa y 142 pruebas focalizadas pasan. El último candidato base tenía
1219 pruebas aprobadas y 11 omisiones OCR/spaCy, documentadas en BMX-02.

Se registrarán checks focalizados y revisión por tarea antes de continuar.
La suite completa con cobertura, el microbenchmark y el wheel se comprobarán
sobre el candidato final integrado. Se conservan sin incluir en los commits
los cambios previos de AGENTS.md, CLAUDE.md y docs/agents/.

| Tarea | Estado del lote |
| --- | --- |
| BMX-03 | Implementada y revisada; 151 pruebas focalizadas pasan |
| BMX-04 | Implementada y revisada; 177 pruebas focalizadas pasan |
| BMX-05 | Implementada y revisada; 197 pruebas focalizadas pasan, 1 juicio P3 aceptado |
| BMX-06 | Implementada y revisada; 214 pruebas focalizadas pasan |
| BMX-07 | Pendiente |
| BMX-08 | Pendiente |
| BMX-09 | Decisiones humanas consultadas; pendientes |
| BMX-10 | Pendiente; depende de BMX-09 |
| BMX-11 | Pendiente; depende de BMX-09 |
| BMX-12 | Pendiente; depende de BMX-10/11 |
