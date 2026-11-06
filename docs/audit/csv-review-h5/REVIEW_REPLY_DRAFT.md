# Respuesta preparada para H5 en #32

Pendiente de envío al hilo real: la política de red bloquea `api.github.com`.
Este archivo no representa una respuesta publicada ni un hilo resuelto.

H5 corregido en `16813896250993360610e26bd89b1ed812250dab`: el ámbito de
documento se deriva una vez del plan completo y verificado del CSV. Cada celda
conserva sus comprobaciones de frescura, reescaneo y recibo firmado.

La reproducción exacta falló antes y pasó después: el mismo correo ficticio
en una celda y precedido de `Contacto:` en otra recibe el mismo token. Se
comprueban separación entre documentos, repetición del plan, ámbitos mayores,
rechazo de planes obsoletos y de recibos alterados.

Evidencia local: 1.127 pruebas aprobadas, 11 omitidas; Ruff, formato, mypy,
microbenchmark y wheel sin extras aprobados. Comandos y hashes en
[el acta](README.md) y [el recibo](health.json). Evidencia ficticia de desarrollo;
ninguna ejecución del test independiente. `merge origin/master` ya estaba al día.

Solicitada auditoría externa en el cuerpo preparado mediante
`Auditoría Claude: pendiente`. Falta publicar esa solicitud mediante la API,
verificar CI real 11/11, cerrar hallazgos e hilos y obtener aprobación de Giovanny.
