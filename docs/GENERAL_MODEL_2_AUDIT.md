# Auditoría reproducible de procedencia de es-general-2

Se revisó PR30 en `042c62b6b9108817cf1cd1f508de11b9daa92c7a`, comparado con
`f99cfce64a1a233f818caa6aef8efd1cc937277b`. La adopción se apoya en la
[comparación controlada](GENERAL_MODEL_COMPARISON.md), que mejora las regresiones
medidas bajo las mismas reglas y políticas. No demuestra ausencia de fugas:
el candidato conserva 88/600 documentos con alguna fuga directa anotada y los
paquetes requieren revisión humana.

## Archivo, licencia y entrenamiento declarado

| Comprobación | Resultado |
| --- | --- |
| Recurso candidato | `src/deidflow/models/es-general-2.json.gz`, 3,086,261 bytes |
| SHA-256 candidato | `f3008720a246e32b7a2adaf4af2ba9a03fb665caadcf698658b029a73042c173` |
| SHA-256 modelo anterior | `bf7e257f363e17bcc6bee943f9dfaa0cd67e502cf8ac3fd90140bdd916a51903` |
| Formato | JSON comprimido con gzip; perceptrón estructurado BIO, características `es-1` |
| Entrenamiento declarado | 9,246 documentos; 1,471,760 tokens; semilla 1729; `min_feature_docs=5` |
| Selección declarada | 1,252 documentos de validación; época 29/30; F1 exacto 0.864027 |
| Calibración declarada | Platt sobre 9,907 menciones de validación, objetivo de tipo y límites exactos |
| Ampliación sintética | 3,000 → 5,000 documentos; 21 → 51 familias de plantillas de entrenamiento |

El hash y los metadatos del archivo concuerdan con el
[reporte de entrenamiento](../benchmarks/results/tagger/training-report-general-2.json).
Ese reporte registra 449 menciones de entrenamiento y 64 de validación que no
se alinearon con la tokenización. Los metadatos y el reporte son declaraciones
del productor: verificarlos entre sí no reconstruye ni certifica la ejecución
del entrenamiento.

La atribución permanece en [NOTICE](../NOTICE). MEDDOCAN usa CC-BY-4.0,
revisión `783a6df385c975b328c99bcffb54196a9ba4078a`; sus particiones declaradas
son `train` para pesos y `dev` para selección. Gretel Spanish usa Apache-2.0,
revisión `7b844d16738527a04264f50214cb426a4cea0897` indicada en NOTICE; se declara
un holdout del 10% del entrenamiento elegido por hash del texto. Los manifiestos
de archivos declarados son, respectivamente:

- MEDDOCAN: `ba4823b70e231902fe7d865c1193607631eb0a2d1f30c8591a6fc523388d4cdc`.
- Gretel: `4226f8df4df63ba3bae639d9b18dc4c9e39a7fcbf27c99117409b4365b237c97`.

El generador del proyecto tiene licencia Apache-2.0 y emplea Faker 40.44.0
(MIT). Los datos personales de estos corpus se describen como sintéticos;
MEDDOCAN los inserta en casos clínicos publicados. No se incorporaron aquí
documentos públicos ni valores generados.

## Verificación independiente del generador

Se regeneraron en memoria los registros completos con semilla 1729 y Faker
40.44.0. Las 30 familias adicionales solo modifican entrenamiento; no equivalen
necesariamente a 30 géneros distintos. La validación y el test conservan los
mismos textos, menciones, identificadores y metadatos entre ambas revisiones.

| Comprobación | Resultado observado |
| --- | --- |
| Validación anterior frente a candidata | 600/600 registros idénticos |
| Test anterior frente a candidato | 600/600 registros idénticos |
| Textos idénticos entre los 5,000 de entrenamiento y validación | 0 |
| Textos idénticos entre los 5,000 de entrenamiento y test | 0 |
| Familias de entrenamiento compartidas con validación o test | 0 |
| SHA-256 de registros de validación | `2e0a18a96cc8489e69e12a06fafada6a2241d91a0b88afec41c14395829dc78e` |
| SHA-256 de registros de test | `a6b90c8f66fad7478faa643d195547652cd38b3942aa39cd9e4b0afa8f72371f` |

Estos hashes usan `dataclasses.asdict`, JSON con claves ordenadas, UTF-8,
`ensure_ascii=False` y separadores compactos. Son distintos de los hashes del
evaluador de aceptación, que usa otra representación de los registros.

La comprobación de textos exactos no descarta valores o entidades compartidos,
paráfrasis, ni contaminación entre corpus públicos. Tampoco acredita que el
test se haya evaluado una sola vez: sus casos se reutilizaron para diagnóstico
de reglas. Las mediciones actuales son regresiones observadas, no una muestra
independiente de documentos reales. No se repitió el entrenamiento ni se
buscaron umbrales durante esta revisión. PR30 conserva el perfil `balanced`,
pero cambia `assurance`; la comparación controlada solo evalúa `balanced`.

## Repetir las comprobaciones sin imprimir documentos

Ejecutar desde la raíz de un clon que contenga las dos revisiones indicadas,
con el extra `training` instalado y Faker 40.44.0. El script carga únicamente
los dos generadores desde Git y usa los módulos locales de esquemas y
validadores, que no cambiaron entre esas revisiones. No necesita red ni los
corpus públicos. Solo imprime hashes, conteos y comprobaciones agregadas.

```bash
PYTHONPATH=src python - <<'PY'
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

assert importlib.metadata.version("Faker") == "40.44.0"
old_rev = "f99cfce64a1a233f818caa6aef8efd1cc937277b"
new_rev = "042c62b6b9108817cf1cd1f508de11b9daa92c7a"
source = "src/deidflow/benchmarks/synthetic_es.py"
model_path = "src/deidflow/models/es-general-2.json.gz"
expected_model = "f3008720a246e32b7a2adaf4af2ba9a03fb665caadcf698658b029a73042c173"
expected_records = {
    "validation": "2e0a18a96cc8489e69e12a06fafada6a2241d91a0b88afec41c14395829dc78e",
    "test": "a6b90c8f66fad7478faa643d195547652cd38b3942aa39cd9e4b0afa8f72371f",
}

def git_bytes(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"])

def load_generator(directory, name, revision):
    path = Path(directory) / f"{name}.py"
    path.write_bytes(git_bytes(revision, source))
    module_name = f"deidflow.benchmarks.{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

asset = git_bytes(new_rev, model_path)
asset_hash = hashlib.sha256(asset).hexdigest()
assert asset_hash == expected_model
metadata = json.loads(gzip.decompress(asset))["metadata"]
report = json.loads(git_bytes(
    new_rev, "benchmarks/results/tagger/training-report-general-2.json"
))
assert report["model_sha256"] == asset_hash
assert report["training_data"] == metadata["training_data"]
assert report["selected_epoch"] == metadata["selected_epoch"] == 29
print(json.dumps({"model_sha256": asset_hash, "bytes": len(asset),
                  "training_report_matches_metadata": True}, sort_keys=True))

with tempfile.TemporaryDirectory() as directory:
    old = load_generator(directory, "audit_old", old_rev)
    new = load_generator(directory, "audit_new", new_rev)
    training = list(new.generate(5000, split="train", seed=1729))
    training_texts = {example.text for example in training}
    held_families = set().union(*new.HELD_OUT.values())
    train_families = {family for family, _ in new.TEMPLATES} - held_families
    observed_families = {example.template_id.split(":", 1)[0]
                         for example in training}
    assert observed_families == train_families
    assert len(train_families) == 51
    assert not train_families & held_families
    print(json.dumps({"train_documents": len(training),
                      "train_families": len(train_families),
                      "family_overlap": 0}, sort_keys=True))
    for split, expected in expected_records.items():
        before = [asdict(e) for e in old.generate(600, split=split, seed=1729)]
        after = [asdict(e) for e in new.generate(600, split=split, seed=1729)]
        assert before == after
        payload = json.dumps(after, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        assert digest == expected
        overlap = len(training_texts & {e["text"] for e in after})
        assert overlap == 0
        print(json.dumps({"split": split, "identical_records": len(after),
                          "records_sha256": digest,
                          "train_text_overlap": overlap}, sort_keys=True))
PY
```

La comparación de calidad tiene un procedimiento separado en
[GENERAL_MODEL_COMPARISON.md](GENERAL_MODEL_COMPARISON.md) y reportes
[JSON/CSV con índice de hashes](../benchmarks/results/general-model2-comparison/).
Congela código, reglas, políticas, corpus y perfil; solo sustituye el modelo
general de los paquetes general y jurídico. Sus resultados no deben mezclarse
con los reportes históricos de `Policy.strict()` en [TAGGER.md](TAGGER.md).
