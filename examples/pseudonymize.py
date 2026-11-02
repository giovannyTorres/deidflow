"""A caller owns secret storage and scope IDs; this demo generates an ephemeral key."""

import secrets

from deidflow import DeidEngine, Policy, Rule

engine = DeidEngine(key=secrets.token_bytes(32), tenant_id="demo", dataset_id="example")
policy = Policy(default=Rule("pseudonym"), token_scope="dataset")
a = engine.deidentify_text("correo: example@example.test", policy=policy)
b = engine.deidentify_text("correo: example@example.test", policy=policy)
assert a.output_text == b.output_text
print(a.audit_dict())
