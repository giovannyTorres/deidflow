# Candidata H1/H2: normalización Unicode

**Estado: candidata de desarrollo; aceptación no cumplida. Auditoría Claude: pendiente.**
No se fusionó ni publicó una versión. La API de GitHub sigue denegada por la
política del entorno: una rama publicada y este cuerpo preparado no son un PR.

Base `master`: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
Código candidato: `93ed28cc4b9ee1c8f0d2b9fb3e919f70df3c7140`.
Rama: `fix/unicode-detection`. [Comparación](https://github.com/giovannyTorres/deidflow/compare/master...fix/unicode-detection).
[Resultados de validación y pins](validation.json). Las comprobaciones integradas
se registran por separado en `health.json` después de completarse.

## Cambio y TDD

La vista compartida retira todos los caracteres de categoría Cf y aplica NFKC
con trazado al original. Descomposición acotada, buckets de clase combinante y
composición de pares evitan normalizar prefijos crecientes. Expansiones,
composición Hangul/Indic y reordenación conservan envolventes originales; la
proyección es constante por hallazgo. No se normaliza el documento emitido.

RuleDetector usa la vista también cuando lo invocan rutas rápidas de columnas y
procesos. El NLP recibe el texto normalizado y sus offsets se validan antes de
proyectar y fusionar. Los escritores siguen transformando intervalos originales.
La relectura/streaming y el texto conservan revisión cuando quedan Cf dentro de
palabras, sin fabricar entidades sensibles. `rules-0.7` impide reutilizar planes
actuales o calibraciones de reglas anteriores; los recibos históricos conservan
su contrato de verificación.

Las primeras pruebas rojas reprodujeron el DNI invisible y un adaptador NLP que
no recibía NFKC. Otra prueba roja demostró APPROVED con un Cf residual en una
palabra no personal. Sus correspondientes verdes están conservados localmente.
Se añadieron pruebas de los seis Cf solicitados, anchura completa, 200.000 Cf
insertados en un identificador (más de 200 KB UTF-8), texto, CSV/TSV, JSON/JSONL,
DOCX/XLSX, HTML y EML. Se inspeccionan partes OOXML, entidades HTML y adjuntos.
ODT/ODS no están en esta base; su matriz se ampliará cuando se integre su PR.

La validación encontró una distinción que NFKC borra: 3ª pasa a 3a. Una primera
corrección de gramática admitía también expresiones ASCII como «3 o más»;
la revisión interna lo reprodujo con tres pruebas rojas. Se restauró la
gramática original y se interpretan los ordinales con su procedencia original,
a las mismas coordenadas de la vista. Esto conserva Pº/Nº y pisos sin convertir
conectores ASCII en ordinales. El corpus sintético recuperó sus métricas previas.

## Validación: resultado bloqueante

Son **particiones de validación**, sin ajustes de pesos, umbrales, modelos,
perfiles o referencia. Cada invocación hace una pasada de puntuación por
configuración, sin warm-up. Se repitió validación después de cambios del helper,
procedencia y gramática; no se ejecutó ningún banco de test/independiente.
Los primeros intentos fallidos quedan como desarrollo local, no como nuevas
mediciones de test. El informe publicado compara el helper congelado y los
mismos textos/anotaciones/configuraciones entre base y candidata final.

| Validación | Configuración | FP exactos base → candidata | Recall de caracteres | Documentos sin cubrir |
| --- | --- | ---: | ---: | ---: |
| Sintética, 600 | Reglas | 268 → 268 | 0.428915 → 0.428915 | 600 → 600 |
| Sintética, 600 | Paquete general balanced | 1090 → 1090 | 0.928963 → 0.928963 | 273 → 273 |
| MEDDOCAN dev, 250 | Reglas | 776 → 777 | 0.587256 → 0.587256 | 250 → 250 |
| MEDDOCAN dev, 250 | Paquete general balanced | 2066 → 2090 | 0.972887 → 0.972624 | 97 → 99 |

Por tanto **no se cumple «sin nuevos falsos positivos» ni la no regresión del
paquete general**. El diagnóstico inicial, anterior al arreglo léxico de ordinales, contrastó el
mapa con normalización stdlib completa y no encontró discrepancias geométricas.
La comparación actual de 93ed28c incluye la validación ordinal adicional y sus
resultados se cuentan por separado. Ese diagnóstico inicial atribuyó la pérdida
de 18 caracteres a
ADDRESS; no se reinterpretó el gold ni se descartaron errores del denominador.
Queda trabajo para compatibilizar reconocedores/modelos con el preprocesamiento;
esta candidata no habilita uso con datos reales ni satisface el cierre de P1.

MEDDOCAN se adquirió del commit/licencia fijados en el registro, fuera del
checkout; solo dev se parseó y puntuó. La verificación de integridad lee bytes
del archivo publicado, incluidos otros splits, sin ejecutarlos como evaluación.
No se publicaron documentos, valores, nombres de archivo de casos ni coordenadas
individuales. Gretel requiere el Spanish train registrado para su holdout hash:
no está disponible aquí y no se sustituyó por el test publicado.

## Reproducción

Usar dos worktrees, uno limpio en la base y otro en el código candidato. Con
las dependencias de desarrollo ya instaladas y sin red durante evaluación:

```sh
PYTHONPATH=/ruta/base/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/base --label baseline --source synthetic --output /ruta/nueva/base-synthetic.json
PYTHONPATH=/ruta/candidata/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/candidata --label candidate --source synthetic --output /ruta/nueva/candidate-synthetic.json
PYTHONPATH=/ruta/base/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/base --label baseline --source meddocan \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/base-meddocan.json
PYTHONPATH=/ruta/candidata/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/candidata --label candidate --source meddocan \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/candidate-meddocan.json
```

El helper rechaza sobrescrituras y selección de test; fija synthetic validation
600/1729 y MEDDOCAN dev. Sus digests de corpus, modelo, configuración y código
permiten comprobar que ambos lados usan las mismas entradas. Los resultados
son evidencia de validación local, no calidad global, anonimato o independencia.

## Revisión y condiciones externas

Revisión interna Matt Pocock a dos ejes, distinta de la auditoría de Claude:
Standards, 0 infracciones/juicios pendientes; Spec, defectos ASCII y Pº resueltos,
con aceptación de validación y condiciones externas todavía pendientes.
Código revisado 93ed28c; cinco comprobaciones independientes de ordinales pasan.

Antes de cualquier fusión siguen siendo obligatorios CI 11/11, ausencia de
hallazgos bloqueantes de Claude, todos los hilos resueltos y aprobación de
Giovanny. Ninguna revisión interna sustituye esas condiciones. No se activó
NarrativeRecognizer, segundo pase de transformación ni un modelo nuevo; se
mantuvieron los defaults de master. No se tocaron #32, hilos de #31, ramas
ajenas, dependencias ni versión del paquete en este incremento.

Los siguientes pasos de P1 siguen abiertos: cerrar esta aceptación, añadir las
dos recetas BMX-12 en su PR correspondiente, corregir HTML H3/H4 y después H5
sobre #32. H3/H4 ya se reprodujeron de forma aislada, sin cambios de código.
No se avanzó a releases, limpieza de ramas ni decisiones pendientes del titular.

Logs locales de la sesión: `/tmp/deidflow-unicode-evidence/`. Los comandos y
resultados finales se adjuntan al cuerpo de PR preparado y al recibo de salud.
