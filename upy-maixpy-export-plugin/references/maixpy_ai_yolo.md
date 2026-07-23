# MaixPy YOLO Reference

Official seed: https://wiki.sipeed.com/maixpy/

Status: seed_reference

YOLO generation uses `maix.nn` plus camera/display/UART references. Generate only a conservative skeleton that requires the user to provide an existing `.mud` model path. Do not train, download, or convert models.

Known safe shape:

```python
from maix import nn
detector = nn.YOLOv5(model="/root/models/yolov5s.mud", dual_buff=True)
objs = detector.detect(img, conf_th=0.5, iou_th=0.45)
```

Required README note:

```text
Place the trained MaixPy model under /root/models before running this script.
```
