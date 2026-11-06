# BMX-09: recibo de decisión operativa

Base: `2da847f710c175d84cc40284cbaa51a6b420527d`.
Estado: **decisión del solicitante ratificada; revisión documental pendiente**.
Fecha: `2026-11-06T18:02:28Z`. Responsable: `requester`.

La respuesta actual resuelve D1–D3; todos los formatos previstos ya eran
obligatorios por respuesta previa. La
[ADR 0001](../adr/0001-bmx-09-operational-profiles-v1.md) y el
[recibo JSON v1](../benchmark-mx/operational-decision-v1.json) registran
automático desde el inicio/global/adaptación local fácil, sensibilidad separada
de validez y perfiles contextual/estricto. La procedencia es la respuesta del
solicitante en esta sesión, resumida sin citas inventadas ni nombres nuevos.

Dirección personal completa y fecha personal exacta se retiran por defecto;
edad y otros cuasiidentificadores sin regla se escalan. Son derivaciones
conservadoras de ingeniería, no decisiones individuales atribuidas al
solicitante. La edad queda en `review_required` hasta acordar granularidad.

Global no amplía el corpus es-MX ni acredita soporte de otros idiomas/localidades.
El objetivo automático usa revisión dirigida ante ambigüedad/falta de soporte,
sin exigir revisión universal. No cambia producción ni sus controles existentes.

La calidad sigue sin ratificar: umbrales, soporte y custodia pertenecen a
BMX-25; el benchmark continúa `DESCRIPTIVE_ONLY`. La decisión operativa no
aprueba candidatos, versiones o ausencia de fuga.

## Comprobación documental

La matriz cubre identificador atribuible inválido, distractor no personal,
negación/dosis, dirección, fecha, edad y PDF sin soporte, con acciones,
precedencia, operadores, formatos, procedencia y límites.
No se ejecutaron pruebas del benchmark ni se crearon corpus/gold.

Revisión independiente de estándares y especificación: **pendiente**. Este
archivo no acredita su aprobación ni cierra BMX-10–12. La especificación
congelada conserva SHA-256
`898610c7c700f1a1f67154662e2b6526ddbce8fcd7e7f90f43e9631f120ee987`.
