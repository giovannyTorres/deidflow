# DeidFlow

Censurado y seudonimización de documentos en español con marcadores legibles,
contexto conservado, identidad persistente y relaciones explícitas. **Local,
abierta, gratuita y sin LLMs.** Código [Apache-2.0](LICENSE), con modelos y
fuentes atribuidos en [NOTICE](NOTICE).

Versión de desarrollo **0.6.0b1**. Python 3.11–3.13; inferencia sin dependencias
obligatorias, cuentas, telemetría ni descargas automáticas. Los paquetes por
dominio y los tres modelos españoles se incluyen en el wheel.

## Empezar

```sh
git clone https://github.com/giovannyTorres/deidflow.git
cd deidflow
python -m pip install .
# Para guardar sesiones cifradas:
python -m pip install '.[vault]'
```

```python
from deidflow import get_domain_pack

pack = get_domain_pack("clinical")
texto = "Paciente: Ana López. Niega fiebre. Toma metformina 500 mg."
with pack.session() as sesion:
    resultado = sesion.deidentify(texto)
    print(resultado.output_text)
    print(resultado.status, resultado.issues)
    grafo = sesion.graph()
```

Los identificadores reciben marcadores como `[PACIENTE_1]`, `[MEDICO_1]`,
`[CORREO_1]` o `[CUENTA_1]`. La política clínica conserva diagnósticos, dosis y
negaciones cuando se identifican correctamente; las decisiones ambiguas
requieren revisión. El texto fuera de los intervalos transformados se conserva
sin reescritura generativa.

**Los paquetes y `Policy.context()` requieren revisión humana por defecto.**
`REVIEW_REQUIRED` es una candidata para revisar, no una autorización para
compartirla. El [flujo de revisión](docs/REVIEW_WORKFLOW.md) permite añadir
omisiones, corregir falsos positivos, reconstruir la salida desde el original y
emitir un recibo firmado ligado a fuente, salida, política y modelo.

La [revisión CSV supervisada](docs/CSV_REVIEW.md) aplica correcciones por celda y
encabezado, conserva marcadores dentro del archivo y separa candidatas de
exportaciones aprobadas. Incluye una CLI y un ejemplo financiero ficticio.

## Paquetes incluidos

| Paquete | Modelo local | Comportamiento y evidencia |
| --- | --- | --- |
| `clinical` | `es-clinical` | Roles de paciente, médico y familiar; contexto clínico. Entrenado con MEDDOCAN. |
| `financial` | `es-finance` | Clientes, acreedores, deudores, cuentas e importes. Entrenado con Gretel financiero en español. |
| `legal` | `es-general` | Roles procesales y reglas de contexto; paquete inicial sin validación jurídica independiente. |
| `general` | `es-general` | Modelo mixto y reglas para documentos generales de España y Latinoamérica. |

```sh
deidflow domains
deidflow deidentify entrada.txt --pack clinical --output candidata.txt
```

Cada paquete expone versión, SHA-256 del modelo, fuentes, licencias y límites.
El modelo general incluye la segunda revisión entrenada con más familias de
documentos; sus mediciones y límites están en [la ficha del modelo](docs/TAGGER.md).
Se puede fijar una versión (`get_domain_pack("clinical@1.0.0")`), cambiar la
política o aportar un modelo local adaptado. [Guía de paquetes](docs/DOMAIN_PACKS.md).

## Guardar identidad y relaciones

Una sesión conserva los marcadores entre documentos y al reabrirse en otro
proceso. Su grafo contiene entidades, menciones con offsets y relaciones
explícitamente declaradas con evidencia. No adivina identidades a partir de
nombres parciales ni extrae relaciones mediante un LLM.

```sh
deidflow keygen clave.bin
deidflow session create --pack clinical --state sesion.df --key-file clave.bin
deidflow session process entrada.txt --pack clinical --state sesion.df \
  --key-file clave.bin --output lote-001
```

`lote-001` contiene `candidate.txt`, `session.df`, `graph.json` y `audit.json`.
Continúa con ese nuevo `session.df`; conserva la clave por separado. Los archivos
existentes no se sobrescriben. El código de salida **2** indica revisión o bloqueo;
**0** indica éxito de la operación y **3** una configuración/operación fallida.
Crear una sesión o guardar un grafo no aprueba un documento.

El estado se cifra y autentica con AES-256-GCM: política, mapeos, contadores,
relaciones y caducidad. La restauración rechaza tokens desconocidos y estados
manipulados. La revisión puede usar la misma sesión con `review apply --state
... --key-file ...`. [Sesiones y relaciones](docs/SESSIONS.md) · [CLI completa](docs/CLI_PRODUCT.md).

El [ejemplo ejecutable](examples/context_session.py) comprueba dos notas clínicas,
una relación declarada y el ciclo cifrado de guardado, carga y restauración:
`python examples/context_session.py --output ejemplo-nuevo`.

## Adaptar el modelo a otro ámbito

El postentrenamiento local parte de los pesos del perceptrón estructurado,
conserva categorías anteriores y admite categorías nuevas y replay explícito.
Entrenamiento y validación se separan de test y regresión; IDs, grupos y hashes
detectan reutilización entre particiones.

```sh
python -m pip install '.[training]'
python scripts/adapt_span_tagger.py stage --baseline builtin:es-clinical \
  --train train.jsonl --validation validation.jsonl --output candidato-001
```

La evaluación posterior compara recall, precisión, fugas reales y pérdida de
contexto contra el modelo base. El candidato se prepara para revisión; nunca se
activa automáticamente. [Protocolo, CLI, criterios y ejemplo](docs/POST_TRAINING.md).

## Formatos y alcance

- Texto, CSV/TSV, JSON/JSONL y DataFrames; lectura de Parquet.
- DOCX y XLSX conservan estructura soportada y eliminan copias ocultas conocidas.
  XLSX siempre requiere revisión; medios retenidos y partes desconocidas bloquean.
- PDF se reconstruye con píxeles nuevos; OCR y reverificación locales. Con
  `--pack` se aplica censurado físico y conservación de categorías permitidas,
  no marcadores editables dentro del PDF.
- HTML y correo `.eml`, con saneado de atributos, cabeceras y adjuntos,
  límites de cobertura y revisión obligatoria.
- Exportación conjunta PDF/JSONL para RAG, derivada del PDF transformado.
- Identificadores con validación para 21 países de habla española; RFC, CURP,
  CLABE, tarjetas, IBAN y otros tipos.

La sesión persistente y la revisión por spans trabajan sobre **texto Unicode**.
Los procesadores de archivos conservan sus controles propios; una revisión de
texto extraído no certifica que un PDF u Office esté completamente saneado.
El HTML y el correo conservan únicamente las estructuras soportadas; los
canales no inspeccionables no pueden quedar aprobados.
[Formatos](docs/formats.md) · [PDF/OCR](docs/pdf-redaction.md) ·
[RAG](docs/RAG_EXPORT.md) · [Países](docs/COUNTRIES.md).

## Evidencia verificable

La evaluación conjunta mide privacidad, contexto, consistencia de identidad,
relaciones y carga de revisión. Los casos ficticios son regresiones; no se
presentan como representativos de expedientes reales ni como una clasificación
de bibliotecas. Los resultados de corpus públicos se mantienen con sus límites.

- [Contrato de producto](docs/PRODUCT_ACCEPTANCE.md).
- [Prueba de contexto y comparación reproducible](docs/CONTEXT_BENCHMARK.md).
- [Modelos, corpus y fugas medidas](docs/TAGGER.md).
- [Comparaciones con otros detectores](docs/COMPARISON.md).
- [Guía de auditoría para Claude Code](docs/AUDIT_GUIDE.md).
- [Seguridad y límites del modelo de confianza](docs/security.md).

Las mediciones públicas todavía muestran identificadores no detectados. La
revisión humana y una evaluación representativa del ámbito de uso siguen siendo
necesarias. Un texto con marcadores y relaciones conserva información sensible;
seudonimización reversible no equivale a anonimato.

## Desarrollo

```sh
python -m pip install '.[dev,pdf,ocr,tables,yaml,training,benchmarks,nlp,vault]'
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.11 src/deidflow
python -m pytest -q --cov=deidflow --cov-fail-under=78
python scripts/benchmark_micro.py --check
python -m build
```

CI valida Linux, Windows y macOS con Python 3.11–3.13, el wheel base, dependencias
y licencias. Los tests OCR/spaCy con activos externos se habilitan explícitamente;
las omisiones se reportan. Consulte [CONTRIBUTING.md](CONTRIBUTING.md),
[AGENTS.md](AGENTS.md), [CHANGELOG.md](CHANGELOG.md) y [SECURITY.md](SECURITY.md).

La API anterior (`DeidEngine`, `Policy.strict()`, `Policy.llm()` y
`deidflow.llm.DeidSession`) se conserva. El nombre histórico `llm` nunca carga ni
llama a un LLM; para nuevas aplicaciones use paquetes, `Policy.context()` y
`deidflow.DeidSession`.
