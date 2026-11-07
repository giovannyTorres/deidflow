# Corpus contextual ficticio MX (BMX-11)

`generate_contextual_package` entrega tres paquetes reproducibles: contextual
y estricto comparten diez documentos y 47 menciones; el desafío separado tiene
dos documentos con tres hipótesis PERSON ambiguas. Son doce textos originales
y fijos, sin generador de nombres aleatorios ni documentos personales reales.
El alcance medido sigue siendo es-MX. No se cambia producción para mejorar los
resultados de estos ejemplos.

```python
from deidflow.benchmarks.contextual_package import generate_contextual_package
from deidflow.benchmarks.transformation_runner import run_transformation_benchmark

summary = generate_contextual_package(
    "/tmp/deidflow-contextual-001",  # Destino nuevo.
    mode="contextual",  # Alternativas: "strict" y "ambiguous".
    decision="docs/benchmark-mx/operational-decision-v1.json",
    decision_sha256="ce1ae6e4ca8e0567bac0fa24a37d3f109eb2e11ef4755bd797d7fd5865ac5ffa",
)
run_transformation_benchmark(
    "/tmp/deidflow-contextual-001",
    manifest_sha256=summary["manifest_sha256"],
    candidate="transform.text",
    profile="transformation-descriptive-v1",
    output="/tmp/deidflow-contextual-transform-001",
)
```

El recibo operativo y su pin son entradas explícitas. El paquete instalado
contiene su propia guía y ledger; no lee documentos del checkout ni importa
pruebas. El escritor compartido serializa y admite todos los recursos antes
de publicar el directorio. Nunca sobrescribe un destino existente. D3 se
comprueba además del hash: clínica preservada en contextual, retirada en
estricto, identificadores retirados en ambos y operadores acordados.

Los [ejemplos versionados](../examples/benchmark-mx-contextual/) contienen
`contextual`, `strict` y `ambiguous`. Sus pins y resultados sanitizados están
en [BMX-11-generation.json](audit/BMX-11-generation.json). Cada paquete incluye
los cuatro IDs técnicos existentes: detection, validation, transformation y
pipeline con sufijo `-descriptive-v1`. Su presencia no afirma que se haya
medido cada pista: este incremento ejecuta detección y transformación aislada;
no añade vectores de checksum a categorías donde no aplica.

| Mención | Soporte confirmado |
| --- | ---: |
| PERSON | 16 |
| ADDRESS | 2 |
| DIAGNOSIS | 3 |
| MEDICAL_CONDITION | 7 |
| MEDICATION | 4 |
| TREATMENT | 6 |
| CLINICAL_OBSERVATION | 9 |

Los diez casos cubren formulario con CRLF, nombres compuestos y acentos,
domicilios con número/interior/colonia, narrativa con y sin puntos, palabras
comunes y nombres de vía, negaciones, dosis/unidades/frecuencia y atribución
de síntomas a paciente o familiar. Hay anidamiento clínico y una codificación
explícita y deliberadamente artificial de nombres cruzados. Esta última
comprueba la mecánica de spans, no representa lenguaje clínico natural.
La variante sin puntos declara padre, raíz, variante y receta; comparte
familia/grupo con la narración de origen. No comienza un generador general de
perturbaciones ni cambia esa ascendencia al exportar.

Dos homónimos declarados como personas distintas tienen IDs diferentes.
Dos notas aportan continuidad explícita y comparten identidad/familia/grupo.
La posible relación entre un nombre y su alias permanece desconocida: sus
menciones PERSON son confirmadas y se protegen, sin inventar una vinculación.
Los runners actuales no miden consistencia de identidad; los IDs son referencia
y evidencia de clausura para la auditoría de particiones, no un resultado de
calidad de identidad.

La [guía real](benchmark-mx/contextual-annotation-guide-v1.md) fija límites,
categorías y expectativas. La [referencia congelada para revisión](benchmark-mx/contextual-reference-v1.json)
incluye todos los textos, offsets Unicode, superficies, contexto de límites,
acciones por modo e identidades declaradas. El
[ledger real de agentes](benchmark-mx/contextual-reference-reviews-v1.json)
registra las revisiones separadas de `/root/bmx11_reference_a` y
`/root/bmx11_reference_b`, y la adjudicación de `/root`. No son revisores
humanos. Ninguna predicción del candidato se utilizó como verdad de referencia.

La procedencia sigue siendo `synthetic_fixture`, con referencias `r-a`/`r-b`
que deben existir en el ledger y coincidir con los hashes de guía/referencia.
El generador rechaza revisión caducada, actores duplicados, resultado rechazado,
casos sin decisión y timestamps sin UTC. Los casos confirmados se marcan
`adjudicated`; los dos desafíos conservan `unresolvable`, revisión requerida y
cobertura no exhaustiva. El desafío nunca se suma a la métrica principal.

El perfil contextual preserva 29 menciones clínicas completas y retira 18
identificadores. El estricto retira las 47 menciones. Con el transformador
aislado y gold, ambos alcanzan 10/10 documentos de éxito conjunto y retención
1.0. Esto verifica transformación con referencia suministrada, no detección.
El desafío obtiene REVIEW_REQUIRED y 0/2 éxitos conjuntos; sus tres hipótesis
no se convierten en negativos ni en un éxito automático de privacidad.

La detección real `rules.mx` sobre los diez casos reconoce exactamente una
mención PERSON y una MEDICATION, con omisiones y falsos positivos conservados.
No se corrigieron reconocedores, límites ni categorías tras ver esos errores.
La guía y la referencia se revisaron antes de ejecutar esa detección.

El objetivo operativo ratificado sigue siendo automático/global y con ajuste
local sencillo, con revisión de ambigüedades. `evidence-9` conserva ese recibo;
los perfiles técnicos derivados mantienen `ratified:false`, y todos los
resultados siguen DESCRIPTIVE_ONLY. Todos los textos están expuestos como
regresión conocida; entrenamiento y ajuste se declaran desconocidos. No hay
train, validation, calibration ni blind_test. La auditoría encuentra ocho
componentes principales y dos de desafío, sin cruces ni grupos separados,
y conserva `NO_BLIND_TEST` e independencia ciega no acreditada.
