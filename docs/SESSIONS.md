# Sesiones locales, identidad y relaciones

`DeidSession` seudonimiza textos en un mismo ámbito de identidad sin llamar a
servicios ni ejecutar un LLM. Conserva marcadores españoles entre documentos y
permite guardar el estado completo cifrado para continuar en otro proceso.
`from deidflow.llm import DeidSession` sigue funcionando como alias de la API
neutral `from deidflow.session import DeidSession`.

```python
from deidflow import DeidEngine
from deidflow.session import DeidSession

session = DeidSession(DeidEngine())
result = session.deidentify("Contacto: persona@example.test")
assert result.output_text == "Contacto: [CORREO_1]"
assert session.deidentify("persona@example.test").output_text == "[CORREO_1]"
graph = session.graph()
```

La política predeterminada es `Policy.context()`: conserva contexto clínico,
generaliza edad y exige capacidad semántica y revisión humana. El motor de reglas del ejemplo
devuelve `REVIEW_REQUIRED`; procesar o guardar una sesión **no aprueba** su salida.
Selecciona el modelo y la política apropiados y atiende `result.status`,
`result.issues` y `result.release_approved` antes de compartir resultados.

## Qué significa una identidad

Se reutiliza un marcador solamente para el mismo valor normalizado Unicode NFC
y tipo de entidad. La sesión neutral activa `compatible_context=True`: si falta
rol o género en una mención, conserva la identidad solamente cuando existe una
única entidad compatible con ese texto exacto. Acumula los roles y géneros
explícitos observados; no deduce los ausentes. Dos roles o géneros explícitos
contradictorios crean entidades separadas. Una mención sin contexto que podría
corresponder a más de una de ellas falla y exige desambiguación explícita.

El marcador ya emitido nunca cambia: `[PERSONA_1]` puede adquirir rol `patient`
en el grafo tras una observación posterior, sin renombrar textos anteriores.
Para exigir igualdad de rol y género incluso cuando falten, aporta un asignador
estricto: `DeidSession(engine, allocator=PlaceholderAllocator())`. El asignador
independiente conserva ese comportamiento estricto por defecto. Los snapshots
antiguos con asignador versión 1 también conservan el modo estricto al cargarse.

No se eliminan acentos, puntuación, diferencias de mayúsculas ni partes del
nombre. Un nombre parcial o un alias nunca establece identidad. Dos personas
homónimas pueden compartir una clave de texto: igualdad textual no prueba
identidad en el mundo real. Usa sesiones separadas cuando sus ámbitos difieran.

Todos los tipos incorporados tienen etiqueta española, por ejemplo
`[PERSONA_1]`, `[CORREO_1]`, `[CUENTA_1]`, `[IMPORTE_1]`, `[DATO_SENSIBLE_1]`.
Un tipo personalizado desconocido usa `[DATO_SENSIBLE_1]`, salvo que su etiqueta
se configure explícitamente. Los roles explícitos incluyen PACIENTE, MEDICO, FAMILIAR, CLIENTE, ACREEDOR,
DEUDOR, AGENTE, DEMANDANTE, DEMANDADO, TESTIGO, ABOGADO y JUEZ. El grafo conserva
`gender` únicamente cuando el reconocedor lo declara como `f` o `m`; la sesión
no deduce sexo ni género a partir del nombre. Las etiquetas personalizadas son
configuración de confianza: no deben contener datos reales.

El texto fuente que ya parece un marcador queda reservado. Si coincide con un
marcador emitido anteriormente, el procesamiento falla para evitar asociaciones
falsas. `session.reidentify(text)` restaura únicamente tokens emitidos por esa
sesión y disponibles en su bóveda; rechaza tokens desconocidos. El modo
`strict=False` deja esos tokens intactos y los enumera en `unknown`. La bóveda
guarda el primer valor original cuando varias representaciones NFC coinciden.

## Guardar y continuar

El procesamiento en memoria no requiere dependencias criptográficas. Para
persistir: `pip install 'deidflow[vault]'`. Genera una clave aleatoria de 32 bytes
y guárdala en un almacén de claves separado del archivo cifrado; sin ella no se
pueden recuperar el estado ni los originales.

```python
import secrets
from deidflow import DeidEngine
from deidflow.session import DeidSession

key = secrets.token_bytes(32)  # Conservar de forma segura fuera del archivo.
session.save("sesion-001.enc", key=key, ttl_seconds=3600)
session.close()

# También funciona en un proceso nuevo que recupere la misma clave.
resumed = DeidSession.load("sesion-001.enc", key=key, engine=DeidEngine())
next_result = resumed.deidentify("persona@example.test")
assert next_result.output_text == "[CORREO_1]"
restored = resumed.reidentify(next_result.output_text)
```

El archivo nuevo se crea con permisos privados y nunca sobrescribe otro.
AES-256-GCM autentica y cifra política, identidad de sesión, caducidad, clave del
asignador, contadores, tokens reservados, grafo y valores reversibles. La carga
rechaza metadatos desconocidos, estados incompletos, referencias inválidas,
archivos mayores de 64 MiB y una política proporcionada que difiera de la
guardada. Hay límites de 100 000 identidades, documentos, apariciones y relaciones;
cada relación admite hasta 128 referencias de evidencia. No se cargan objetos
Python, código ni modelos serializados.

`engine` se aporta de nuevo y debe ser de confianza. Si contiene `model_digest`,
o se pasa `model_digest=` al constructor, la carga exige el mismo digest SHA-256.
Los packs de dominio proporcionan ese identificador. En motores personalizados,
el identificador declara una configuración: no es una atestación independiente
de los pesos. Sin digest, la sesión no puede comprobar equivalencia de motores.
`policy=` opcional en `load` exige igualdad exacta; si se omite, se restaura la
política autenticada. Un cambio de política o del digest asociado al motor
durante una sesión se rechaza.

Una nueva caducidad puede acortar, nunca ampliar, la de la sesión actual.
Al caducar se borran sus estructuras en memoria y ya no puede continuar.
`close()` también limpia valores, asignador y grafo. Esto no garantiza borrado
seguro de todas las copias de cadenas de Python, no elimina archivos guardados
y no revoca snapshots anteriores: una copia previa sin caducidad sigue siendo
válida con su clave. No existe un registro externo contra restaurar versiones
anteriores. Continúa una sola línea de snapshots: dos procesos que parten de la
misma copia pueden asignar el siguiente token a valores distintos; no hay
coordinación entre procesos. Controla copias, acceso y retención fuera de la biblioteca.

`reversible=False` omite originales y permite guardar/restaurar solamente la
identidad y el grafo; `reidentify` queda deshabilitado. En modo reversible, la
bóveda en memoria predeterminada contiene originales: persistencia cifrada no
equivale a memoria protegida. `EncryptedVault` es opcional para cifrar sus
valores en memoria. Guardar sesiones solo admite las bóvedas incorporadas.
No modifiques directamente bóveda ni asignador de una sesión activa. Los
antiguos archivos `deidflow.vault.v2` son bóvedas, no snapshots de sesión: no
contienen el estado necesario para esta reanudación completa.

## Grafo y relaciones declaradas

`session.graph()` entrega una copia independiente con `schema_version=1`,
`session_id` y estas listas:

| Lista | Campos |
| --- | --- |
| `entities` | `id` (token), `type`, `role`, `gender` |
| `documents` | `id` opaco, `status`, `sequence` |
| `occurrences` | `id` opaco, `entity_id`, `document_id`, `start`, `end`, `output_start`, `output_end` |
| `relations` | `id` opaco, `source`, `target`, `relation`, `evidence_ids`, `provenance` |

Los offsets son índices de caracteres Python, de inicio inclusivo a fin exclusivo,
del texto fuente y de su salida respectivamente. Solo aparecen transformaciones
`indexed`; otros tratamientos de la política no crean identidades. `result.audit`
incluye `session_id`, `document_id` y `occurrence_ids` para enlazar registros.
El grafo no incluye originales, hashes de originales ni claves. Los vínculos,
tipos, roles, posiciones y frecuencias siguen siendo metadatos sensibles.

```python
result = resumed.deidentify("persona@example.test y otra@example.test")
evidence = result.audit["occurrence_ids"]
relation = resumed.relate("[CORREO_1]", "relacionado_con", "[CORREO_2]", evidence_ids=evidence)
```

`relate` es una declaración humana explícita: exige dos tokens emitidos distintos
y apariciones reales de ambos como evidencia. No interpreta el significado del
texto ni verifica que la relación sea verdadera; la persona que declara debe
revisarla. `provenance` solo admite `"human"`. Las relaciones admitidas son
`familiar_de`, `atiende_a`, `pertenece_a`, `representa_a`, `parte_de`, `titular_de`,
`contraparte_de` y `relacionado_con`. Nunca fusionan nodos ni añaden alias.

## Revisión humana en la misma sesión

Construye el plan con `create_review_plan(session.engine, source,
policy=session.policy, model_digest=...)`, prepara decisiones `ReviewDecision`
y aplícalas con `session.apply_review(source, plan, decisions, reviewer_id=...)`.
La sesión debe tener un digest de modelo. La operación devuelve `ReviewedText`
con `.result` y `.receipt`, utiliza el mismo asignador y registra correcciones
manuales en bóveda y grafo. `approve=True` y `source_complete=True` son
declaraciones humanas explícitas, sujetas todavía a las verificaciones del motor;
ninguna sesión las presupone. `signing_key=` permite firmar el recibo de revisión.
Un plan obsoleto o una operación fallida no conserva identidades a medio crear.
