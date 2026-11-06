# Admisión del paquete local del benchmark MX (BMX-02)

Este incremento implementa [BMX-02](tickets/benchmark-mx/02-admision-paquete.md)
de [DF-EVAL-MX v0.1.0](specs/BENCHMARK_MX_SPEC.md): valida el paquete completo
antes de evaluar y conserva spans anidados o cruzados. El recorrido
[BMX-01](BENCHMARK_MX_EMAIL.md) y su API siguen disponibles.

## Reproducción local

Sin extras, red ni adquisición de activos, desde el checkout:

```python
from deidflow.benchmarks.package_runner import run_package_benchmark

report = run_package_benchmark(
    "examples/benchmark-mx-package",  # También acepta un ZIP local.
    manifest_sha256="60649f3f48a350b1b04d8bf0c930e983e98ae5a9eacbcbd790bc422907d724f9",
    candidate="rules.mx",
    profile="email-descriptive-v1",
    output="/tmp/deidflow-package-run-001",  # Directorio nuevo.
)
print(report["result"]["metrics"]["EMAIL"])
```

El hash confiable se suministra por separado. Leerlo automáticamente del mismo
paquete no autentica su procedencia. No se extraen ZIPs ni se ejecutan recursos,
scripts, generadores o referencias declaradas en los datos.

El [ejemplo](../examples/benchmark-mx-package/manifest.json) es un fixture
totalmente ficticio de **regresión conocida**: dos documentos y dos menciones
EMAIL anidadas, en el dominio reservado `.test`. El detector real reconoce la
mención exterior: TP=1, FP=0, FN=1, soporte=2, precision=1.0, recall=0.5,
F1=2/3. Comprueba la conservación de solapamientos; no estima calidad poblacional.
Las anotaciones están en borrador, sin revisores humanos inventados.

## Contrato v1

Esta implementación concreta las formas JSON de los apartados 3 y 4 de la
especificación. No ratifica D1–D3 ni un perfil de calidad. El ejemplo y sus seis
recursos son instancias completas; el validador ejecutable está en
[`evaluation_package.py`](../src/deidflow/benchmarks/evaluation_package.py).

| Elemento | Contrato y validación |
| --- | --- |
| Manifiesto | Esquema `df-eval-mx.package.v1`, taxonomía `df-eval-mx.taxonomy.v1`, anotación `df-eval-mx.annotation.v1`; versión numérica del dataset, ID opaco y fecha UTC |
| Recursos | Roles obligatorios `sources`, `documents`, `units`, `mentions`, `expectations` en JSONL; perfiles JSON; binarios opacos. Descriptor exacto: `path`, `kind`, `sha256`, `bytes`, `records` |
| Fuentes | Identidad, revisión, contenido; origen, idioma, país, dominio, referencias y licencia conocida; permisos separados, revisión, estado ficticio/no personal y exposición |
| Documentos | Caso, fuente, raíz, grupo, familia y linaje; partición o panel; formato, estratos, capacidades, artefacto, unidades, receta y estado de anotación |
| Unidades | `unit_id`, `case_id`, `text`, `text_sha256`, `content_role`, `locator`; texto original sin normalización; localizador `{kind: "text", index: entero}` único por caso |
| Menciones | ID, unidad, tipo, intervalo, certeza, validez separada por patrón/estructura/checksum; sensibilidad, identidad ficticia opcional y procedencia |
| Expectativas | Perfil, caso y mención o intervalo de contexto; acción, operadores, verificación, cobertura y estados aceptables |
| Perfiles | `profile_id`, `ratified=false`, `clinical_policy`, `quasi_identifier_policy`, `precedence`; referencia y hash en el manifiesto |

Se rechazan campos adicionales, versiones de esquema desconocidas, claves JSON
duplicadas, NaN/Infinity y overflow a infinito, BOM, UTF-8 o surrogates inválidos.
Las versiones numéricas tienen tres componentes de 1–6 dígitos. IDs de registros:
prefijo de su tipo (`d-`, `s-`, `c-`, `u-`, `m-`, `e-`, `g-`, `t-`, `v-`, `i-`,
`r-`) y 1–32 dígitos hexadecimales; no nombres, correos ni nombres originales.

Roles de perfil: `profile-<hex>`; binarios: `artifact-<hex>`, `evidence-<hex>`,
`generator-<hex>` o `rule-<hex>`. Los binarios tienen conteo cero, JSON tiene
uno y JSONL usa el número exacto de filas. Se admite salto final y CRLF; las
líneas vacías intermedias son inválidas. Un recurso de contrato desconocido
no se ignora.

Los permisos de evaluación, anotación, derivación, entrenamiento y redistribución
son booleanos separados; evaluación debe ser verdadero. Una fuente sintética
requiere `fictional` y revisión `synthetic_fixture` o `approved`. Otro origen
requiere `verified_nonpersonal`, revisión `approved` y referencias locales de
evidencia/términos. Las declaraciones se validan estructuralmente: no prueban
permisos legales ni ausencia de datos personales. Solo se incorporan fixtures
originales en esta entrega.

`exposure` contiene `training`, `tuning`, `prior_evaluation` (booleano o `unknown`)
y `candidate_exposure` (`known`, `unknown`, `unexposed`). No se convierte lo
desconocido en ausencia de exposición. Para una fuente con una unidad,
`content_sha256` hashea su texto UTF-8. Con varias unidades, ordenadas por ID,
hashea nombre UTF-8 y texto, cada uno precedido por longitud de 8 bytes big-endian.
Los recursos se hashean en bytes originales; el hash del manifiesto es externo.

## Relaciones y límites

Las referencias deben existir y coincidir en ambos sentidos: documento/unidad,
mención/unidad, expectativa/caso/perfil y artefacto/recurso/hash. Cada caso
pertenece exactamente a una partición o panel, con grupos consistentes que no
cruzan colecciones. No se crean particiones ni grupos mediante fallback. El
linaje no admite ciclos y conserva raíz, grupo y familia; derivar necesita
permiso explícito.

Los offsets son enteros no booleanos, base cero, intervalos semiabiertos de
puntos de código Python. Se conservan diacríticos, caracteres fuera de BMP y
CRLF. Spans anidados y cruzados se admiten; duplicados por unidad/tipo/intervalo
se rechazan aunque cambie el ID. La cobertura declara unidades, categorías
exhaustivas, regiones inspeccionadas y límites; exhaustividad exige inspección
sin huecos de toda la unidad. La cobertura parcial permanece como tal.

Las expectativas solapadas se comprueban con barrido de intervalos. Acciones
diferentes requieren precedencia explícita en el perfil (primera con prioridad).
Operadores y estados de las expectativas activas de la acción aplicable deben
tener intersección. No se elige una acción silenciosamente ni se transforma.

`generation` declara versión, algoritmo (`none` o `python-random-v1`), semillas
enteras y referencias de recursos/reglas; no se ejecuta. `freeze` declara
`unfrozen` o `frozen`; congelar exige fecha UTC, custodia declarada y hashes
coincidentes de todos los recursos. No acredita custodia o independencia real.

| Límite de admisión | Valor |
| --- | --- |
| Manifiesto | 64 KiB |
| Recurso | 2 MiB |
| Bytes totales / ZIP / expansión ZIP | 16 MiB |
| Recursos / miembros ZIP | 128 / 256 |
| Ratio máximo de compresión ZIP | 100 |
| Filas por recurso / predicciones por unidad | 10000 / 10000 |
| Profundidad JSON | 32 |

Rutas relativas sin componentes vacíos, `.` o `..`, barras invertidas ni
prefijos de volumen; enlaces que salen del directorio se rechazan. ZIP rechaza
miembros duplicados, cifrados o especiales y compresiones distintas de
stored/deflate. No se extrae. Son límites de admisión, no de tiempo/RSS duros.

## Resultado y estados separados

El informe `df-eval-mx.package-report.v1` separa `result` determinista de
`operational`; publica hashes, configuración y conteos, sin textos, valores,
IDs originales, nombres de archivos ni mensajes arbitrarios del candidato.

- **Dataset inválido:** `InvalidPackageError`, subclase de `ValueError`,
  `status=INVALID_RUN`; mensaje fijo y sin informe favorable.
- **Evaluación no soportada:** `UnsupportedEvaluationError`, subclase de
  `ValueError`, `status=UNSUPPORTED`; sin métricas ni salida favorable.
- **Respuesta/fallo del candidato:** informe `attempt_status=candidate_error`,
  código `CANDIDATE_ERROR`, métricas EMAIL `null` y soporte requerido conservado;
  nunca una predicción vacía favorable.

La admisión valida todo antes de ejecutar. Este recorrido puntúa únicamente
`known_regression`, EMAIL textual, menciones confirmadas y cobertura EMAIL
exhaustiva, con perfil explícito no ratificado. Entrenamiento se valida sin
puntuarlo. Otros ámbitos, perfiles y formatos conservan sus tickets propios.

`rules.mx` usa el motor existente. Para adapters locales controlados se admite
`DetectionCandidate(candidate_id, source_sha256, detect)`: ID `candidate-<hex>`,
fingerprint declarado por el caller y callback texto → lista/tupla. Predicciones
validan tipo, offsets y score/confianza finitos en [0,1]; se copian a valores
estables. Su identidad es `caller_declared`; configuración no acreditada queda
desconocida. El callback es Python local confiable; los datos no pueden crear
ni seleccionar código ejecutable. No es una sandbox para código arbitrario.

La calidad siempre es **`DESCRIPTIVE_ONLY`**. La admisión no acredita anonimato,
representatividad, permisos reales, independencia ni aislamiento nativo. Los
binarios solo se comprueban por identidad/tamaño, sin afirmar que un DOCX/PDF
sea válido o haya sido inspeccionado. Véase [el acta BMX-02](audit/BMX-02.md).
