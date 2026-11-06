# BMX-03: detección por entidad

Estado: implementada y revisada; verificación integrada final pendiente del lote.
Base: `69942cc8fe6e9fae9130ab2bdb8fb703991eb03c`.
Ticket: [BMX-03](../tickets/benchmark-mx/03-deteccion-por-entidad.md).
Seam: paquete/candidato/perfil → informe, usando el mismo recorrido de BMX-02.

TDD observado: 1 fallo → verde para categorías y conteos; 2 fallos → verde para
referencia parcial/ambigua; 1 fallo → verde para soporte tras error del candidato;
2 fallos → verde para razones de macro indefinido. Las verificaciones adicionales
de tipos erróneos y Unicode/CRLF ya pasaron al añadirse.

Revisión: se observó fallo rojo y corrección verde para conservar incertidumbre
ante error del candidato, y para distinguir cobertura parcial de predicción.
Una prueba adicional comprueba reasignación de pares para máxima cardinalidad;
ya pasó al escribirse. Se compartieron fórmulas entre EMAIL y multientidad y se
eliminó el cálculo duplicado que se descartaba.

Comprobación de paso: 9 pruebas nuevas y 142 del recorrido previo pasan
(151 en total). Ruff y mypy pasan (70 módulos). Logs reproducibles en
`/tmp/deidflow-batch/BMX-03/`. Caso controlado TP=FP=FN=1 produce precision,
recall y F1=0.5; el caso real Unicode conserva TP=1 y FN=1 en EMAIL anidado.
Son fixtures conocidos, no estimaciones de calidad poblacional.

## Standards

Revisión inicial: 1 P2 por pérdida de metadatos de incertidumbre tras error del
candidato, y 1 juicio P3 de fórmulas duplicadas. Corregidos y confirmados por el
revisor en `ee4c19c`: 0 pendientes. No se mezcla este eje con Spec.

## Spec

Revisión inicial: 1 P2 por falta de cobertura diagnóstica de spans predichos.
Se añadió unión de caracteres y matching de intersección iterativo uno a uno,
separado del exacto. El revisor confirmó 0 pendientes en `ee4c19c` y verificó
30 976 combinaciones contra un conteo y matching exhaustivos independientes.

Resumen de revisión: Standards 0 pendientes (1 infracción y 1 juicio resueltos),
Spec 0 pendientes (1 resuelto). Sin peor hallazgo vigente en ninguno de los ejes.

La suite completa y el empaquetado se ejecutarán sobre la integración final del
lote; no se afirman resultados futuros. No cambia código de detectores, API
de producción, dependencias ni versión; no ratifica decisiones humanas.
