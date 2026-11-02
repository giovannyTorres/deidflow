"""Run: python examples/rag_preprocessing.py. Requires no LLM or external service."""

from deidflow import DeidEngine, Policy

engine = DeidEngine()
source = "Paciente: Ana Ejemplo. Correo: ana@example.test. Diagnóstico: diabetes."
result = engine.deidentify_text(source, policy=Policy.strict())
print(result.audit_dict())
if result.release_approved:
    # Pass only approved content to a caller-owned chunker/vector store.
    documents_for_indexing = [result.output_text]
else:
    print("Indexing held for policy review or a locally installed semantic model.")
