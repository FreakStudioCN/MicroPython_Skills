# Source: https://wiki.sipeed.com/maixpy/
# Purpose: Conservative YOLO + UART JSONL skeleton. User must provide MODEL_PATH.
import json
from maix import app, camera, display, err, image, nn, pinmap, uart


MODEL_PATH = "/root/models/yolov5s.mud"
UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)

detector = nn.YOLOv5(model=MODEL_PATH, dual_buff=True)
cam = camera.Camera(detector.input_width(), detector.input_height(), detector.input_format())
disp = display.Display()


def send_detection(label, score, x, y, w, h):
    payload = {
        "type": "object",
        "label": str(label),
        "score": float(score),
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
    }
    serial.write_str(json.dumps(payload) + "\n")


while not app.need_exit():
    img = cam.read()
    objs = detector.detect(img, conf_th=0.5, iou_th=0.45)
    for obj in objs:
        label = detector.labels[obj.class_id] if hasattr(detector, "labels") else str(obj.class_id)
        send_detection(label, obj.score, obj.x, obj.y, obj.w, obj.h)
        img.draw_rect(obj.x, obj.y, obj.w, obj.h, image.COLOR_RED)
        img.draw_string(obj.x, obj.y, label, image.COLOR_RED)
    disp.show(img)
