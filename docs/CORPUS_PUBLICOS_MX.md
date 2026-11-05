# Corpus públicos para datos médicos y financieros en español de México

Búsqueda del 2026-11-05 en Kaggle, Hugging Face, repositorios académicos y portales
de datos abiertos de México.

> **Conclusión:** no existe un corpus público de texto médico o financiero **mexicano**
> con datos personales anotados. Los corpus de notas clínicas mexicanas citados en
> artículos (UNAM-IIMAS; 98 notas de SEDESA en un trabajo del CIC-IPN) no se han
> liberado. El holdout mexicano (fase F3) tendrá que construirse con datos con
> consentimiento o licencia, por ejemplo en el piloto en modo sombra.

**Verificación:** la política de red de la sesión bloqueó huggingface.co, kaggle.com,
zenodo.org, physionet.org, inegi.org.mx, gob.mx, datamx.io y data.mendeley.com. Las
licencias y cifras de esta página vienen de resultados de búsqueda, no de las
páginas oficiales. Hay que confirmarlas antes de descargar o integrar cualquier fuente.

## Candidatos

| Recurso | País / tipo | Anotación de datos personales | Licencia según la búsqueda | Uso comercial | Uso recomendado |
|---|---|---|---|---|---|
| [MEDDOCAN](https://github.com/PlanTL-GOB-ES/SPACCC_MEDDOCAN) | España, casos clínicos con PHI sintética, 1,000 documentos | Sí, 22 tipos | CC-BY-4.0 | Sí, con atribución | Ya integrado: evaluación y entrenamiento |
| [Corpus de salud ocupacional seudonimizado](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11267746/) (Dunstan et al., 2024) | **Chile**, 1,787 anamnesis reales seudonimizadas | Sí, 10 categorías de datos personales | CC BY 4.0 ([registro UC](https://repositorio-az.uc.cl/dspace/items/b9a1bcb1-5801-490d-b464-729927e87b01/full)) | Sí, con atribución | **Mejor siguiente fuente**: es el único gold latinoamericano con datos personales anotados |
| [CARMEN-I](https://physionet.org/content/carmen-i/1.0.2/) | España/Cataluña, 2,000 informes reales con sustitutos sintéticos | Desidentificado; anota conceptos clínicos | PhysioNet, acceso bajo solicitud | Sin confirmar | Revisar el acuerdo de uso antes de usarlo |
| [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | Sintético, documentos financieros; unos 4,609 en español | Sí, spans de datos personales | Apache-2.0 | Sí | Entrenamiento y evaluación financiera; localismo mexicano sin confirmar |
| [Synthetic PII in Financial Documents](https://data.mendeley.com/datasets/tzrjx692jy/1) (Mendeley) | Sintético, financiero | Sí | Sin confirmar | Sin confirmar | Revisar idioma y licencia |
| [ai4privacy pii-masking](https://huggingface.co/datasets/ai4privacy/pii-masking-300k) | Sintético, incluye español de España | Sí | Propia: académica y no comercial | **No**, salvo contrato | Evitar sin licencia de ai4privacy |
| [Chilean Waiting List Corpus](https://zenodo.org/record/7555181) | Chile, 9,000 interconsultas | Solo entidades clínicas | CC BY-NC-SA 4.0 | **No** | Evitar en el producto comercial |
| [SPACCC-Spanish-NER](https://huggingface.co/datasets/IEETA/SPACCC-Spanish-NER) | España, casos clínicos | Entidades clínicas | CC-BY-4.0 | Sí | Contexto clínico, no datos personales |
| [Datos abiertos COVID-19](https://www.gob.mx/salud/documentos/datos-abiertos-152127) (DGE, Secretaría de Salud) y su [espejo en Kaggle](https://baselight.app/u/kaggle/dataset/riteshahlawat_covid19_mexico_patient_health_dataset) | **México**, registros individuales tabulares (sexo, edad, entidad, comorbilidades) | No hay texto ni nombres | Datos abiertos del Gobierno de México | Probable; verificar | Pruebas tabulares de cuasi-identificadores y riesgo |
| [Nombres y apellidos comunes en México](https://datamx.io/dataset/muestra-de-nombres-y-apellidos-comunes-en-mexico) (DataMX) | **México**, frecuencias | No aplica | CC0 (recurso de nombres de mujer) | Sí | Ampliar el catálogo de nombres de pila |
| [INEGI: DENUE y catálogos geoestadísticos](https://www.inegi.org.mx/inegi/terminos.html) | **México**, negocios con nombre y domicilio; estados, municipios y localidades | No aplica | Términos de libre uso del INEGI, con atribución | Probable; verificar | Catálogos de organizaciones y lugares |
| Catálogo CLUES de establecimientos de salud (DGIS) | **México**, nombres de hospitales y clínicas | No aplica | Sin confirmar | Sin confirmar | Catálogo de centros médicos si la licencia lo permite |
| Catálogo de códigos postales (Correos de México, antes SEPOMEX) | **México**, colonias y códigos postales | No aplica | Gratis para uso particular; **prohíbe comercializar y distribuir a terceros** | **No** | No incluirlo en el producto |
| [Listado del artículo 69-B (SAT)](https://www.sat.gob.mx/minisitio/DatosAbiertos/index.html) | **México**, contribuyentes reales con RFC, razón social y domicilio fiscal | No aplica | Publicación oficial | Uso de datos reales: revisar con un abogado | Solo pruebas locales de RFC y organizaciones; nunca en el repositorio |

## Plan de uso

1. **Evaluación latinoamericana inmediata:** adaptar el corpus chileno de salud ocupacional
   (CC BY 4.0) como segundo gold público, junto a MEDDOCAN. Es texto real seudonimizado
   con 10 categorías de datos personales: mide la fuga fuera de España.
2. **Entrenamiento del NER comercial (F2.2):** MEDDOCAN-train (CC-BY-4.0), el subconjunto
   en español de Gretel (Apache-2.0) y plantillas mexicanas sintéticas generadas con los
   nombres CC0 de DataMX y los catálogos del INEGI. Mantener separados los documentos
   de evaluación.
3. **Catálogos:** ampliar nombres (DataMX), lugares y organizaciones (INEGI) y centros
   médicos (CLUES, si su licencia lo permite). Excluir el catálogo de códigos postales.
4. **Holdout mexicano (F3):** no hay sustituto público. Se necesita un piloto en modo
   sombra con consentimiento o licencia, doble anotación y κ ≥ 0.80.
5. **Para descargar estas fuentes desde una sesión en la nube:** agregar sus dominios a
   *Allowed domains* en la configuración de red del entorno
   ([instrucciones](https://code.claude.com/docs/en/cloud-environments#network-access)).

## Otras fuentes consultadas

- [Revisión de corpus de desidentificación en español (medRxiv, 2020)](https://www.medrxiv.org/content/10.1101/2020.04.09.20058958v1.full.pdf)
  y el [conjunto de datos CARMEN-I en Scientific Data](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12215073/).
- Notas clínicas mexicanas no liberadas: [tesis UNAM](https://ru.dgb.unam.mx/bitstreams/f0ba8643-b6d9-4154-97d9-db18cb7ab2a4/download)
  y [extracción de síntomas, CIC-IPN](https://www.rcs.cic.ipn.mx/2021_150_5/Extraccion%20de%20sintomas%20en%20notas%20medicas%20escritas%20en%20espanol.pdf).
- Microdatos financieros agregados sin texto: [Banxico EconLab](https://www.banxico.org.mx/EconLab/microdatos).
