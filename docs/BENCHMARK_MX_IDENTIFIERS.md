# Corpus ficticio de identificadores mexicanos (BMX-10)

`generate_identifier_package` crea un paquete local de 36 casos conocidos, con
seis tipos y ocho familias. Los literales son construidos o constantes genéricas
de facturación. No procede de documentos personales, no consulta servicios y no
afirma que un número sea inexistente, no asignado o propiedad de alguien.

```python
from deidflow.benchmarks.synthetic_package import generate_identifier_package
from deidflow.benchmarks.evaluation_package import load_evaluation_package
from deidflow.benchmarks.package_runner import run_package_benchmark
from deidflow.benchmarks.validation_runner import run_validation_benchmark

summary = generate_identifier_package(
    "/tmp/deidflow-identifiers-001",  # Destino nuevo; nunca se sobrescribe.
    seed=104729,
    decision="docs/benchmark-mx/operational-decision-v1.json",
    decision_sha256="ce1ae6e4ca8e0567bac0fa24a37d3f109eb2e11ef4755bd797d7fd5865ac5ffa",
)
package = load_evaluation_package(
    "/tmp/deidflow-identifiers-001", manifest_sha256=summary["manifest_sha256"]
)
for runner, profile, output in (
    (run_package_benchmark, "detection-descriptive-v1", "/tmp/deidflow-identifiers-detection-001"),
    (
        run_validation_benchmark,
        "validation-descriptive-v1",
        "/tmp/deidflow-identifiers-validation-001",
    ),
):
    runner(
        "/tmp/deidflow-identifiers-001",
        manifest_sha256=summary["manifest_sha256"],
        candidate="rules.mx",
        profile=profile,
        output=output,
    )
```

El generador instalado no necesita archivos del repositorio ni módulos de
pruebas. El caller proporciona el recibo local y su pin SHA-256; sus bytes se
copian como `evidence-9`. El ejemplo anterior utiliza el recibo de esta sesión.
La comprobación del hash acredita integridad respecto del pin, no autentica
por sí misma la autoría ni crea una ratificación nueva.

El [ejemplo versionado](../examples/benchmark-mx-identifiers/manifest.json)
usa `mx-identifiers-1.0.0`, dataset `1.0.0`, semilla `104729` y manifest SHA-256
`ed2a387e84ab9a0b5764a803e59ea8f173e5c2eceaea00debd2b26064a1c1dba`.

| Familia | Casos | Cobertura acotada |
| --- | ---: | --- |
| RFC de forma física | 6 | Compacto, separadores, checksum, fecha imposible, ambiguo y distractor |
| RFC de forma moral | 4 | Compacto, separadores, checksum y distractor |
| RFC genéricos | 2 | Nacional/extranjero; constantes no personales |
| CURP | 5 | Válido, checksum, fecha imposible, truncado y distractor |
| CLABE | 5 | Compacto, grupos, checksum, truncado y distractor |
| PAN | 5 | Longitudes 13/16, grupos, checksum y distractor |
| Teléfono mexicano | 4 | Formato internacional/nacional, longitud corta y distractor |
| Correo | 5 | Dot-atom, etiqueta `+`, dobles puntos, doble `@` y distractor |

El resumen entrega soporte por entidad, familia, entidad/estrato y acción; no
contiene textos ni identificadores originales. Una celda ausente tiene cero
soporte. Estos pocos ejemplos no representan la distribución de despliegue.
Hay 27 menciones, 36 vectores y 144 expectativas: 26 casos requieren retirar,
nueve preservar y uno revisar en cada configuración. Las cifras de soporte de
detección pueden excluir la mención ambigua según la métrica.

El mismo RFC con checksum malo aparece atribuido, sin atribución confirmada y
como constante explícita de software. D2 exige respectivamente `remove`,
`review_required` y `preserve`; el checksum permanece inválido en los tres.
Los distractores no tienen mención gold de detección, pero sí una expectativa
de preservación por intervalo. Los RFC de forma moral prueban la forma técnica
de un identificador proporcionado en un expediente sintético, sin afirmar la
existencia de una persona jurídica.

El recibo de decisiones D1–D3 está ratificado. Las cuatro configuraciones
ejecutables `*-descriptive-v1` son traducciones técnicas del agente y mantienen
`ratified:false`: no se ratificaron individualmente. El resumen distingue ese
estado de `decision.status:ratified` y de `quality_ratified:false`. Las acciones
siguen D2; este corpus no contiene hechos clínicos que diferenciar según D3.
Los perfiles de transformación y pipeline se incluyen para facilitar evaluación
posterior; su presencia no acredita que sus recorridos hayan sido aprobados.
Todos los resultados actuales siguen `DESCRIPTIVE_ONLY`.

Las familias/grupos y su panel se asignan antes de renderizar. La semilla solo
selecciona entre dos textos por acción: `random.Random(seed).random()` y el
índice `floor(2*u)`, registrados como `python-random-v1`. Las variantes de
formato son fixtures declarados, sin perturbaciones generadas ni padres
inventados. Todas las particiones `train`, `validation`, `calibration` y
`blind_test`, y el panel `external_transfer`, están explícitamente vacíos;
36 casos pertenecen a `known_regression`. La exposición previa es conocida;
el historial de entrenamiento/ajuste se declara desconocido. El auditor conserva
`NO_BLIND_TEST`, cero cruces y cero grupos separados, sin acreditar independencia
ciega. Las fechas fijas del corpus son la época de metadatos de esta versión,
no un sello de revisión humana ni la hora de cada generación.

Las referencias separan patrón, estructura y checksum. Se ejecutaron
`python-stdnum 2.2` para RFC/CURP/Luhn y una hoja reducida 3/7/1 para CLABE;
el [recibo de comprobación](audit/BMX-10-vectors.json) conserva observaciones
reales de los 36 vectores. Ni stdnum ni otro paquete nuevo se importa durante
la generación o inferencia. Para RFC se calcula el dígito por separado:
`XEXX` tiene checksum ordinario válido y `XAXX` inválido. La excepción del
candidato para `XAXX` produce una discrepancia conservada. La
[fe de erratas de BMX-04](audit/BMX-04-erratum.md) corrige el fixture anterior
sin reescribir los recibos históricos.

CLABE/PAN solo declaran longitud, caracteres y no degeneración para estructura;
no verifican banco, plaza, BIN, red ni registro. PHONE comprueba una forma
acotada de diez dígitos nacionales con `+52` opcional; estructura queda
desconocida. EMAIL contrasta sintaxis ASCII con `email.headerregistry.Address`
y una hoja dot-atom/DNS, utilizando `example.invalid`; no consulta DNS ni
entrega. El parser no es un oráculo completo de toda la sintaxis de correo.
Los validadores builtin de PHONE/EMAIL siguen devolviendo patrón/estructura
desconocidos y checksum no aplicable. Las referencias sintácticas conocidas
producen discrepancias y `unknown_prediction`, no acuerdos fabricados.

`write_package_records(destination, records, manifest)` es el escritor compartido.
Serializa listas JSONL, objetos JSON y bytes binarios, recalcula hashes de
recursos/perfiles y membresías, aplica límites y pasa el resultado por el
cargador real antes de publicarlo. Conserva las referencias, digests de
unidades/fuentes y linaje proporcionados: un error produce rechazo, no una
reparación silenciosa. Nunca reemplaza un destino existente y sanea los errores
del sistema de archivos. No carga código de los recursos. Su uso no modifica
detectores, políticas ni transformadores para mejorar estas puntuaciones.
