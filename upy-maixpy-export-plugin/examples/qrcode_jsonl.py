# Source: https://wiki.sipeed.com/maixpy/
# Purpose: QR code detection skeleton with fixed UART JSONL fields.
import json
from maix import app, camera, display, err, pinmap, uart


UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)
cam = camera.Camera(640, 480)
disp = display.Display()


def bbox_from_code(code):
    if hasattr(code, "rect"):
        rect = code.rect()
        return rect[0], rect[1], rect[2], rect[3]
    if hasattr(code, "corners"):
        corners = code.corners()
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    return 0, 0, 0, 0


def send_qrcode(payload_text, x=0, y=0, w=0, h=0):
    payload = {
        "type": "qrcode",
        "label": str(payload_text),
        "score": 1.0,
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
    }
    serial.write_str(json.dumps(payload) + "\n")


while not app.need_exit():
    img = cam.read()
    for code in img.find_qrcodes():
        text = code.payload() if hasattr(code, "payload") else str(code)
        x, y, w, h = bbox_from_code(code)
        send_qrcode(text, x, y, w, h)
    disp.show(img)
