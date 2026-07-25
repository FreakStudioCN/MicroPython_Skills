# Source: https://wiki.sipeed.com/maixpy/doc/en/vision/find_blobs.html
# Source: https://wiki.sipeed.com/maixpy/api/maix/image.html
# Purpose: Color blob skeleton with fixed UART JSONL fields. Tune thresholds in real light.
import json
from maix import app, camera, display, err, image, pinmap, uart


UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"
THRESHOLDS = [[0, 80, 40, 80, 10, 80]]


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)
cam = camera.Camera(640, 480)
disp = display.Display()


def blob_value(blob, index, method):
    if hasattr(blob, method):
        return getattr(blob, method)()
    return blob[index]


def send_blob(label, x, y, w, h):
    payload = {
        "type": "color",
        "label": str(label),
        "score": 1.0,
        "x": int(x),
        "y": int(y),
        "w": int(w),
        "h": int(h),
    }
    serial.write_str(json.dumps(payload) + "\n")


while not app.need_exit():
    img = cam.read()
    blobs = img.find_blobs(THRESHOLDS, pixels_threshold=500)
    for blob in blobs:
        x = blob_value(blob, 0, "x")
        y = blob_value(blob, 1, "y")
        w = blob_value(blob, 2, "w")
        h = blob_value(blob, 3, "h")
        send_blob("color_blob", x, y, w, h)
        img.draw_rect(x, y, w, h, image.COLOR_RED)
    disp.show(img)
