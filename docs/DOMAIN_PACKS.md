# Paquetes de dominio locales en español

DeidFlow incluye cuatro paquetes versionados. Cada uno selecciona reglas de
identificación, un modelo discriminativo local con SHA-256 fijado y una política
que sustituye identificadores por marcadores españoles con índice. No necesita
un LLM, una API, credenciales de inferencia ni descargas en tiempo de ejecución.

| Nombre | Modelo predeterminado | Uso y alcance |
| --- | --- | --- |
| `clinical@1.0.0` | `es-clinical` | Notas clínicas; MEDDOCAN, España, con datos personales sintéticos. |
| `financial@1.0.0` | `es-finance` | Documentos financieros; parte española del conjunto sintético de Gretel. |
| `legal@1.1.0` | `es-general` (`es-general-2`) | Paquete inicial: modelo general y reglas de roles jurídicos. No hay un modelo jurídico especializado ni validación independiente jurídica. |
| `general@1.1.0` | `es-general` (`es-general-2`) | MEDDOCAN/Gretel y 5000 documentos sintéticos de 51 familias de entrenamiento. |

La evaluación de esos modelos no prueba la calidad sobre documentos reales de
una organización o de cada país. Todos los paquetes declaran
`supervised_review=True`: requieren evaluación local y revisión antes de liberar
resultados. La política activa `require_human_review`; el motor devuelve
`HUMAN_REVIEW_REQUIRED` hasta que se complete la revisión explícita.
`APPROVED` describe las comprobaciones del flujo; no es
una certificación de anonimato. El perfil `assurance` cambia los umbrales de
operación; tampoco garantiza que no haya fugas.

## Descubrir y fijar una versión

```python
import json
from deidflow.domains import get_domain_pack, list_domain_packs

print(json.dumps([pack.to_dict() for pack in list_domain_packs()], ensure_ascii=False, indent=2))
pack = get_domain_pack("clinical@1.0.0")
assert pack is get_domain_pack("clinical", version="1.0.0")
```

La consulta no carga pesos. Los metadatos incluyen modelo y digest, revisiones
de los corpus, licencias, alcance de evaluación, roles, categorías conservadas
y limitaciones. Una versión inexistente o un cambio del digest del modelo produce
un error. El código es Apache-2.0; MEDDOCAN exige atribución CC-BY-4.0, Gretel usa
Apache-2.0 y Faker usa MIT. Véanse [NOTICE](../NOTICE), [la ficha de los modelos](TAGGER.md)
y [las fuentes públicas](PUBLIC_CORPORA.md).

Los paquetes general y jurídico 1.1.0 fijan los pesos `es-general-2`. La versión
1.0.0 de esos paquetes correspondía a `es-general-1` y no se redirige de forma
silenciosa al modelo nuevo. Los resultados anteriores de ese modelo permanecen
como evidencia histórica. Para reanudar una sesión anterior se necesita su misma
configuración; los paquetes clínico y financiero conservan su versión 1.0.0.

## Conservar significado y consistencia

```python
from deidflow.domains import get_domain_pack

pack = get_domain_pack("clinical@1.0.0")
session = pack.session()
result = session.deidentify(
    "Paciente: Ana López niega diabetes y toma metformina 500 mg. Médico: Luis Pérez."
)
print(result.output_text)
# Paciente: [PACIENTE_1] niega diabetes y toma metformina 500 mg.
# Médico: [MEDICO_1].
print(result.status, result.issues)  # Revisar antes de utilizar el resultado.
```

Las categorías clínicas detectadas, el contexto demográfico y los importes se
conservan por defecto. Dosis, negaciones, conectores y cláusulas permanecen como
texto cuando no se solapan con una detección sensible. Las personas, documentos,
cuentas, organizaciones, ubicaciones, edades y fechas absolutas se sustituyen
por marcadores. Conservar una enfermedad rara, un importe excepcional o una
combinación demográfica puede permitir reidentificación; la política debe
ajustarse al propósito y al riesgo del conjunto.

Los roles proceden de indicios explícitos antes de un nombre y construcciones
acotadas como «debe a» o «adeuda a» para un acreedor. Los marcadores
incluyen `PACIENTE`, `MEDICO`, `FAMILIAR`, `CLIENTE`, `ACREEDOR`, `DEUDOR`, `AGENTE`,
`DEMANDANTE`, `DEMANDADO`, `TESTIGO`, `ABOGADO` y `JUEZ`. El género gramatical de un
título es evidencia lingüística, no una afirmación sobre la identidad de la persona.

La misma grafía normalizada, tipo y rol reutilizan un marcador dentro de una
sesión. «Ana López», «López» y «Ana» no se unen por una suposición. Un cambio de
rol tampoco se considera automáticamente la misma identidad. Los paquetes pueden
reutilizar una única identidad compatible cuando se repite el valor completo y
falta el rol o género; los datos explícitos contradictorios impiden esa unión.
Pronombres,
relaciones familiares y obligaciones no se resuelven por inferencia. La sesión
permite declarar relaciones con evidencia explícita; su grafo no incluye los
valores originales. Los marcadores y relaciones siguen siendo datos vinculables.

Si un modelo extiende `PERSON` hasta una palabra como «niega», el paquete puede
recortar esa detección al nombre completo indicado por un rol explícito. Solo
admite palabras de una lista cerrada fuera del nombre; otros nombres o
identificadores conservan su cobertura. La marca `DOMAIN_BOUNDARY_REFINED`
mantiene el resultado en revisión. No garantiza preservar todo contexto en texto
arbitrario.

También reconoce observaciones clínicas negativas con gramática y vocabulario
acotados tras una etiqueta de paciente, por ejemplo «NO REFIERE TOS NI DISNEA» o
«SIN SIGNOS DE INFECCIÓN». Si un modelo las confunde con una persona o ubicación,
las reclasifica como observaciones clínicas con marca `DOMAIN_CONTEXT_REFINED`.
La revisión sigue siendo obligatoria y no se descartan detecciones de documentos,
cuentas u otros identificadores por esta regla.

Los sustantivos de parentesco en minúsculas se conservan bajo construcciones
como «su hermano» o «ambos son hermanos». Esto no relaciona identidades en el
grafo. Cuando dos nombres completos conocidos están unidos por «y» o «e», se
separan sus menciones con la marca `PERSON_COORDINATION_SPLIT`; los apellidos
compuestos, como «Ortega y Gasset», conservan su cobertura. Los puntos finales de
una oración quedan fuera de los identificadores etiquetados, mientras que los
puntos internos de un código siguen formando parte de él.

En turnos con etiqueta y dos puntos, respuestas completas seguidas de puntuación
como «Cliente: Sí,» o «Agente: Gracias,» no se convierten en nombres. «Cliente:
No Cárdenas» conserva su detección de persona. Los nombres coordinados sin
evidencia suficiente y las direcciones superpuestas pueden compartir marcador
y absorber puntuación; esa ambigüedad requiere revisión y no implica resolución
automática de identidades.

Las direcciones etiquetadas terminan ante el siguiente encabezado conocido con
dos puntos o signo igual. Las abreviaturas «Av.» y «C.P.» y las continuaciones
postales permanecen dentro de la dirección. Teléfonos y correos se detectan por
separado. El grupo sanguíneo etiquetado es `MEDICAL_ATTRIBUTE`: el paquete lo
conserva por defecto, mientras que una política estricta o una selección
explícita de esa categoría sensible lo sustituye.

## Elegir modelo, detector y política

```python
from deidflow.domains import get_domain_pack

pack = get_domain_pack("financial")
engine = pack.engine(model="builtin", profile="assurance", country="MX")
policy = pack.policy(sensitive_types=("AMOUNT",))
result = engine.deidentify_text("Cliente: Ana López. Importe: 6500 MXN.", policy=policy)
print(result.output_text, result.status)
```

Al usar directamente los métodos de `pack.engine()` debe pasarse
`policy=pack.policy()` o una política propia. `pack.session()` aplica la política
del paquete automáticamente. `pack.recognizers()` proporciona las reglas
narrativas y de roles para configurar un motor propio.

| Opción | Comportamiento |
| --- | --- |
| `model="default"` o `"builtin"` | Carga el modelo fijado y verifica el SHA-256 del recurso. |
| `model="rules"` | Usa reglas sin modelo estadístico. La política exige modelo, por lo que el resultado requiere revisión. |
| `model="custom"` | Requiere un adaptador local confiable con `detect_batch` y un `adapter_digest` SHA-256 explícito. Es una declaración del llamador sobre recursos/configuración, no una verificación del código arbitrario del adaptador. |
| `profile="balanced"` o `"assurance"` | Selecciona los umbrales empaquetados. Los adaptadores propios configuran sus umbrales directamente y aceptan solo el perfil predeterminado. |
| `country="ALL"`, `"MX"`, `"ES,MX"`, etc. | Selecciona reglas de identificadores nacionales soportadas. No cambia los corpus de entrenamiento. |
| `preserve_context=False` en `policy()` | Sustituye también las categorías de contexto detectadas. |
| `sensitive_types=("MEDICATION", "AMOUNT")` | Sustituye esas categorías: `[MEDICAMENTO_1]`, `[IMPORTE_1]`. |

Las reglas monetarias reconocen números acompañados de moneda o etiquetas como
«importe:» y «saldo:». Conservar importes nunca elimina una detección de tarjeta,
cuenta u otro identificador superpuesto. Por ejemplo, un número con checksum de
tarjeta sigue ocultándose aunque termine en «MXN». La ambigüedad puede reducir
la utilidad y debe revisarse.

## Fechas y edades

Por defecto las edades y fechas se convierten en marcadores. Repetir una fecha
reutiliza su índice, pero los índices no codifican un intervalo de tiempo. Para
conservar intervalos se puede elegir un desplazamiento constante:

```python
from deidflow.domains import get_domain_pack

pack = get_domain_pack("clinical")
policy = pack.policy(dates="shift", shift_days=30)
session = pack.session(model="rules", policy=policy)
result = session.deidentify("Nacimiento: 1990-01-03. Consulta: 2025-01-10; control: 2025-01-17.")
assert "[FECHA_NACIMIENTO_1]" in result.output_text
assert "2025-02-09" in result.output_text and "2025-02-16" in result.output_text
```

`shift_days` debe ser un entero no nulo entre −36500 y 36500 y mantenerse igual
en la sesión. Solo `DATE` permite residuales cuando se desplaza; las fechas
detectadas como `DATE_OF_BIRTH` siempre se indexan. Se admiten los formatos del
transformador, incluidos ISO, día/mes/año con año de cuatro dígitos y fechas
escritas en español. Un formato no transformable no debe liberarse.
`dates="keep"` conserva fechas absolutas por decisión explícita y tampoco conserva
fechas de nacimiento detectadas. `sensitive_types=("DATE",)` tiene prioridad.
Ni desplazar ni conservar fechas elimina su riesgo de vinculación. Las edades
se pueden configurar con una `Policy` propia si el caso necesita otro tratamiento.

## Reanudar con la misma configuración

```python
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from deidflow.domains import get_domain_pack
from deidflow.session import DeidSession

pack = get_domain_pack("financial@1.0.0")
session = pack.session(model="rules")
first = session.deidentify("Cliente: Ana López")
key = secrets.token_bytes(32)  # Guardar por separado; no imprimir ni registrar.
with TemporaryDirectory() as directory:
    path = Path(directory) / "sesion.enc"
    session.save(path, key=key, ttl_seconds=3600)
    resumed = DeidSession.load(
        path, key=key, engine=pack.engine(model="rules"), policy=pack.policy()
    )
    second = resumed.deidentify("Cliente: Ana López")
    assert first.output_text == second.output_text
```

El cifrado requiere `deidflow[vault]`. El digest vincula paquete, modelo, perfil,
reglas y países; la sesión verifica también la política. Cambiar esa
configuración impide reanudar con el mismo archivo. El archivo reversible
contiene originales cifrados y necesita retención, permisos y custodia de clave
apropiados. No se serializa código ejecutable ni se carga un modelo del archivo.

Los casos ficticios de `tests/test_domain_packs.py` comprueban estos contratos,
incluyendo identificadores superpuestos, negaciones, dosis, importes, roles y
reanudación. Son regresiones reproducibles, no una estimación de calidad clínica,
financiera o jurídica en producción.
