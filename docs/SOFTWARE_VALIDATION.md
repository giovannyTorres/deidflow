# Validación de software de la candidata 0.6.0b1

Se ejecutó la suite integrada sobre la implementación congelada en el checkout
local `d5e6d260cf7ce379321a71cd24689a2519b6e073`. Los cambios posteriores de
esta entrega añaden evidencia y documentación. Los reportes vinculan el código
mediante su SHA-256 de fuentes Python:
`190ab7724f062a97fbf046286001ad4b0cfde0bb89135a80f47f4175a15026b5`.
Ese digest, los hashes de modelos y el árbol de la entrega permiten reproducir
la comprobación aunque el commit local no forme parte de la historia remota.

| Comprobación local | Resultado |
| --- | --- |
| Suite completa, incluidos OCR y spaCy reales | **1080 pruebas correctas, cero omitidas** |
| Cobertura de código | **86.56 %**, umbral exigido 78 % |
| Ruff y formato | Correctos |
| MyPy, Python 3.11 | Correcto, 64 módulos |
| Microbenchmark y recall exacto de tipos críticos | Correctos; EMAIL, CURP, RFC, CLABE y API_KEY al 100 % en ese fixture |
| Construcción de wheel y archivo fuente | Correcta; Twine 7 verifica ambos |
| Wheel en entorno nuevo sin extras y sin red | Tres modelos y enrutador cargados, sesiones en memoria y contexto comprobados |
| Persistencia sin el extra `vault` | Error explícito, sin archivo ni mutación de estado |
| `pip check` y vulnerabilidades conocidas | Correctos; cero vulnerabilidades encontradas en el entorno auditado |
| Licencias | Inventario de 106 distribuciones y atribuciones de modelos |

Las órdenes están en [la guía de auditoría](AUDIT_GUIDE.md). El entorno usa
Python 3.11.17 en Linux. Los [activos externos](validation-assets.json) incluyen
Tesseract 5.5.0 y `es_core_news_sm` 3.8.0; no se incluyen sus binarios o pesos en
el paquete. Los datos de las pruebas son ficticios. La matriz remota de GitHub
verifica adicionalmente Linux, Windows y macOS en Python 3.11–3.13; los activos
OCR/spaCy externos son opcionales y sus omisiones se reportan separadamente.

La revisión interna independiente reprodujo ataques de HTML/MIME, identidades,
persistencia, recibos y límites de direcciones. Las regresiones correspondientes
están en `tests/`. No se atribuye esa revisión a Claude Code: su auditoría externa
queda preparada en [CLAUDE.md](../CLAUDE.md).

Estos resultados validan mecanismos de software. La [evaluación de calidad](PRODUCT_EVIDENCE.md)
publica también omisiones de identificadores y pérdida de contexto; una suite
correcta no demuestra anonimato ni autoriza liberación automática.
