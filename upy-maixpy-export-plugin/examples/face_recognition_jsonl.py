# Purpose: Conservative face recognition placeholder.
#
# This file is not a complete runtime example. Face recognition needs model files,
# a face database/enrollment workflow, and version-specific MaixPy APIs. Use it
# only as a README/code-shape reminder until references/maixpy_ai_face_recognition.md
# is refreshed from official docs and examples.

MODEL_PREREQUISITES = [
    "Face recognition model files copied to /root/models",
    "Face database or enrollment data prepared on the MaixPy device",
    "Task-specific MaixPy face recognition API verified from local references",
]

JSONL_FIELDS = ("type", "label", "score", "x", "y", "w", "h")
