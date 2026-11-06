# H1/H2: normalización Unicode y compatibilidad léxica

**La regresión de MEDDOCAN está corregida en la candidata.** La validación
sintética y MEDDOCAN dev conservan los mismos tipos y coordenadas de predicción
que master, tanto por reglas como con el paquete general. Gretel sigue sin
medirse por falta de acceso a sus activos. **Auditoría Claude: hallazgos A1–A5 corregidos (ver «Cierre»).**

Base master: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.
Código probado/revisado: `3de9d732dca9a6df106a757836f0c8194be73916`.
Rama: `fix/unicode-detection`; los cambios posteriores son documentación, recibos y un reproductor clínico
ejecutado por separado.
[Validación actual](validation.json) · [salud local](health.json) ·
[cuerpo de PR](PR_BODY.md).

## Qué cambió

La vista común retira todos los Cf y aplica NFKC con mapa de offsets al original.
La tokenización, los segmentos, las comprobaciones de sustituciones y los
intervalos del NLP utilizan esa vista. La salida conserva el original fuera de
los intervalos transformados, incluidas sus formas Unicode.

NFKC convierte los ordinales º/ª en o/a y elimina distinciones léxicas necesarias
para reglas y modelos ya entrenados. Ahora la procedencia conserva la clase de
ordinal como **metadato para características léxicas y validación de límites**;
la vista NFKC permanece intacta y no se reintroducen Cf ni letras de ancho
completo. No se cambiaron pesos, umbrales, perfiles, modelos ni defaults.

El modelo calcula sus características con esa evidencia, manteniendo los tokens
y coordenadas NFKC. DomainModelAdapter conserva la misma información al refinar
límites. DomainRouter, CombinedNER y CachedTagger la propagan; el caché no
confunde el ordinal 5º con el literal 5o. Los adaptadores externos sin esta
capacidad siguen recibiendo texto NFKC mediante `detect_batch`.

La validación de nombres distingue el marcador original Nº del apellido literal
No; también conserva el reconocimiento de abreviaturas personales como Mª.
Esto evita consumir un marcador de número como otro apellido. La relectura de
archivos y el streaming conservan revisión ante Cf residuales dentro de palabras,
sin inventar entidades sensibles.

## Evidencia de validación

Las mediciones finales usan el mismo helper, corpus, anotaciones, modelos y
configuraciones en base y candidata. Se comprobó igualdad del hash de **todas
las predicciones tipadas con sus offsets**, además de las métricas exigidas.
No se eligieron subconjuntos favorables ni se modificó el gold.

| Validación | Configuración | FP base → candidata | Recall de caracteres | Documentos sin cubrir |
| --- | --- | ---: | ---: | ---: |
| Sintética, 600 | Reglas | 268 → 268 | 0.428915 → 0.428915 | 600 → 600 |
| Sintética, 600 | General balanced | 1090 → 1090 | 0.928963 → 0.928963 | 273 → 273 |
| MEDDOCAN dev, 250 | Reglas | 776 → 776 | 0.587256 → 0.587256 | 250 → 250 |
| MEDDOCAN dev, 250 | General balanced | 2066 → 2066 | 0.972887 → 0.972887 | 97 → 97 |
| MEDDOCAN dev, 250 | Clínico balanced | 2030 → 2030 | 0.978497 → 0.978497 | 79 → 79 |
| MEDDOCAN dev, 250 | builtin:auto balanced | 974 → 974 | 0.973164 → 0.973164 | 94 → 94 |

Clínico y auto se comprobaron adicionalmente mediante el reproductor publicado;
sus posiciones marcadas como inciertas por score < 0.75 también coinciden.
Los hashes de scores, confianza y contexto se conservan por separado, junto al
ECE observado: no se recalibraron perfiles. Las filas principales comparan las
métricas de aceptación; no afirman identidad de cada campo de confianza.

El intento anterior tenía FP general 2090 y 99 documentos sin cubrir en MEDDOCAN.
Se conservan íntegros sus [recibos de validación](history/93ed28c-validation.json)
y [salud local](history/93ed28c-health.json), ligados al código anterior. No se
presentan como mediciones del código corregido.

Cada invocación de validación realiza una pasada de puntuación por configuración
sin warm-up. Se repitió validación durante las correcciones y al comprobar el
reproductor en su ruta publicada; ningún banco de test/independiente fue puntuado.
Las pruebas pytest y sus ejemplos de entrenamiento son fixtures de software y
regresión ficticia de desarrollo, no evidencia independiente de adopción.

MEDDOCAN se adquirió de su registro fijado, CC-BY-4.0, fuera del checkout. Solo dev
se parseó/puntuó; la integridad del archivo publicado se verificó por hashes.
Gretel acepta únicamente el archivo Spanish train de la revisión registrada,
verifica su SHA antes/después de cargar y selecciona el holdout determinista
10%, salt deidflow. La partición de entrenamiento interna y el test publicado
quedan fuera de puntuación. Su ejecución real sigue pendiente, sin resultados
fabricados. Las coincidencias de identidad/plantilla no se acreditan con ese hash.

## Pruebas, TDD y empaquetado

**1227 pruebas pasan, 11 omitidas**, 237.84 s. Cobertura: **86.61% sentencias,
78.60% ramas, 84.21% combinada**. Las omisiones son activos opcionales OCR/spaCy
ausentes; no se cuentan como aprobadas. Ruff, formato, mypy Python 3.12, pip check,
microbenchmark, build, twine --strict y wheel base sin extras pasan.

Pruebas rojas/verdes reproducen DNI con Cf, NLP que perdía el piso, Nº consumido
como apellido, wrappers que perdían metadatos y alias de caché. La matriz de
texto, CSV/TSV, JSON/JSONL, DOCX/XLSX, HTML y EML verifica los seis Cf pedidos,
anchura completa, entidades HTML, canales OOXML y adjuntos. El caso de 200.000
Cf dentro de un identificador supera 200 KB UTF-8 y cumple su presupuesto.
ODT/ODS se añadirán cuando su PR llegue a master.

El wheel se construyó desde git archive del código probado y se instaló sin red
ni extras en un venv vacío, fuera del checkout. Se verificaron la API anterior,
modelos empaquetados, retirada de Cf/anchura completa, revisión residual y
cobertura del piso con NLP puro Python. No se publicó en PyPI.

## Reproducción

Usar un worktree limpio en la base y otro en el código probado. El helper de
la candidata debe ser el mismo en ambos comandos, con dependencias ya instaladas:

```sh
PYTHONPATH=/ruta/base/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/base --label baseline --source meddocan \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/base-meddocan.json
PYTHONPATH=/ruta/candidata/src python /ruta/candidata/scripts/validate_unicode_detection.py \
  --source-root /ruta/candidata --label candidate --source meddocan \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/candidate-meddocan.json
```

Para sintético: sustituir --source meddocan por --source synthetic y omitir
--corpus. Para Gretel: --source gretel y --corpus apuntando al Spanish train
registrado; se rechazan test, SHA distinto, datos dentro de Git y sobrescrituras.

[Reproductor clínico/auto](verify_clinical_routes.py), ejecutado en ambos runtimes:

```sh
PYTHONPATH=/ruta/base/src python /ruta/handoff/verify_clinical_routes.py \
  --source-root /ruta/base --helper /ruta/candidata/scripts/validate_unicode_detection.py \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/routes-base.json
PYTHONPATH=/ruta/candidata/src python /ruta/handoff/verify_clinical_routes.py \
  --source-root /ruta/candidata --helper /ruta/candidata/scripts/validate_unicode_detection.py \
  --corpus /ruta/meddocan-registrado --output /ruta/nueva/routes-candidate.json
```

Los recibos incluyen pins de código, helper, datos, configuración y modelos,
sin valores, textos o coordenadas individuales de los documentos.

## Auditoría y bloqueos externos

Revisión interna Matt Pocock: Standards sin infracciones escritas; se acepta un
juicio P3 sobre las listas paralelas source/view del protocolo por lotes, con
validación de cardinalidad en cada frontera. Spec sin defectos de código
pendientes; la evidencia de Gretel y los requisitos externos continúan pendientes.
Esta revisión interna no sustituye la auditoría de Claude.

No hay PR creado: el intento de GitHub API devolvió Forbidden. La rama y el
cuerpo preparado están publicados. No se fusionará hasta CI 11/11, ningún
hallazgo bloqueante de Claude, todos los hilos resueltos y aprobación de Giovanny.
La aceptación completa de las tres fuentes exige todavía Gretel.

Se guardó en el borrador de nube el acceso a huggingface.co conservando
api.github.com. Solo cambió ese borrador: las reglas no están aplicadas al runtime.
El producto requiere revisar, guardar y publicar el entorno desde ajustes para
activar la configuración. No se agregaron credenciales, instalaciones ni
repositorios a ese borrador y no se eludió la política de red.

El resto del plan conserva su orden y sus PRs separados. No se modificaron #32,
hilos de #31, defaults pendientes, ramas ajenas ni la versión del paquete.
Logs locales: /tmp/deidflow-unicode-evidence/continuation/.

## Cierre (Claude Code)

La auditoría de `9402452`/`d05f807` encontró cinco hallazgos; esta rama los corrige:

| Hallazgo | Corrección | Evidencia |
|---|---|---|
| A1 invisibles no Cf (CGJ, selectores de variación, rellenos Hangul, mongol, jemer) | Vista y señal de revisión usan `Default_Ignorable_Code_Point` además de `Cf` | `tests/test_unicode_hardening.py` (9 caracteres × DNI, correo y teléfono) |
| A2 regresión de MEDDOCAN | Ya resuelta por `3de9d73` (procedencia ordinal) | Hallazgos idénticos a master, abajo |
| A3 excepción con más de 1M de caracteres | Vista por palabras: solo se trazan palabras que cambian; las sustituciones 1:1 no reservan mapas | 1,2M caracteres con `º` y NBSP: `APPROVED` |
| A4 coste | Igual que A3; el texto sin cambios no se recorre en Python | 66k caracteres: 0,094 s frente a 0,090 s de master; 400k invisibles: 0,15 s frente a 0,37 s |
| A5 homoglifos griegos y cirílicos | Plegado a latín solo en palabras con letras o dígitos ASCII, solo en la vista | `12345678Ζ`, `аna@…` sustituidos; «5α-reductasa» intacto |

**Validación** (sin conjuntos de test). Comparación hallazgo por hallazgo con `master` `44d04b1`:
- **Paquete general balanced:** 0 documentos con diferencias en MEDDOCAN dev (250) y en el holdout de Gretel (402).
- **Ruta `builtin:auto` con reglas:**

  | Corpus | F1 | Recall de caracteres | Documentos sin cubrir |
  |---|---|---|---|
  | MEDDOCAN dev | 0,8964 | 0,9732 | 94 |
  | Gretel | 0,6447 | 0,8301 | 174 |
  | Sintético 600 | 0,7930 | 0,9087 | 338 |

  Las tres cifras son idénticas a master.

**Comprobaciones:** 1257 pruebas pasan, 11 omitidas. Ruff, formato, mypy y microbenchmark (ratio 1,01) OK.
