"""PDFium requires process-wide serialization, including separate documents."""

import threading

PDFIUM_LOCK = threading.RLock()
