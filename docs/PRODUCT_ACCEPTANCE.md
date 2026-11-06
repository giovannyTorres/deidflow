# Contrato de producto

DeidFlow transforma documentos en español para poder analizarlos conservando
su sentido, con identificadores sustituidos por marcadores legibles. Funciona
sin LLMs, llamadas remotas ni servicios de pago. Código Apache-2.0; modelos y
fuentes con atribución y licencia explícitas.

## Comportamientos verificables

| Necesidad | Criterio de aceptación |
| --- | --- |
| Marcadores en español | Todas las categorías tienen etiqueta española; dos entidades distintas no comparten marcador. |
| Contexto | Los caracteres fuera de los intervalos transformados permanecen idénticos; negaciones, dosis, importes y relaciones se miden por separado. |
| Identidad estable | La misma identidad exacta mantiene su marcador dentro de la sesión y después de guardarla y cargarla. Los alias no se adivinan. |
| Relaciones | El grafo conserva entidades, menciones y relaciones declaradas con referencias verificables; no incluye valores originales. |
| Guardado | Estado autenticado y cifrado, rechazo de claves equivocadas, manipulación, caducidad y esquemas inválidos. |
| Dominios | Paquetes clínico, financiero, jurídico y general con modelo, política, versión, fuentes y límites consultables. |
| Correcciones | Un revisor puede añadir omisiones y corregir falsos positivos; los recibos quedan ligados a fuente, salida, política y evidencia. |
| Postentrenamiento | Entrenamiento local reproducible, particiones separadas, artefactos por versión y evaluación de regresión antes de activar. |
| Instalación | El wheel base funciona sin NumPy, spaCy, red ni credenciales. Cifrado, entrenamiento y formatos ampliados son extras. |
| Auditoría | Pruebas reproducibles y resultados medidos sobre el commit entregado, con omisiones y fallos visibles. |

## Lo que significa conservar contexto

Conservar texto fuera de los intervalos modificados es una propiedad mecánica
comprobable. Elegir correctamente esos intervalos es un problema de detección
y revisión. Un falso positivo puede eliminar información útil; un falso negativo
puede filtrar un identificador. Por eso se miden ambos, además de la consistencia
de marcadores y las relaciones. La evaluación no recompensa eliminar todo el
documento como si fuera un buen resultado de privacidad.

Las fechas, edades, ubicaciones y relaciones pueden permitir reidentificación
incluso después de sustituir nombres. Las políticas hacen explícita esa elección.
La seudonimización reversible no convierte datos personales en datos anónimos.

## Evidencia y activación

Los casos ficticios comprueban contratos y regresiones. Los corpus públicos
anotados aportan evidencia en sus dominios; no representan automáticamente
expedientes mexicanos reales. Un modelo adaptado requiere una evaluación
separada y representativa, además de superar las pruebas de software. Los
artefactos se preparan para revisión y no se activan por obtener un F1 elevado.

La [evidencia de la candidata 0.6](PRODUCT_EVIDENCE.md) presenta resultados,
denominadores, errores restantes y digests para este contrato: 40 casos fijos,
600 documentos de regresión, 600 de validación y una adaptación ficticia.
