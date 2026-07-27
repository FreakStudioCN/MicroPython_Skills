# MaixPy Face Recognition Reference

Official URL: https://wiki.sipeed.com/maixpy/doc/zh/vision/face_recognition.html

API URL: https://wiki.sipeed.com/maixpy/api/maix/nn.html

Status: seed_reference

Face recognition is supported by official MaixPy `maix.nn` APIs. If generated output says this API is unavailable, that is a Skill reference/readiness bug. Stage A may generate a conservative skeleton, but it must state the model files, face database, and enrollment workflow are manual prerequisites.

Required model/data prerequisites:

- Face detection model path, for example `/root/models/yolov8n_face.mud`.
- Face feature model path, for example `/root/models/face_feature.mud`.
- Face database path, for example `/root/models/faces.bin`.
- An enrollment workflow that calls `recognizer.add_face(...)` and `recognizer.save_faces(...)`; stage A does not automate enrollment.

Officially indexed API shape:

```python
from maix import nn

recognizer = nn.FaceRecognizer(
    detect_model=detect_model,
    feature_model=feature_model,
    dual_buff=True,
)
recognizer.load(detect_model, feature_model)
recognizer.load_faces("/root/models/faces.bin")
cam = camera.Camera(recognizer.input_width(), recognizer.input_height(), recognizer.input_format())
faces = recognizer.recognize(
    img,
    conf_th=0.5,
    iou_th=0.45,
    compare_th=0.8,
    get_feature=False,
    get_face=False,
)
recognizer.add_face(face, "Alice")
recognizer.save_faces("/root/models/faces.bin")
recognizer.remove_face(idx=-1, label="Alice")
```

Face object fields:

```python
face.x
face.y
face.w
face.h
face.class_id
face.score
recognizer.labels
```

Codegen policy:

- May generate a runtime skeleton using `nn.FaceRecognizer`, camera/display, and UART JSONL.
- Must not claim known identities exist unless a face database path is supplied and documented.
- Must keep `"unknown"` as a safe fallback label.
- Must check `fs.exists(face_db_path)` before `load_faces(...)` and wrap the returned error code with `err.check_raise(...)`.
- Must initialize camera with `recognizer.input_width()`, `recognizer.input_height()`, and `recognizer.input_format()`.
- Must not use invented APIs such as a custom `face_db.match(...)`.
