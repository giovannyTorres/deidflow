# Comparación controlada de es-general-1 y es-general-2

La actualización concurrente PR30 (`042c62b6b9108817cf1cd1f508de11b9daa92c7a`)
añadió 30 familias sintéticas de entrenamiento y sustituyó el modelo general.
Para comprobar regresiones se cargó su archivo mediante `SpanTagger.load`,
verificando SHA-256 `f3008720a246e32b7a2adaf4af2ba9a03fb665caadcf698658b029a73042c173`.

Se mantuvieron el código `d5e6d260cf7ce379321a71cd24689a2519b6e073`, el
perfil `balanced` sin márgenes, las reglas, las políticas y los mismos corpus
anteriores. Solo cambió el adaptador NLP de los paquetes general y jurídico.
Los paquetes clínico y financiero conservaron sus modelos. El registro de
recursos del runtime sigue mostrando es-general-1 porque ese es el checkout
congelado; el modelo candidato externo tiene su digest separado y verificado.

| Medida, mismos 600 documentos | es-general-1 | es-general-2 |
| --- | ---: | ---: |
| Caracteres directos eliminados | 97.419% | 98.263% |
| Menciones directas completamente sustituidas | 95.314% | 96.457% |
| Documentos con fuga directa anotada | 113/600 | **88/600** |
| Caracteres no sensibles conservados | 99.196% | 99.468% |
| Revisión requerida / bloqueados | 595 / 5 | 598 / 2 |
| Aprobados automáticamente | 0 | 0 |

Ambas configuraciones conservan los resultados de los 40 casos de contrato:
102/102 menciones con marcador exacto y tipo correcto, 96/96 fragmentos de
contexto, 4357/4357 caracteres no sensibles, 51/51 pares de identidad, 20/20
relaciones declaradas y 20/20 guardados/cargas cifrados. El guard de inferencia
registró cero intentos de red.

Los [reportes JSON/CSV y su índice](../benchmarks/results/general-model2-comparison/)
permiten auditar la comparación. El corpus amplio conserva digest de textos
`b8b1d35298405dbfb16dec2febd2fbed5fc5d18b2140dd1e1983a1109477ddb3`
y de registros anotados
`26d6691616d4c4f05f8d24fd28b0a9ae7a12e9a50b308d81586c1fe69d659a05`.

La medición apoya adoptar el candidato porque mejora privacidad y conservación
de contexto en estas regresiones, sin perder el contrato comprobado. **Quedan
88 documentos con fuga directa anotada (14.67%)**, todos pendientes o bloqueados;
la adopción no autoriza liberación automática. Son casos ya observados durante
el desarrollo de reglas: usarlos para decidir la actualización no los convierte
en evidencia independiente del desempeño real. No se entrenó, calibró ni
buscaron umbrales durante esta comparación. El perfil `assurance` cambió en
PR30 y no está evaluado por estas cifras de `balanced`.

La corrida registrada usó el commit local `d5e6d26`. Para reproducirla desde un
clon remoto se usa `875a76c88e9d36a3ab4270f99f46c8a373006a8e`, disponible en
la rama publicada. Ambos tienen el mismo árbol `src` y digest Python
`190ab7724f062a97fbf046286001ad4b0cfde0bb89135a80f47f4175a15026b5`;
no se ha cambiado retroactivamente la procedencia de la corrida.

Para repetir con la misma versión de Faker (40.44.0), desde el checkout final:

```bash
git worktree add --detach /tmp/deidflow-general-reference \
  875a76c88e9d36a3ab4270f99f46c8a373006a8e

PYTHONPATH=/tmp/deidflow-general-reference/src \
  python scripts/compare_general_candidate.py \
  --candidate-model src/deidflow/models/es-general-2.json.gz \
  --candidate-sha256 f3008720a246e32b7a2adaf4af2ba9a03fb665caadcf698658b029a73042c173 \
  --candidate-revision 042c62b6b9108817cf1cd1f508de11b9daa92c7a \
  --output /tmp/general-model-comparison.json
```

Los nuevos reportes de aceptación ejecutan los paquetes incorporados con su pin
actualizado; esta comparación conserva por separado la evidencia histórica del
cambio de modelo bajo reglas constantes.
