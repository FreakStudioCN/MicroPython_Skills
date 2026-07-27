# maix.nn

Official URL: https://wiki.sipeed.com/maixpy/api/maix/nn.html

Status: seed_reference

Brief: neural network module.

Stage A policy: may be used for conservative AI skeletons only when a task-specific reference and example are present. Do not generate model training, MaixHub automation, model conversion, automatic model download, or deployment.

Core result object conventions:

- Object detection results expose `x`, `y`, `w`, `h`, `class_id`, and `score`.
- Detector instances commonly expose `input_width()`, `input_height()`, `input_format()`, and `labels`.
- Prefer `camera.Camera(detector.input_width(), detector.input_height(), detector.input_format())` for model-backed camera loops.

Object detection surfaces:

```python
from maix import nn

detector = nn.YOLOv5(model="/root/models/yolov5s.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45)

detector = nn.YOLOv8(model="/root/models/yolov8n.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45, keypoint_th=0.5, sort=0)

detector = nn.YOLO11(model="/root/models/yolo11n.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45, keypoint_th=0.5, sort=0)

world = nn.YOLOWorld(model="", text_feature="", labels="", dual_buff=True)
objs = world.detect(img, conf_th=0.5, iou_th=0.45, sort=0)
```

Classification surfaces:

```python
classifier = nn.Classifier(model="/root/models/classifier.mud", dual_buff=True)
results = classifier.classify(img, softmax=True, fit=...)
```

Face detection/recognition surfaces:

```python
face_detector = nn.FaceDetector(model="/root/models/yolov8n_face.mud", dual_buff=True)
faces = face_detector.detect(img, conf_th=0.5, iou_th=0.45)

recognizer = nn.FaceRecognizer(
    detect_model="/root/models/yolov8n_face.mud",
    feature_model="/root/models/face_feature.mud",
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
recognizer.add_face(face, "label")
recognizer.save_faces("/root/models/faces.bin")
recognizer.remove_face(idx=-1, label="label")
```

OCR surfaces:

```python
ocr = nn.PP_OCR(model="/root/models/pp_ocr.mud")
cam = camera.Camera(ocr.input_width(), ocr.input_height(), ocr.input_format())
objects = ocr.detect(img, thresh=0.3, box_thresh=0.6, char_box=False)
one = ocr.recognize(img, box_points=[])
text = objects[0].char_str()
points = objects[0].box.to_list()
```

Codegen policy by task:

- `yolo_detection`: may generate code using YOLOv5 by default; YOLOv8/YOLO11/YOLOWorld require explicit user selection and model path.
- `face_recognition`: may generate a conservative skeleton using `FaceRecognizer`, but README must require detect model, feature model, and face database/enrollment preparation.
- `ocr`: may generate a conservative skeleton using `PP_OCR`, but README must require OCR model and language/font assets.
- `classifier`, `face_detector`, `tracker`, `speech`, LLM/VLM classes, and custom tensor workflows require their own task references before generation.

Restrictions:

- Do not claim a model exists on the device.
- Do not claim face labels or OCR dictionaries are already installed.
- Do not fabricate model filenames beyond clear placeholders or task-provided paths.
