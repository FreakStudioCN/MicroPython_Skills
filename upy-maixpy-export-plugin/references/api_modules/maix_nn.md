# maix.nn

Official URL: https://wiki.sipeed.com/maixpy/api/maix/nn.html

Status: seed_reference

Brief: neural network module.

Stage A policy: may be used for YOLO skeletons only when `references/maixpy_ai_yolo.md` and `examples/yolo_uart_jsonl.py` are present. Do not generate model training, MaixHub automation, or automatic model download.

Known safe surface:

```python
from maix import nn
detector = nn.YOLOv5(model="/root/models/yolov5s.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45)
```

Face recognition and OCR require task-specific references and model prerequisites.
