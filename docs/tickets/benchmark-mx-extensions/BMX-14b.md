<!-- deidflow-benchmark:extension:BMX-14b -->
# BMX-14b: verificar los artefactos ODT/ODS reales y sus canales recuperables

**Gestor de destino:** GitHub Issues de `giovannyTorres/deidflow`.
**Estado de publicación:** borrador; no hay número ni URL de issue verificados.
**Estado de implementación:** pendiente; este documento no inicia el benchmark.
**Tipo:** tarea técnica. Etiqueta propuesta: `ready-for-agent`; no aplicada.

Esta extensión queda fuera del manifiesto congelado de los 27 tickets DF-EVAL-MX
v0.1.0. No renumera BMX-14/BMX-15 ni modifica sus hashes, la especificación o su
historial. Antecedentes: [BMX-14 DOCX](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/tickets/benchmark-mx/14-docx.md)
y [BMX-15 XLSX](https://github.com/giovannyTorres/deidflow/blob/f2e4751d280a100e5af450337d70db78a8fefa03/docs/tickets/benchmark-mx/15-xlsx.md).

## Dependencias

- Soporte ODT/ODS integrado en `master` mediante su PR auditado y aprobado;
  el código de referencia está en `claude/opendocument` `abb9601`.
- Fundamentos del benchmark integrados y auditados: admisión/referencia BMX-02,
  transformación BMX-05, pipeline real BMX-06, aislamiento BMX-07 y linaje BMX-08.
- Perfiles operativos versionados de BMX-09, manteniendo la calificación
  `DESCRIPTIVE_ONLY` hasta ratificar soporte, umbrales y custodia por separado.
- Para aprobar las pruebas Unicode del formato, la corrección H1/H2 debe estar
  integrada y auditada. No sustituirla por una normalización del gold.

Los IDs BMX y las ramas son referencias de trabajo, no issues remotos ni
pruebas de aprobación. GitHub API sigue inaccesible desde este entorno; publicar
este cuerpo cuando el acceso esté habilitado, comprobando antes duplicados y
resolviendo las dependencias a enlaces reales.

## Entrega observable

Un paquete ficticio ODT/ODS admitido pasa por el escritor real y produce un
informe local con filas separadas por formato y canal. La evaluación inspecciona
el **archivo serializado que se emitiría**, no una copia del texto extraído antes
de escribirlo. Un `APPROVED` con residuo sensible confirmado cuenta como fuga.

El inspector de referencia debe ser independiente del recorrido XML compartido
por lector/escritor productivos. Reusar ese recorrido como única verdad podría
ocultar el mismo canal dos veces. Fijar y versionar su inventario de partes,
localizadores, contenido inspeccionado y límites.

## Criterios de aceptación

- [ ] Evaluar ODT y ODS por separado, con soportes, cobertura, retiradas, residuos,
  conservación, éxito conjunto y estados de liberación; no mezclar denominadores.
- [ ] Inspeccionar texto de `content.xml`/`styles.xml`, texto dividido entre spans,
  espacios/tabulaciones/saltos ODF, cabeceras/pies, notas, anotaciones, revisiones,
  cuadros de texto y texto alternativo. Declarar qué canales se retiraron y qué
  contenido retenido se verificó.
- [ ] Inspeccionar nombres y referencias, propiedades, autores/fechas, campos,
  valores tipados y mostrados, fórmulas y resultados retenidos. En ODS incluir
  hojas/celdas ocultas, repeticiones, filtros, validaciones, formatos condicionales,
  nombres definidos y copias de tablas dinámicas/orígenes de datos admitidas.
- [ ] Verificar el inventario ZIP y el manifiesto de salida: configuraciones,
  miniaturas, firmas, macros, medios/objetos y enlaces externos se retiran o quedan
  explícitamente sin verificar. Un canal retenido no inspeccionado nunca permite
  una conclusión favorable.
- [ ] Las referencias usan localizadores estables por parte, hoja y celda o flujo;
  el informe utiliza IDs opacos, sin nombres de archivo, valores ni ubicaciones
  sensibles. Mantener linajes/grupos/particiones al generar variantes.
- [ ] Cubrir Cf/NFKC, entidades XML y valores divididos entre nodos/celdas con mapas
  a sus intervalos originales. Verificar ausencia de residuo en el artefacto y
  conservación del contexto no sensible, sin normalizar el texto puntuado.
- [ ] La salida ODS y `verify()` conservan `REVIEW_REQUIRED`; una revisión no exime
  residuos ni cobertura incompleta. Documentar las condiciones reales de ODT.
- [ ] Ejecución completamente local, sin documentos personales reales, descargas,
  inferencia o telemetría remotas, cambios de modelo ni dependencias innecesarias.
  Etiquetar estos fixtures como regresión ficticia conocida, no test independiente.

## Pruebas exigidas

- [ ] Fixture ODT con identificadores en spans, notas/comentarios/revisiones,
  metadatos y atributos: comprobar retiradas y conservación en el ZIP/XML emitido.
- [ ] Fixture ODS con un valor mostrado inocuo y una copia tipada sensible,
  fórmulas con literales/referencias externas y copias en criterios: el inspector
  detecta una copia residual incluso si el lector productivo no la presenta.
- [ ] Mismo correo en celdas/contextos distintos: identidad/token de documento
  consistente, con verificación por celda y sin inferir equivalencias de nombres.
- [ ] Candidata adversarial que devuelve `APPROVED` con una copia sensible oculta:
  informe de fuga y fallo de conformidad; borrar todo también falla conservación.
- [ ] Medios retenidos, parte desconocida, cifrado, miembros duplicados, DTD/entity
  y repetición expansiva: rechazo o cobertura incompleta sin crédito de éxito.
- [ ] Cf solicitados y anchura completa en texto, atributos, celdas y adjuntos;
  controles de formato residuales conservan revisión y los límites evitan ReDoS.
- [ ] Adjuntos `.odt`/`.ods` en EML: verificar tanto MIME/renombrado como el archivo
  adjunto real, propagando revisión o retirada sin otorgar éxito al original.
- [ ] Repetir con las mismas entradas/configuración conserva hashes y conteos.
  Esta repetición corresponde a generación/regresión de desarrollo. Un test
  independiente posterior se puntúa una sola vez por configuración y se informa.
  La apertura local en LibreOffice es una comprobación de compatibilidad
  complementaria y no reemplaza la inspección de privacidad.

## Cierre

Adjuntar comandos, SHAs de código/datos/inspectores, resultados y límites
sanitizados. El PR indica `Auditoría Claude: pendiente` y solo se fusiona con
CI 11/11 en verde, ningún hallazgo bloqueante de Claude abierto, todos los hilos
resueltos y aprobación de Giovanny. No publicar una versión ni modificar los
conjuntos de test o los detectores para mejorar las cifras de este ticket.
