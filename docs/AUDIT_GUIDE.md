# Auditoría reproducible de DeidFlow

Esta guía prepara la revisión externa solicitada por Giovanny. Su presencia no
significa que Claude Code haya auditado ni aprobado el código. El auditor debe
registrar el commit exacto, los comandos ejecutados y sus resultados.

## Contrato y superficie de cambios

Leer [AGENTS.md](../AGENTS.md), [contrato de producto](PRODUCT_ACCEPTANCE.md) y
[seguridad](security.md). La versión 0.6 añade:

- Paquetes locales clínico, financiero, jurídico inicial y general.
- Política de contexto y revisión humana exigida por código.
- Marcadores españoles, continuidad de identidad exacta compatible, sesiones
  cifradas y relaciones declaradas con evidencia.
- Correcciones humanas por offsets y recibos HMAC ligados a los artefactos.
- Adaptación del perceptrón, particiones separadas y gates antes de promoción.
- Evaluación conjunta de fuga, contexto, identidad y relaciones.

Los resultados finales y los errores restantes están en
[evidencia del producto](PRODUCT_EVIDENCE.md), con reportes JSON/CSV y digests.
La [validación de software](SOFTWARE_VALIDATION.md) registra pruebas, cobertura,
paquete y dependencias de la implementación entregada.

La base de trabajo fue `7d35654044f670d2f7cddab315428d01d803ed4e`, que ya contiene
la corrección de criterios y fórmulas compartidas XLSX. Se incorporó el modelo
general del [PR #25](https://github.com/giovannyTorres/deidflow/pull/25) tras
reproducir sus métricas de 600 documentos sintéticos. Se incorporaron después los cambios concurrentes de
[HTML #26](https://github.com/giovannyTorres/deidflow/pull/26) y
[correo #28](https://github.com/giovannyTorres/deidflow/pull/28), hasta
`362a902871ed61538043d28ac1cd7dbe5bfba891`, y después direcciones y rendimiento HTML
de #27 y #29 hasta `f99cfce64a1a233f818caa6aef8efd1cc937277b`.
La [revisión de las 24 ramas](BRANCH_REVIEW_v060.md) registra las decisiones.
La revisión confirmó canales de fuga
en sintaxis HTML/CSS y MIME, por lo que esas rutas reciben controles adicionales
y requieren revisión incluso cuando la reverificación no detecta residuos.

## Ejecutar las comprobaciones

En un checkout limpio y un entorno aislado Python 3.11–3.13:

```sh
python -m pip install '.[dev,pdf,ocr,tables,yaml,training,benchmarks,nlp,vault]'
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m mypy --python-version 3.11 src/deidflow
python -m pytest -q -ra --cov=deidflow --cov-report=term --cov-fail-under=78
python scripts/benchmark_micro.py --check
python -m build
python -m pip_audit --skip-editable
python scripts/audit_licenses.py
```

Probar también el wheel en un entorno nuevo sin extras ni red: importar el
paquete, cargar los modelos incorporados, procesar un texto, mantener marcadores
en memoria y comprobar que NumPy, spaCy y cryptography no son dependencias
obligatorias. La persistencia debe solicitar explícitamente el extra `vault`.
El workflow de CI prueba nueve combinaciones de sistema/Python, paquete,
vulnerabilidades conocidas y licencias.

Las pruebas reales de OCR y spaCy requieren activos externos. Configurar
`DEIDFLOW_TEST_TESSERACT`, `DEIDFLOW_TEST_TESSDATA_DIR` y
`DEIDFLOW_TEST_SPACY_MODEL`, registrando versiones, licencias y hashes. No ocultar
omisiones ni sustituirlas por el resultado de un adaptador ficticio. Cambiar de
versión OCR puede cambiar la confianza de un reconocimiento y exigir revisión;
no se debe bajar un umbral para hacer que un fixture quede aprobado.
Los [activos de validación registrados](validation-assets.json) identifican el
OCR, idiomas y modelo externo usados en la integración local; no se distribuyen
esos binarios o pesos externos dentro de DeidFlow.

## Reproducir las mediciones

```sh
python scripts/benchmark_context.py --pipeline domains --profile balanced \
  --checkpoint-between-documents \
  --compare-to benchmarks/results/context-baseline-v050b1.json \
  --output /tmp/context-candidate.json --csv /tmp/context-candidate.csv
python scripts/adapt_span_tagger.py demo --output /tmp/adaptation-demo
python scripts/benchmark_domain_regression.py --documents 600 --seed 1729 \
  --output /tmp/domain-regression.json --csv /tmp/domain-regression.csv
python examples/context_session.py --output /tmp/context-example
```

Usar destinos nuevos. El benchmark de contexto liga corpus, modelos, recursos
y fuentes Python; registra si el checkout tiene cambios sin commit. Para una
comparación histórica, ejecutar cada versión en su checkout con el mismo corpus.
El ejemplo de adaptación es ficticio: demuestra el mecanismo y debe quedar
bloqueado para promoción real. No cuenta como mejora de un modelo incorporado.

## Casos que merecen revisión adversarial

1. PII retenida dentro de una sustitución configurable: no debe quedar exenta
   de reverificación por llamarse `generalize`.
2. Token literal en la fuente, token desconocido, clave incorrecta, instantánea
   manipulada/caducada, contadores inconsistentes y referencias cruzadas inválidas.
3. Cambio de rol/género conocido a desconocido y contradicción explícita: la
   continuidad no debe fusionar identidades incompatibles ni adivinar alias.
4. Fallo a mitad de una operación: no debe restaurar secretos después de cerrar
   una sesión caducada, ni publicar una salida parcial o sobrescribir otra.
5. Negaciones, dosis, parentescos, nombres coordinados e importes: verificar
   cobertura de identificadores y conservación del texto por separado.
6. Recibo editado, fuente distinta, política/modelo distinto, decisiones faltantes
   y firma incorrecta: no deben autorizar liberación.
7. Identidades/grupos/textos repetidos entre particiones, métricas no finitas,
   categorías sin soporte y exposición previa del modelo a los holdouts.
8. Un mapa de offsets que declara un marcador pero conserva parte del original:
   el evaluador no debe conceder eliminación completa ni éxito conjunto.
9. HTML con atributos desconocidos, CSS adversarial, comentarios malformados y
   esquemas URL ofuscados; MIME con codificación inválida o metadatos ocultos.
   Las excepciones para metadatos de correo regenerados deben depender de esa
   ejecución y de su ubicación, nunca solo de que parezcan un token válido.

La revisión interna encontró y añadió regresiones para estas clases de error;
una auditoría externa debe volver a comprobarlas y buscar otras. Los controles
de software no establecen que el detector reconozca todos los identificadores.

## Qué no concluir

No convertir una suite verde, F1 alto o cero fugas en 40 casos ficticios en una
promesa de anonimato. No describir el paquete jurídico como modelo especialista
validado. No afirmar que una revisión de texto certifica un contenedor Office o
PDF. No equiparar hashes con autenticidad de un editor desconocido ni HMAC con
identidad humana probada. No publicar datasets privados ni claves en el reporte.
