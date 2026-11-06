> **Registro histórico de la rama de implementación.** Este texto describe
> el trabajo conservado en [`f2e4751`](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/audit/BMX-09-decisions-for-review.md),
> no una implementación incorporada a `master` ni una auditoría o CI de esta PR.
> Los enlaces fijados al commit permiten consultar evidencia que no se copia aquí.
> Consulte el [estado de esta revisión](benchmark-spec/README.md).

# BMX-09: decisiones operativas ratificadas

El solicitante resolvió D1–D3: objetivo automático, global y fácilmente
reentrenable/ajustable localmente; acepta protección de identificadores inválidos
atribuibles, revisión de ambigüedad y conservación de distractores documentados;
acepta perfiles clínicos contextual y estricto. Todos los formatos, incluido
OCR, ya eran obligatorios. No se exige revisión universal de cada salida.

La [ADR 0001](../adr/0001-bmx-09-operational-profiles-v1.md) registra reglas,
derivaciones conservadoras, escenarios y matriz. El
[recibo JSON versionado](../benchmark-mx/operational-decision-v1.json) registra
responsable de rol, fecha y procedencia sin datos personales nuevos.

El alcance medido de esta etapa sigue siendo es-MX. La calidad no está
ratificada: DESCRIPTIVE_ONLY hasta BMX-25. Objetivo automático no equivale
a aprobación del candidato actual. Los perfiles ejecutables derivados pueden
seguir siendo configuraciones técnicas no ratificadas individualmente; la
decisión operativa superior sí está ratificada.

El estado pendiente del commit 2da847f queda como historial, sustituido por
esta decisión explícita. BMX-10 y BMX-11 quedan desbloqueadas tras cerrar
la revisión documental de BMX-09; BMX-12 conserva sus dependencias.
