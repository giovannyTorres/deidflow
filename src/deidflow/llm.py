"""Compatibility imports for the local session API; no LLM dependency or call.

Use ``deidflow.session`` for new applications. The optional prompt constant is
retained for existing clients and does not invoke any external service.
"""

from deidflow.session import DeidSession, ReidentifyResult

SYSTEM_PROMPT_ES = (
    "Los textos entre corchetes como [PERSONA_1], [MEDICO_1] o [LUGAR_2] son marcadores "
    "que sustituyen datos personales. Consérvalos exactamente como aparecen, no intentes "
    "adivinar su contenido y usa el mismo marcador cada vez que te refieras a esa entidad."
)

__all__ = ["SYSTEM_PROMPT_ES", "DeidSession", "ReidentifyResult"]
