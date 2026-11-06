"""Ejemplo local con dos notas clínicas ficticias; no usa LLM ni red.

Instalación: pip install 'deidflow[vault]'
Ejecución: python examples/context_session.py --output /ruta/nueva/ejemplo

Conserva dosis y negación, comprueba identidad entre notas y declara una relación
humana con sus apariciones como evidencia. Guarda y carga una sesión cifrada y
verifica la restauración dentro del proceso. Nunca imprime originales ni claves.
La clave de esta demostración solo vive en memoria: sus archivos cifrados no
podrán abrirse después de terminar. Para continuar entre ejecuciones, proporciona
la clave desde un gestor de secretos; la CLI también ofrece `deidflow keygen`.
Las salidas siguen pendientes de revisión humana; este ejemplo no las aprueba.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from deidflow import DeidSession, ReleaseStatus, get_domain_pack
from deidflow.private.security import protect

NOTE_1 = "Paciente: Ana López niega diabetes y toma metformina 500 mg. Médico: Luis Pérez."
NOTE_2 = "Paciente: Ana López mantiene metformina 500 mg y niega fiebre. Médico: Luis Pérez."


def write_private(path: Path, value: str | dict[str, Any]) -> None:
    """Crea un archivo privado; nunca sobrescribe otro."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        protect(path, directory=False)
        handle.write(text)


def demonstrate(output: Path) -> dict[str, Any]:
    if importlib.util.find_spec("cryptography") is None:
        raise ImportError("Instala deidflow[vault] para guardar y cargar sesiones cifradas")
    # La biblioteca incluye este modelo en español; no descarga ningún recurso.
    pack = get_domain_pack("clinical")
    key = secrets.token_bytes(32)
    with pack.session() as session:
        first = session.deidentify(NOTE_1, domain=pack.name)
        second = session.deidentify(NOTE_2, domain=pack.name)
        assert first.status == second.status == ReleaseStatus.REVIEW_REQUIRED
        assert first.output_text is not None and second.output_text is not None
        assert (
            "metformina 500 mg" in first.output_text and "metformina 500 mg" in second.output_text
        )
        assert "niega diabetes" in first.output_text and "niega fiebre" in second.output_text

        graph = session.graph()
        patient = next(item["id"] for item in graph["entities"] if item["role"] == "patient")
        clinician = next(item["id"] for item in graph["entities"] if item["role"] == "clinician")
        assert patient in first.output_text and patient in second.output_text
        assert clinician in first.output_text and clinician in second.output_text
        evidence = [
            item["id"]
            for item in graph["occurrences"]
            if item["document_id"] == first.audit["document_id"]
            and item["entity_id"] in {patient, clinician}
        ]
        # Declaración explícita basada en estas notas ficticias, nunca inferida.
        session.relate(clinician, "atiende_a", patient, evidence_ids=evidence)
        expected_graph = session.graph()
        assert "Ana López" not in json.dumps(expected_graph)
        assert "Luis Pérez" not in json.dumps(expected_graph)

        output.mkdir(mode=0o700, exist_ok=False)
        protect(output, directory=True)
        session.save(output / "sesion.enc", key=key, ttl_seconds=3600)
        write_private(output / "nota-1.candidata.txt", first.output_text)
        write_private(output / "nota-2.candidata.txt", second.output_text)
        write_private(output / "nota-1.auditoria.json", first.audit_dict())
        write_private(output / "nota-2.auditoria.json", second.audit_dict())

    # Otra instancia restaura contador, identidad, restricciones y relaciones.
    with DeidSession.load(
        output / "sesion.enc", key=key, engine=pack.engine(), policy=pack.policy()
    ) as resumed:
        assert resumed.graph() == expected_graph
        assert resumed.reidentify(second.output_text).text == NOTE_2
        write_private(output / "grafo.json", resumed.graph())
        resumed.save(output / "sesion-reanudada.enc", key=key)
        return {
            "estado": "REVISION_HUMANA_REQUERIDA",
            "documentos": len(expected_graph["documents"]),
            "entidades": len(expected_graph["entities"]),
            "relaciones_declaradas": len(expected_graph["relations"]),
            "continuidad_verificada": True,
            "restauracion_verificada": True,
            "aprobacion_automatica": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="Directorio nuevo; su padre debe existir"
    )
    args = parser.parse_args()
    try:
        result = demonstrate(args.output)
    except ImportError:
        print("Falta la dependencia opcional: instala deidflow[vault].", file=sys.stderr)
        return 3
    except FileExistsError:
        print(
            "La salida debe ser un directorio nuevo; no se sobrescribió el existente.",
            file=sys.stderr,
        )
        return 3
    except Exception:
        print(
            "El ejemplo no pudo completarse; revisa la configuración local en privado.",
            file=sys.stderr,
        )
        return 3
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
