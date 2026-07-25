# maix.tracker

Official URL: https://wiki.sipeed.com/maixpy/api/maix/tracker.html

Status: seed_reference

Brief: tracker module.

Stage A policy: indexed for future tracking workflows. Do not generate tracker code unless the user explicitly requests tracking and the detection object mapping is clear.

Officially indexed callable surface:

```python
from maix import tracker

obj = tracker.Object(x, y, w, h, class_id, score)
track = tracker.Track(id, score, lost, start_frame_id, frame_id)
bt = tracker.ByteTracker(max_lost_buff_num=60, track_thresh=0.5, high_thresh=0.6, match_thresh=0.8, max_history=20)
tracks = bt.update([obj])
```

Codegen guidance:

- YOLO result objects must be converted to `tracker.Object` deliberately.
- Tracking IDs should be added as optional JSONL metadata only after the receiver contract supports extra fields.
