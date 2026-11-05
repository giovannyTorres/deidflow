# Auditoría de métricas y plan a producción

Fecha: 2026-11-05 · Versión auditada: `0.3.0` (commit `68883a5`) · Alcance: detección,
transformación, *release gate*, benchmarks, empaquetado y adecuación al caso de uso
"anonimizar texto en español antes de enviarlo a un LLM sin perder contexto".

> **Veredicto:** DeidFlow tiene una base de ingeniería sólida (tests, validadores
> mexicanos, PDF físico, *fail-closed*), pero **no está lista para producción** en el
> caso de uso objetivo. Hay tres bloqueadores: (1) la detección de texto libre es
> insuficiente: con reglas, el 100 % de los documentos de MEDDOCAN test filtra al menos un
> identificador directo (81 % con el mejor NER genérico). (2) La aprobación (`APPROVED`) es circular: aprueba texto con fugas si el
> mismo detector no las vio. (3) No existe la funcionalidad central que pide el caso de uso:
> marcadores numerados y consistentes (`[PERSONA_1]`) con una bóveda reversible.
> Además, la licencia actual ("todos los derechos reservados") impide que terceros la usen.

---

## 1. Caso de uso objetivo y lo que hace hoy la librería

Entrada (ejemplo del producto):

```text
La señora Verónica Herrera fue diagnosticada por el doctor Jiménez antes de la cita del señor González.
```

Salida esperada para un LLM, sin perder contexto ni relaciones:

```text
La señora [PERSONA_1] fue diagnosticada por el doctor [MEDICO_1] antes de la cita del señor [PERSONA_2].
```

Salida **real** de v0.3.0. La reproduje con `DeidEngine().deidentify_text(...)`:

| Política | Hallazgos | Estado | Salida |
|---|---|---|---|
| `Policy.strict(require_ner=False)` | **0** | **`APPROVED`** | texto original íntegro, con los 3 nombres |
| `Policy.strict()` (por defecto) | 0 | `REVIEW_REQUIRED` (solo porque falta el NER) | texto original íntegro |
| `Policy(default=Rule("pseudonym"))` | 0 | `APPROVED` | texto original íntegro |
| Con abreviaturas (`Sra.`, `Dr.`, `Sr.`) y nombre completo | 1 de 3 | `APPROVED` | `La Sra. [PERSON] … Dr. Jiménez … Sr. González` |
| Con abreviaturas y nombre+apellido en los 3 | 3 | `APPROVED` | `La Sra. [PERSON] … Dr. [PERSON] … Sr. [PERSON]` |

Con seudónimos, la salida es
`[DF_PERSON_JY2FDEHHGWPCFR6JZ7G2YZ4VLSLZSHPU]`. El token es consistente para el mismo
texto exacto, pero es opaco, largo (44 caracteres en base32 aleatoria) y no indica rol.
Tampoco agrupa variantes: `Verónica Herrera`, `la señora Herrera` y `Verónica` reciben
tokens distintos.

Otras pruebas representativas en español de México, con la política solo-reglas:

| Entrada | Resultado |
|---|---|
| `La doctora Ana Ruiz atendió a la Lic. Paola Méndez en el Hospital General de México.` | 0 hallazgos, `APPROVED` |
| `El Ing. Roberto Salinas, NSS 12345678901, trabaja en Pemex en Villahermosa, Tabasco.` | 0 hallazgos, `APPROVED` |
| `Clave de elector GMVLMR80070501M100, INE folio 1234567890123.` | 0 hallazgos, `APPROVED` |
| `Mi número es 5512345678 y mi WhatsApp 33 1234 5678.` | solo el segundo teléfono; `APPROVED` |
| `Vive en Av. Insurgentes Sur 1602, Col. Crédito Constructor, Benito Juárez, 03940 CDMX.` | `Vive en [ADDRESS], Col. Crédito Constructor, Benito Juárez, 03940 CDMX.`: se filtran la colonia, la alcaldía y el CP; `APPROVED` |
| `Verónica tiene VIH y toma metformina; su médico es el Dr. Ramírez del Hospital Ángeles en Guadalajara.` | VIH y metformina sin detectar (no hay disparador "paciente"); el nombre "Ramírez del Hospital Ángeles" se fusiona con el hospital; `Verónica` y `Guadalajara` se filtran; `APPROVED` |
| `Paciente femenina de 52 años con VIH y depresión, tratada en el IMSS de Guadalajara.` | detecta edad y condiciones; filtra institución y ciudad; `APPROVED` |

**Causas raíz en el código:**

- `_HONORIFIC` (`src/deidflow/detectors/__init__.py`) solo reconoce las abreviaturas
  `Sr./Sra./Dr./Dra.`. No reconoce *señor, señora, doctor, doctora, licenciado, Lic., Ing.,
  maestro, don, doña*, etc. Además exige al menos dos palabras de nombre
  (`_NAME_VALUE` usa `{1,5}`), así que un apellido solo ("el Dr. Jiménez") se pierde.
- No existe un detector de lugares, instituciones ni hospitales en reglas. El adaptador
  `SpacyNER` solo mapea `PER/PERSON/LOC/GPE`, así que descarta `ORG` aunque el modelo la prediga.
- La salud se detecta con 13 términos y solo junto a un "sujeto" explícito
  (`_HEALTH_SUBJECT`).
- `transform_text` produce `[TIPO]` sin índice, o un HMAC opaco. No hay correferencia
  (`resolve_exact_mentions` existe, pero no se usa en la transformación), no hay bóveda
  reversible y no hay re-identificación de la respuesta del LLM.
- `_gate` vuelve a escanear la salida **con el mismo detector**. Si el detector no vio
  algo en la entrada, tampoco lo verá en la salida, y el estado será `APPROVED`. La
  verificación es circular para todo lo que el detector no conoce.

---

## 2. Métricas actuales, reproducidas en esta auditoría

### 2.1 Entorno y reproducibilidad

- Linux, Python 3.13.18, 4 vCPU y 15 GB de RAM. Las cifras originales se midieron en Windows,
  Python 3.11.9, Ryzen 7 5700G.
- Suite completa: **359 aprobados, 11 omitidos**. Los omitidos necesitan Tesseract o spaCy
  locales. `ruff check`, `ruff format --check` y `mypy --python-version 3.13` pasan.
  `benchmark_micro.py --check` pasa.
- MEDDOCAN se reconstruyó desde el commit fijado `783a6df` y se verificó contra el hash del
  manifiesto por archivo, `file_digest_manifest_sha256 = ba4823b7…`, con **coincidencia exacta**.
  El hash del ZIP de `codeload.github.com` no es reproducible byte a byte, porque GitHub
  regenera los ZIP. Además, `acquire()` ignora el CA corporativo al forzar `certifi`.
  Ver la recomendación F0.4.
- Las cifras del repositorio se **reproducen exactamente**: reglas P/R/F1 =
  0.6927/0.4022/0.5089; reglas + `es_core_news_sm` = 0.4145/0.5370/0.4679.

### 2.2 MEDDOCAN test (250 documentos, 5,661 menciones humanas)

| Pipeline | P exacta | R exacta | F1 exacta (IC 95 %) | Precisión por solapamiento | Recall de caracteres sensibles | Menciones 100 % cubiertas | Identificadores directos 100 % cubiertos | Docs con fuga de identificador directo | Sobre-redacción | ms/doc* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Reglas v0.3 | 0.693 | 0.402 | 0.509 (0.500–0.518) | 0.923 | 0.538 | 0.459 | 0.650 | **250/250** | 0.2 % | 2 |
| Reglas + `es_core_news_sm` (GPL) | 0.415 | 0.537 | 0.468 | 0.526 | 0.759 | 0.668 | 0.800 | 233/250 | 3.9 % | 49 |
| Reglas + `es_core_news_md` (GPL) | 0.492 | 0.615 | 0.546 (0.540–0.553) | 0.609 | 0.809 | 0.723 | 0.858 | 202/250 | 2.7 % | 54 |
| **Reglas + NER spaCy entrenado en MEDDOCAN-train** (checkpoint intermedio, 1 época)† | 0.734 | 0.888 | 0.804 | 0.780 | — | 0.959 | **0.976** | **43/250** | 0.9 % | 111‡ |
<!-- TRAINED_NER_ROWS -->

\* Latencia medida en esta máquina, en una sola pasada. Es solo orientativa.
† Experimento de esta auditoría (§6). No se distribuye. ‡ Medido mientras el entrenamiento ocupaba un núcleo.

### 2.3 Desglose por tipo (reglas v0.3, MEDDOCAN test)

"Cobertura completa" = fracción de menciones cuyos caracteres quedaron **todos** cubiertos
por alguna predicción, sin importar la categoría. Es la métrica más cercana a "no se filtró".

| Tipo | Menciones gold | % del gold | R exacta | Cobertura completa | Comentario |
|---|---:|---:|---:|---:|---|
| LOCATION (país, provincia, ciudad) | 1,319 | 23 % | 0.000 | 0.002 | No existe detector |
| PERSON | 1,084 | 19 % | 0.329 | 0.383 | Solo campos etiquetados y abreviaturas |
| DATE | 611 | 11 % | 0.838 | 0.838 | Bien |
| AGE | 518 | 9 % | 0.041 | 0.044 | El número se detecta (solapamiento 0.91). El gold incluye "años". Filtrar "años" no identifica a nadie, así que la métrica exacta subestima |
| DEMOGRAPHIC (sexo) | 461 | 8 % | 0.883 | 0.896 | Bien |
| ADDRESS | 413 | 7 % | 0.002 | 0.598 | Los límites cortan la dirección y se filtran fragmentos |
| PATIENT_ID / REGIONAL_ID / INSURANCE_ID / EMAIL | 1,003 | 18 % | 0.94–0.99 | 0.95–0.99 | Bien (identificadores etiquetados) |
| MEDICAL_FACILITY | 136 | 2 % | 0.000 | 0.007 | No existe detector |
| ORGANIZATION | 67 | 1 % | 0.000 | 0.000 | No existe detector |
| PHONE | 33 | 0.6 % | 0.030 | 0.121 | 191 predicciones PHONE con 1.6 % de precisión tipada: se solapan con identificadores (NHC/NASS). No genera fuga, pero sí confusión de tipo |

Con `es_core_news_md`, LOCATION sube a 0.64 de recall por solapamiento y PERSON a 0.78. A cambio,
se generan 2,548 predicciones LOCATION con solo **33 % de precisión tipada**: el modelo
genérico marca términos clínicos como lugares. Eso destruye contexto útil para el LLM.

### 2.4 Otras métricas existentes y cómo leerlas

| Métrica publicada | Valor | Lectura de la auditoría |
|---|---|---|
| Benchmark sintético (159 docs) | F1 95.0 %, recall 99.7 % | **No es representativo.** Usa plantillas propias con pocas variaciones. Diverge 45 puntos de MEDDOCAN. No debe usarse como indicador de calidad. |
| TAB (inglés judicial) | F1 0.0 | Fuera de alcance para una librería en español. Recomiendo retirarlo del tablero principal. |
| CSV 1M filas | 5,397 filas/s, 39 MB RSS | Bien, pero solo con reglas y columnas sintéticas. |
| PDF nativo 100 pág. | 75 s (8 workers), `REVIEW_REQUIRED` | Bien para lotes. No aplica al flujo LLM en tiempo real. |
| Calibración (ECE) | `null` | Sin calibrar. Los umbrales (`review_below = 0.75`) son arbitrarios: toda fecha (score 0.7) envía el documento a revisión. |
| Tasa real de `REVIEW_REQUIRED` | No medida | Hace falta conocerla para dimensionar la revisión humana. |

### 2.5 Problemas metodológicos de las métricas

1. **El indicador principal (F1 exacta) no mide el riesgo.** Para anonimizar importa si
   *algún carácter identificante* llega al LLM (recall de fuga). Para la utilidad importa
   cuánto contexto no sensible se destruye (sobre-redacción). Los límites exactos penalizan
   casos inocuos ("45" frente a "45 años") e ignoran fugas parciales ("Ramírez" cubierto,
   "Hospital Ángeles" no).
2. **Faltan métricas de contexto**, que son el valor del producto: consistencia de
   correferencia (misma persona = mismo marcador), exactitud de rol
   (paciente / médico / familiar), y utilidad del LLM (rendimiento de la tarea sobre texto
   anonimizado frente al original).
3. **No hay un holdout mexicano.** MEDDOCAN es español de España, clínico y con PHI
   sintética. No representa correos, chats de soporte, expedientes del IMSS, contratos ni
   formularios mexicanos.
4. **No hay medición del *release gate*:** falta la tasa de falsos `APPROVED`, es decir,
   documentos aprobados que contienen identificadores según el gold. Hoy es 100 % en el ejemplo del producto.
5. **No hay pruebas adversariales de fuga en texto libre:** espaciado, mayúsculas, errores
   de OCR o dictado ("Verónica él dirigirá"), nombres comunes que también son palabras
   (Rosa, Blanca, León, Paz), nombres indígenas o extranjeros.

---

## 3. Hallazgos priorizados

| # | Severidad | Hallazgo | Evidencia |
|---|---|---|---|
| H1 | Crítica | El texto narrativo con títulos completos o un solo apellido no se detecta y se aprueba | §1, ejemplo del producto |
| H2 | Crítica | Verificación circular: `APPROVED` no aporta evidencia independiente | `engine._gate` vuelve a escanear con el mismo `RuleDetector` |
| H3 | Crítica | No hay marcadores indexados y consistentes, ni bóveda reversible, ni re-identificación de respuestas | `transformations._apply` |
| H4 | Crítica | Recall de LOCATION, MEDICAL_FACILITY y ORGANIZATION ≈ 0 en reglas. El NER genérico tiene 33 % de precisión en LOCATION | §2.3 |
| H5 | Alta | 250/250 documentos de MEDDOCAN filtran al menos un identificador directo con reglas, y 202/250 con el mejor NER genérico | §2.2 |
| H6 | Alta | La licencia "All rights reserved" impide el uso por terceros. Los modelos `es_core_news_*` son GPL-3.0 y no sirven para distribución comercial | `LICENSE`, `docs/third-party-licenses.md` |
| H7 | Alta | Datos de salud: el léxico es mínimo y depende de un disparador. No hay política explícita de *mantener lo clínico y quitar la identidad* | `_HEALTH`, `_HEALTH_SUBJECT` |
| H8 | Media | Puntuaciones sin calibrar y umbral de revisión arbitrario. La tasa de revisión no está medida | §2.4 |
| H9 | Media | Alcance del paquete: Gmail, UI web de anotación y PDF ráster conviven con el núcleo. Aumentan la superficie de ataque y las dependencias de un SDK para LLM | `src/deidflow/private/` |
| H10 | Media | `DeidEngine` solo acepta `country="MX"`, pero la validación pública es de España. No hay paquetes de país (ES, CO, AR, CL, PE…) | `engine.py` |
| H11 | Media | Las fechas solo se desplazan en formato ISO. No hay sustitución consistente de fechas en español ("3 de marzo") que preserve intervalos ("antes de la cita") | `_apply("date_shift")` |
| H12 | Baja | La adquisición del benchmark depende del hash de un ZIP no estable y de `certifi` | §2.1 |
| H13 | Baja | El CI nunca corrió en GitHub (lo indica la documentación). No hay publicación en PyPI ni SBOM firmado | `docs/roadmap.md` |

---

## 4. Objetivos de producción (KPIs y criterios Go/No-Go)

Se miden en **tres conjuntos**: MEDDOCAN test, un holdout mexicano multidominio
anotado (nuevo, ver F3) y una suite de aceptación LLM (nueva, ver F0).

| KPI | Definición | Hoy (reglas / mejor híbrido) | Meta GA |
|---|---|---|---|
| Recall de fuga de identificadores directos | Menciones de PERSON, ID, teléfono, correo y dirección cubiertas al 100 % | 0.650 / 0.858 | **≥ 0.99** |
| Recall de cuasi-identificadores | LOCATION, FACILITY, ORG, DATE, AGE cubiertos al 100 % | 0.20 / 0.56 | ≥ 0.95 |
| Documentos sin fuga directa | % de documentos con 0 caracteres de identificador directo expuestos | 0 % / 19 % | **≥ 95 %** |
| Precisión tipada | Predicciones correctas en tipo, por solapamiento | 0.92 / 0.61 | ≥ 0.90 |
| Sobre-redacción | % de caracteres no sensibles ocultados | 0.2 % / 2.7 % | ≤ 2 % |
| Exactitud de rol en PERSON | paciente / personal sanitario / familiar / otro | no existe | ≥ 0.90 |
| Consistencia de correferencia | Mismo referente = mismo marcador (B³ F1) dentro del documento o sesión | no existe | ≥ 0.95 |
| Round-trip de re-identificación | Marcadores válidos en la respuesta del LLM restaurados correctamente | no existe | 100 % (0 restauraciones de tokens ajenos) |
| Utilidad del LLM | Caída de la métrica de la tarea (extracción, resumen, QA) con texto anonimizado frente al original | no medida | ≤ 3 puntos |
| Falsos `APPROVED` | Documentos aprobados con al menos 1 identificador directo según el gold | 100 % en el ejemplo | ≤ 1 % |
| Tasa de revisión humana | % de `REVIEW_REQUIRED` en el holdout | no medida | ≤ 10 % |
| Latencia | p95 por documento de 1,000 tokens, CPU de 4 núcleos, reglas + NER | 2 ms reglas / 54 ms con spaCy md (media por doc) | ≤ 150 ms |
| Calibración | ECE de la confianza por tipo | `null` | ≤ 0.05 |

**Regla de salida:** todos los KPI de fuga deben cumplirse en *ambos* holdouts, con el
límite inferior del IC 95 % por encima de la meta. Ningún KPI de utilidad puede compensar
un KPI de fuga.

---

## 5. Plan paso a paso

Las fases se solapan parcialmente. Las duraciones suponen un equipo pequeño (2–3 personas).

### Fase 0: Medición correcta (semanas 1–2)

Objetivo: que cada mejora posterior se mida con métricas alineadas al riesgo y al caso LLM.

- **F0.1** Hacer métricas principales el *recall de fuga por cobertura completa* (por tipo
  y por documento), los *falsos `APPROVED`* y la *sobre-redacción*. La F1 exacta pasa a
  ser secundaria. Casi todo ya está calculado en `quality_metrics`; falta exponerlo por tipo y
  agregar "documentos con fuga de identificadores directos".
- **F0.2** Añadir a `public_quality` la **exactitud de rol**: MEDDOCAN ya distingue
  `NOMBRE_SUJETO_ASISTENCIA`, `NOMBRE_PERSONAL_SANITARIO` y `FAMILIARES_SUJETO_ASISTENCIA`,
  pero hoy se colapsan en `PERSON`.
- **F0.3** Crear la **suite de aceptación LLM** (`tests/acceptance_llm/`): unas 200 oraciones
  y párrafos con gold de spans, rol y correferencia, que incluyan el ejemplo del producto, los
  casos de §1, títulos completos, un solo apellido, solo nombre de pila, nombres que también son
  palabras comunes y errores de dictado. Entra en CI como *xfail* hasta que cada fase lo resuelva.
- **F0.4** Hacer la adquisición reproducible: fijar el commit de git y el manifiesto por
  archivo (ya existe) en vez del hash del ZIP, y respetar `SSL_CERT_FILE` / CA del sistema.
- **F0.5** Un job de CI que ejecute MEDDOCAN (corpus en caché) y falle si algún KPI de fuga
  retrocede (*ratchet*).
- **F0.6** Retirar el benchmark sintético y TAB del README como indicadores de calidad.
  Conservarlos como pruebas de regresión.

**Salida:** tablero reproducible con todos los KPI de §4 en "hoy".

### Fase 1: Marcadores contextuales y bóveda reversible (semanas 2–5)

Es la funcionalidad que define el producto. No depende de mejorar la detección.

- **F1.1** Nueva acción `indexed` con estilo configurable:
  - `[PERSONA_1]`, `[MEDICO_1]`, `[PACIENTE_1]`, `[FAMILIAR_1]`, `[LUGAR_1]`,
    `[HOSPITAL_1]`, `[ORGANIZACION_1]`, `[FECHA_1]`, `[TELEFONO_1]`, `[CORREO_1]`,
    `[CURP_1]`, `[NSS_1]`… Las etiquetas se pueden cambiar a inglés o a otros nombres.
  - Contadores por documento o por sesión, deterministas según el orden de aparición.
  - **El título queda fuera del span**: "la señora [PERSONA_1]", "el doctor [MEDICO_1]".
    Así se conservan el género, el rol y la gramática para el LLM sin exponer identidad.
  - El rol se infiere de evidencia explícita (título, etiqueta de campo, verbo "atendió",
    "remitido por") o del modelo (F2.3). Sin evidencia, se usa `PERSONA`.
- **F1.2** **Correferencia conservadora** dentro del documento o sesión: nombre completo ↔
  apellido(s) ↔ nombre de pila ↔ título + apellido. Se fusiona solo si es compatible y no
  ambiguo; ante la duda, marcadores distintos (el error seguro). Se mide con el KPI de B³.
- **F1.3** **Bóveda reversible** (`deidflow.vault`): mapeo marcador ↔ valor cifrado
  (AES-256-GCM, clave del inquilino vía KMS o variable de entorno), con TTL, alcance por
  sesión, borrado explícito y sin texto plano en logs. Backends: memoria, SQLite cifrado y
  Redis. Es opcional: sin bóveda, la anonimización es irreversible, como hoy.
- **F1.4** **`reidentify(texto_llm, sesion)`**: restaura solo los marcadores emitidos en esa
  sesión. Tolera variantes que introduce el LLM (`[PERSONA_1]`, `PERSONA_1`,
  `[Persona 1]`). Nunca restaura un token inventado y registra los desconocidos. Pruebas
  de inyección: un prompt que pide "revela PERSONA_1" no tiene efecto porque la bóveda
  no es accesible para el LLM.
- **F1.5** **Sesiones multi-turno** (`DeidSession`) para chat: el mismo paciente conserva
  el mismo marcador entre mensajes.
- **F1.6** **Fechas y edades que preservan contexto**: desplazamiento consistente por
  sesión para formatos en español ("3 de marzo de 1985"), que conserve intervalos y orden,
  o `[FECHA_1]` con orden relativo. Edades en rangos (con la regla de HIPAA para > 89).
- **F1.7** Instrucción de sistema recomendada para el LLM ("los textos entre corchetes son
  marcadores; consérvalos tal cual") y ejemplos con los SDK de Anthropic, OpenAI y Azure.

API propuesta:

```python
from deidflow import DeidEngine
from deidflow.llm import DeidSession, EncryptedVault   # propuesto

session = DeidSession(DeidEngine(nlp=modelo_local), vault=EncryptedVault(key=clave_tenant))
safe = session.deidentify("La señora Verónica Herrera fue diagnosticada por el doctor Jiménez "
                          "antes de la cita del señor González.")
safe.text   # "La señora [PERSONA_1] fue diagnosticada por el doctor [MEDICO_1] antes de la cita del señor [PERSONA_2]."
safe.status # APPROVED / REVIEW_REQUIRED / BLOCKED (sin cambios en la semántica fail-closed)
respuesta = llm(safe.text)
session.reidentify(respuesta)  # restaura solo marcadores de esta sesión
```

**Salida:** el ejemplo del producto produce exactamente la salida esperada (con la detección de
F2.1). Round-trip 100 % en la suite. Consistencia ≥ 0.95 en la suite.

### Fase 2: Cerrar las brechas de detección (semanas 3–9)

- **F2.1 Reglas rápidas (1–2 semanas, alto impacto en la suite LLM):**
  - Títulos y tratamientos completos y abreviados: *señor/a, Sr/a., don, doña, doctor/a,
    Dr/a., licenciado/a, Lic., ingeniero/a, Ing., maestro/a, Mtro/a., profesor/a,
    enfermero/a, arquitecto/a, C.P.*, seguidos de **uno o más** nombres o apellidos.
    El título se excluye del span.
  - Nombre de pila después de "llamado/a", "de nombre", "mi nombre es", "soy".
  - Gazetteers (con licencia compatible): 32 entidades federativas, municipios y
    localidades del catálogo INEGI; provincias y comunidades de España; países. Instituciones
    de salud: IMSS, ISSSTE, Pemex, Sedena, Cruz Roja, Hospital|Clínica|Centro de Salud|Sanatorio +
    nombre propio.
  - Identificadores mexicanos que faltan: **NSS IMSS** (11 dígitos con dígito verificador),
    **clave de elector INE** (18 caracteres), **CIC/OCR** de la INE, cédula profesional,
    pasaporte, placas vehiculares, **CP** de 5 dígitos con contexto, teléfonos de 10 dígitos
    sin separadores con contexto ("número", "cel").
  - Direcciones: extender el span a colonia, alcaldía o municipio, CP y ciudad
    (hoy se filtran estos fragmentos).
  - DOB: "nació el …". Corregir que la fecha de nacimiento se tipifica como `DATE`.
  - En `SpacyNER`, mapear `ORG` → `ORGANIZATION` y `MISC` como candidato opcional.
- **F2.2 Modelo NER de dominio, con licencia comercial:**
  - Entrenar un clasificador de tokens con MEDDOCAN-train (CC-BY-4.0), datos sintéticos
    mexicanos (plantillas y generación con LLM, solo para entrenamiento) y el corpus
    mexicano anotado de F3.
  - Primer paso, barato: spaCy CNN. Esta auditoría lo midió (ver §6): tras una sola época, la cobertura completa de identificadores directos pasa de 0.650 a 0.976 y los documentos con fuga directa bajan de 250 a 43. <!-- TRAINED_NER_INLINE -->
  - Paso de producción: un encoder *transformer* en español (familia RoBERTa-BNE / BETO /
    mDeBERTa, verificando la licencia de cada checkpoint), exportado a **ONNX int8** para CPU.
    La literatura de MEDDOCAN reporta F1 > 0.95 con este tipo de modelos.
  - **No usar modelos GPL** (`es_core_news_*`) en la distribución.
- **F2.3 Etiquetas de rol** en el mismo modelo: paciente, personal sanitario, familiar,
  otro. Alimentan F1.1.
- **F2.4 Fusión orientada a recall:** unión de reglas validadas, NER y gazetteers;
  normalización de límites (edad + "años", dirección completa); resolución de conflictos de
  tipo (teléfono frente a NHC).
- **F2.5 Datos de salud y categorías especiales:** detector de condiciones sensibles
  (VIH, salud mental, adicciones, salud reproductiva, orientación sexual, religión,
  origen étnico) que no dependa de un disparador. Política explícita por dominio: en el caso LLM
  clínico se *mantiene* el contenido clínico y se quita la identidad. Para casos de
  RR. HH., seguros o legal se puede *generalizar* ("[CONDICION_SENSIBLE]").
- **F2.6 Paquetes de país:** `es_MX` (prioridad) y `es_ES`. Más adelante `es_CO`, `es_AR`,
  `es_CL` y `es_PE`, con validadores propios (DNI/NIE ya existen, CC colombiana, RUT
  chileno, CUIT argentino…).

**Salida:** en MEDDOCAN test, recall de fuga directa ≥ 0.97, cuasi ≥ 0.90 y precisión
tipada ≥ 0.85. En la suite LLM, 0 fallos en identificadores directos.

### Fase 3: Datos de evaluación mexicanos y calibración (semanas 5–10)

- **F3.1** Corpus mexicano multidominio con licencia o consentimiento: notas clínicas,
  reclamaciones de seguros, RR. HH., contratos, correos y chats de atención a clientes.
  Unos 600 documentos de evaluación y unos 1,500 de entrenamiento, separados **por fuente y
  proveedor** (el holdout no comparte plantillas).
- **F3.2** Guía de anotación pública (basada en la de MEDDOCAN, adaptada a México), doble
  anotación, acuerdo κ ≥ 0.80 y adjudicación. Las herramientas locales de anotación del repo
  (`private/annotation.py`) sirven para esto.
- **F3.3** Calibración isotónica por tipo y detector. Umbrales elegidos para cumplir las
  metas de recall. Medición de la tasa real de `REVIEW_REQUIRED`.
- **F3.4** Pruebas de equidad: recall por origen del nombre (hispano, indígena, extranjero) y
  por género. Ninguna brecha mayor de 3 puntos.

### Fase 4: Verificación independiente y seguridad (semanas 8–12)

- **F4.1** **Romper la circularidad del gate:** un verificador independiente (otro modelo
  u otra semilla, gazetteers, más un detector de "nombres propios residuales" por
  mayúsculas/POS) que reescanea la salida. Los desacuerdos van a `REVIEW_REQUIRED`.
  Medir los falsos `APPROVED`.
- **F4.2** **Canarios:** inyectar valores sintéticos conocidos en producción (modo sombra) y
  verificar que nunca aparecen en lo que se envía al LLM.
- **F4.3** **Ataque de re-identificación con LLM** como prueba de *red team*: pedir a un LLM
  que adivine identidades u hospitales a partir del texto anonimizado del holdout.
  Medir la tasa de acierto, que debe estar cerca del azar.
- **F4.4** Pruebas adversariales: espaciado, homoglifos, mayúsculas, OCR, dictado,
  nombres partidos entre líneas, texto mezclado con inglés.
- **F4.5** Revisión de seguridad de la bóveda (gestión de claves, rotación, borrado, logs sin
  PII) y un pentest externo.

### Fase 5: Ingeniería de producto (semanas 6–14, en paralelo)

- **F5.1** **Licencia:** decidir Apache-2.0, MIT o un esquema dual (núcleo abierto y
  modelos o soporte comerciales). Sin esto no hay producción para terceros.
- **F5.2** **Separar paquetes:** `deidflow` (núcleo: texto, tablas, LLM, bóveda),
  `deidflow-pdf` (PDF y OCR), `deidflow-models` (pesos ONNX con licencia comercial) y
  `deidflow-tools` (Gmail y anotación, fuera del SDK).
- **F5.3** **API estable** con semver, documentación en español y ejemplos de integración
  (LangChain, LlamaIndex, SDK directos), además de un microservicio REST o gRPC en Docker
  (*gateway* de anonimización delante del LLM).
- **F5.4** Observabilidad sin PII: métricas de tipos detectados, tasa de revisión, latencia y
  marcadores desconocidos en respuestas.
- **F5.5** CI remoto real (GitHub Actions ya configurado), PyPI con *trusted publishing*,
  SBOM, firma (Sigstore) y lockfiles por sistema operativo.
- **F5.6** Mapeo normativo, sin prometer certificación: LFPDPPP (México, incluida la nueva
  ley de 2025) y sus datos sensibles, NOM-024-SSA3-2012 (expediente clínico electrónico),
  RGPD/LOPDGDD (España) e identificadores de HIPAA *Safe Harbor* como lista de control.
  Documentar la diferencia entre *seudonimización* (reversible, sigue siendo dato personal) y
  *anonimización*.

### Fase 6: Piloto y salida a producción (semanas 12–16)

- **F6.1** Piloto en **modo sombra** con 1–2 clientes: anonimizar sin enviar, revisar una
  muestra humana estratificada y medir los KPI de §4 con datos reales.
- **F6.2** Piloto activo con revisión obligatoria de `REVIEW_REQUIRED`, más un proceso de
  incidentes (fuga detectada, reentrenamiento y regresión).
- **F6.3** **GA** cuando se cumplan todos los criterios de §4 en ambos holdouts y en el piloto,
  con la licencia publicada y la revisión de seguridad cerrada.

---

## 6. Evidencia: techo alcanzable con un NER de dominio

Para estimar el impacto de F2.2 sin especular, entrené en esta auditoría un modelo
spaCy CNN (vectores estáticos de `es_core_news_md`) **solo con MEDDOCAN-train**. Usé
MEDDOCAN-dev para la parada temprana y evalué una sola vez en MEDDOCAN-test, sin tocar el
umbral. Los pesos no se distribuyen: los vectores base son GPL, así que esto es solo un
experimento.

Resultado del checkpoint intermedio (1 época, dev F1 = 0.890 sobre las 21 etiquetas finas de
MEDDOCAN), combinado con las reglas actuales:

| Tipo | Gold | Cobertura completa: reglas | Cobertura completa: reglas + NER entrenado | Precisión tipada |
|---|---:|---:|---:|---:|
| LOCATION | 1,319 | 0.002 | **0.970** | 0.982 |
| PERSON | 1,084 | 0.383 | **0.979** | 0.971 |
| DATE | 611 | 0.838 | 0.949 | 0.987 |
| AGE | 518 | 0.044 | **0.985** | 0.864 |
| DEMOGRAPHIC | 461 | 0.896 | 0.993 | 0.973 |
| ADDRESS | 413 | 0.598 | **0.942** | 0.877 |
| PATIENT_ID | 322 | 0.947 | 0.969 | 0.988 |
| MEDICAL_FACILITY | 136 | 0.007 | **0.838** | 0.958 |
| ORGANIZATION | 67 | 0.000 | 0.149 | — |
| PHONE | 33 | 0.121 | 0.909 | 0.113 |

Conclusiones:

1. **La brecha principal es de datos y modelo, no de arquitectura.** Un NER de dominio barato
   resuelve la mayor parte de LOCATION, PERSON, AGE, ADDRESS y FACILITY. Las reglas siguen
   aportando los identificadores validados (CURP, RFC, CLABE, DNI) y la trazabilidad.
2. **Aun así, no alcanza la meta.** Todavía quedan 43/250 documentos con alguna fuga
   directa, ORGANIZATION casi no se aprende (pocas muestras) y la precisión de PHONE es mala
   por conflicto con identificadores. Hacen falta el *transformer* (F2.2), la fusión (F2.4)
   y datos mexicanos (F3).
3. **MEDDOCAN no es México.** Este resultado es un techo optimista *dentro de dominio*.
   La suite LLM y el holdout mexicano decidirán la salida a producción.

<!-- TRAINED_NER_SECTION -->

---

## 7. Riesgos principales del plan

| Riesgo | Mitigación |
|---|---|
| No conseguir datos mexicanos reales con licencia | Acuerdos con clientes piloto (modo sombra, anotación local); sintéticos solo para entrenamiento, nunca como holdout |
| El NER transformer es lento en CPU | ONNX int8, ventanas por oración, reglas como *fast path*, lotes |
| Sobre-redacción que degrada al LLM | KPI de utilidad obligatorio; marcadores tipados y con rol en vez de `█` |
| Correferencia errónea que fusiona dos personas | Fusión conservadora, KPI B³ y pruebas con homónimos |
| La bóveda se vuelve un punto único de fuga | Cifrado por inquilino, TTL, KMS, sin texto plano en logs, pentest |
| Afirmaciones legales excesivas | Mantener `anonymity_proven: False` y el lenguaje prudente actual del repositorio |

## 8. Cómo reproducir esta auditoría

```sh
python -m pip install -e ".[dev,pdf,ocr,tables,yaml,training,benchmarks,nlp]"
pytest -q          # 359 aprobados, 11 omitidos (sin OCR/spaCy locales)

# MEDDOCAN fuera del repositorio. Si el ZIP de codeload no coincide byte a byte, clonar el
# commit fijado y copiar corpus/{train,dev,test}/brat/*.{txt,ann} -> <corpora>/meddocan/{split}/
git clone https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN && git -C SPACCC_MEDDOCAN checkout 783a6df

# Reglas (verifica el manifiesto de digests por archivo antes de evaluar)
python scripts/audit_public_breakdown.py --corpus <corpora>/meddocan \
  --manifest benchmarks/public-sources/meddocan.json \
  --output benchmarks/results/audit-2026-11/meddocan-test-rules.json
# Reglas + modelo spaCy local (es_core_news_md u otro)
python scripts/audit_public_breakdown.py --corpus <corpora>/meddocan \
  --manifest benchmarks/public-sources/meddocan.json --spacy-model <modelo_local>
# Reglas + modelo entrenado con las etiquetas originales de MEDDOCAN
python scripts/audit_public_breakdown.py --corpus <corpora>/meddocan \
  --spacy-model <modelo_entrenado> --meddocan-labels
```

`scripts/audit_public_breakdown.py` reutiliza `quality_metrics()` sin cambios y añade el
desglose por tipo de cobertura completa, la precisión tipada y los documentos con fuga de
identificadores directos. Los JSON en `benchmarks/results/audit-2026-11/` contienen solo
agregados: ningún texto del corpus ni valor de entidad.

El NER experimental de §6 se entrenó con `spacy init config --lang es --pipeline ner
--optimize accuracy` (CNN con vectores estáticos de `es_core_news_md`, semilla 1729), con train
como entrenamiento y dev como parada temprana. Las etiquetas BRAT se convirtieron a `DocBin`
con `alignment_mode="expand"` y se descartaron 9/11,333 spans de train por solapamiento.
