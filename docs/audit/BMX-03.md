# BMX-03: detección por entidad

Estado: implementación verificada con pruebas focalizadas; revisión pendiente.
Base: `69942cc8fe6e9fae9130ab2bdb8fb703991eb03c`.
Ticket: [BMX-03](../tickets/benchmark-mx/03-deteccion-por-entidad.md).
Seam: paquete/candidato/perfil → informe, usando el mismo recorrido de BMX-02.

TDD observado: 1 fallo → verde para categorías y conteos; 2 fallos → verde para
referencia parcial/ambigua; 1 fallo → verde para soporte tras error del candidato;
2 fallos → verde para razones de macro indefinido. Las verificaciones adicionales
de tipos erróneos y Unicode/CRLF ya pasaron al añadirse.

Comprobación de paso: 6 pruebas nuevas y 142 del recorrido previo pasan
(148 en total). Ruff y mypy pasan (69 módulos). Logs reproducibles en
`/tmp/deidflow-batch/BMX-03/`. Caso controlado TP=FP=FN=1 produce precision,
recall y F1=0.5; el caso real Unicode conserva TP=1 y FN=1 en EMAIL anidado.
Son fixtures conocidos, no estimaciones de calidad poblacional.

## Standards

Pendiente revisión independiente de Matt Pocock.

## Spec

Pendiente revisión independiente del ticket y AC-02/AC-03/AC-05.

La suite completa y el empaquetado se ejecutarán sobre la integración final del
lote; no se afirman resultados futuros. No cambia código de detectores, API
de producción, dependencias ni versión; no ratifica decisiones humanas.
