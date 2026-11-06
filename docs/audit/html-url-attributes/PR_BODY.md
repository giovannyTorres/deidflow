Conserva exactamente las URL con `%xx` y los atributos que no cambian. Proyecta reemplazos de datos codificados al atributo original; encierra entre comillas el valor completo al reescribir un atributo sin comillas. Mantiene la protección de esquemas peligrosos y corrige la proyección de referencias sin punto y coma.

Auditoría Claude: pendiente

SHA de código: `ad9d72abb8bd4b9914385039840678846c1876a5`. Base: `44d04b16fb1ec545161c4ef0c14f516c7b0d9d29`.

| Comprobación | Evidencia |
| --- | --- |
| Suite completa | 1105 pasan; 11 omitidas; 280.90 s |
| Cobertura combinada | 84.11 %; umbral 78 % |
| Ruff / formato / mypy / pip check | Pasan |
| Microbenchmark ficticio de CI | Pasa; 1.321104 ms/registro; ratio 3.223469; recall crítico 1.0 |
| Wheel y sdist; twine estricto | Pasan; build del SHA de código indicado |
| Wheel sin extras fuera del checkout | Smoke de CI y reproducción específica pasan; cero intentos de red |

Comandos, alcance, hashes y límites: [README de auditoría](https://github.com/giovannyTorres/deidflow/blob/fix/html-url-attributes/docs/audit/html-url-attributes/README.md) y [health.json](https://github.com/giovannyTorres/deidflow/blob/fix/html-url-attributes/docs/audit/html-url-attributes/health.json) en `docs/audit/html-url-attributes/`. Evidencia exclusivamente ficticia de desarrollo; cero ejecuciones del test independiente. Sin nuevas dependencias, modelos, cambio de API pública ni publicación.

Comandos ejecutados: `python -m ruff check .`; `python -m ruff format --check .`; `python -m mypy --python-version 3.12 src/deidflow`; `python -m pip check`; `python -m pytest -q --basetemp=… --cov=deidflow --cov-branch --cov-fail-under=78`; `python scripts/benchmark_micro.py --check`; `python -m build --no-isolation`; `python -m twine check --strict`; smoke del wheel sin extras y reproducción específica fuera del checkout. Las rutas completas se documentan en el acta.

Revisión interna Matt: Standards 0 pendientes; Spec 0 pendientes. No es aprobación de Claude.

- [ ] CI 11/11 verde.
- [ ] Ningún hallazgo bloqueante de Claude abierto.
- [ ] Todos los hilos resueltos.
- [ ] Aprobación de Giovanny.
