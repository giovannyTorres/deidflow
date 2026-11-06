# Evidencia de BMX-01

Estado: implementación terminada; aceptación integrada y revisión en curso.
Fecha: 2026-11-06. Entorno local: Linux, Python 3.12.14.

Ticket: [BMX-01](../tickets/benchmark-mx/01-primer-recorrido-local.md).
Contrato y reproducción: [primer recorrido EMAIL](../BENCHMARK_MX_EMAIL.md).
Especificación: DF-EVAL-MX v0.1.0, SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.

Base fija de implementación/revisión:
`9d8bbafa9f422ba1b85a3d1ebeb9cbf616fa246c`.
El incremento es aditivo: módulo de evaluación, pruebas, paquete ficticio y
documentación. No modifica API existente, detectores, políticas, transformación,
dependencias de producción ni versión. Los cambios previos a instrucciones de
agentes se conservan fuera del commit del ticket.

## TDD observado

Se ejercitó la interfaz pública paquete/candidato/perfil → informe con el
detector real. Cada ciclo añadió primero el comportamiento y observó el fallo.
Los fallos se corrigieron antes de continuar; no se cambiaron los detectores
para mejorar resultados. Los recuentos corresponden a la prueba del incremento.

| Ciclo | Comportamiento | Rojo | Verde |
| --- | --- | --- | --- |
| 1 | Paquete positivo/negativo → informe descriptivo | 1 fallo: módulo inexistente | 1 pasa |
| 2 | Preservar destino existente sin exponer su nombre | 1 fallo, 1 pasa | 2 pasan |
| 3 | Rechazar entrada ilegible, metadatos no admitidos e intervalos inválidos | 3 fallos, 3 pasan | 6 pasan |
| 4 | Sanitizar errores del destino | 1 fallo, 6 pasan | 7 pasan |
| 5 | Sanitizar fallo de lectura al identificar el candidato | 1 fallo, 14 pasan | 15 pasan |
| 6 | Sanitizar destino demasiado largo y paquete con enlace circular | 2 fallos, 15 pasan | 17 pasan |
| 7 | Rechazar claves JSON repetidas y manifiesto no UTF-8 | 4 fallos, 17 pasan | 21 pasan |

La refactorización separó admisión, identificación y escritura del informe y
concentró la creación de paquetes en las pruebas. Después de las correcciones
de revisión, **21 pruebas pasan**.
Las verificaciones adicionales que ya pasaron al escribirse no se presentan
como ciclos rojos: matching exacto, repetición sin red, canarios, denominadores
ausentes, configuración no admitida y el ejemplo distribuido.

Los logs locales por ciclo están en `/tmp/deidflow-bmx01/tdd-0N-red.log` y
`tdd-0N-green.log`. No se adjuntan trazas de fallos con rutas/canarios al informe
compartible. La prueba final puede reproducirse con:

```sh
.venv/bin/python -m pytest -q tests/test_email_benchmark.py
```

## Métricas y aceptación integrada

Pendiente de registrar la ejecución integrada final, el microbenchmark y el
smoke test del wheel. Las comprobaciones estáticas preliminares ya pasan:
Ruff, formato (222 archivos) y mypy (65 módulos).

El ejemplo contiene dos documentos ficticios, uno positivo y uno negativo.
Resultado observado en las pruebas: TP=1, FP=0, FN=0, soporte=1;
precision=recall=F1=1.0. Calidad: `DESCRIPTIVE_ONLY`. No es una estimación de
calidad poblacional ni garantía de anonimato.

## Revisión Matt Pocock

Dos revisores independientes, con contexto fresco, compararon la base fija con
`fc32b301a1b1fcba16a3bbe61e56e4db96d2941e`. Pendiente su comprobación de las
correcciones siguientes; no se mezclan los ejes.

### Standards

Dos hallazgos documentados P2: la comprobación inicial del destino podía exponer
una ruta demasiado larga; el parser aceptaba claves JSON duplicadas y descartaba
contenido. Peor problema de este eje: exposición de rutas en excepciones.
No se identificaron smells Fowler sustantivos.

Resolución: se eliminó la consulta duplicada al destino y se utiliza la creación
exclusiva con errores sanitizados. El parser rechaza claves repetidas en todos
los niveles y constantes no finitas. Regresiones observadas rojas y verdes.

### Spec

Un hallazgo: la sanitización prometida era incompleta para enlaces circulares de
entrada y rutas de salida demasiado largas. No se encontraron otros requisitos
faltantes ni ampliación del alcance. Peor problema de este eje: nombres
originales expuestos mediante excepciones.

Resolución: errores de resolución de enlaces se convierten en diagnóstico
genérico de paquete inválido; el destino usa la frontera de escritura sanitizada.
Dos regresiones observadas rojas y verdes.

Recuento inicial: Standards 2; Spec 1. No se escoge un peor problema global.

## Riesgos y trabajo posterior

- Solo EMAIL en texto y regresión sintética conocida; transformación y datos
  residuales no evaluados. Los demás tickets permanecen sin implementar.
- El formato mínimo no constituye la admisión completa de BMX-02.
- Sin perfil ratificado, independencia acreditada ni aislamiento nativo. La
  prueba bloquea DNS/conexiones Python; no certifica una sandbox del proceso.
- No se publican datos personales reales, modelos ni nueva versión en PyPI.
- GitHub Issues sigue sin acceso API verificado; BMX-01 es un identificador
  documental, no se inventa número ni cierre remoto de issue.
