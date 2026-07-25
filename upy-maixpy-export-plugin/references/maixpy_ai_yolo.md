# MaixPy YOLO Reference

Official URL: https://wiki.sipeed.com/maixpy/api/maix/nn.html

Task docs:

- https://wiki.sipeed.com/maixpy/doc/en/vision/yolov5.html

Status: seed_reference

YOLO generation uses `maix.nn` plus camera/display/UART references. Generate only a conservative skeleton that requires the user to provide an existing `.mud` model path. Do not train, download, convert, or upload models.

Default stage A shape:

```python
from maix import nn

detector = nn.YOLOv5(model="/root/models/yolov5s.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45)
```

Additional indexed detector families:

```python
detector = nn.YOLOv8(model="/root/models/yolov8n.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45, keypoint_th=0.5, sort=0)

detector = nn.YOLO11(model="/root/models/yolo11n.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45, keypoint_th=0.5, sort=0)

world = nn.YOLOWorld(model="", text_feature="", labels="", dual_buff=True)
objs = world.detect(img, conf_th=0.5, iou_th=0.45, sort=0)
```

Output object fields:

```python
obj.x
obj.y
obj.w
obj.h
obj.class_id
obj.score
detector.labels
```

Required README note:

```text
Place the trained MaixPy model under /root/models before running this script.
```

Codegen policy:

- Use `YOLOv5` unless the user explicitly selects another supported detector and supplies a matching model path.
- Do not claim the labels list is complete; use `detector.labels[obj.class_id]` only with bounds/fallback handling.
- For keypoint tasks, add a task-specific JSONL contract before emitting extra keypoint fields.
