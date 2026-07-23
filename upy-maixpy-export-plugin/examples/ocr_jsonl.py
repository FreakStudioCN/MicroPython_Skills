# Purpose: Conservative OCR placeholder.
#
# This file is not a complete runtime example. OCR needs model files, fonts or
# dictionary assets, and version-specific MaixPy APIs. Use it only as a README
# prerequisite reminder until references/maixpy_ai_ocr.md is codegen-ready.

MODEL_PREREQUISITES = [
    "OCR model files copied to /root/models",
    "Font or dictionary assets copied to the expected MaixPy path",
    "Task-specific MaixPy OCR API verified from local references",
]

JSONL_FIELDS = ("type", "label", "score", "x", "y", "w", "h")
