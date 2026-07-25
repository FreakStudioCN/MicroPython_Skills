# Source: https://wiki.sipeed.com/maixpy/api/maix/nn.html
# Source: https://wiki.sipeed.com/maixpy/doc/zh/vision/face_recognition.html
# Purpose: Conservative FaceRecognizer + UART JSONL skeleton.
#
# Prerequisites:
# - Face detection model copied to FACE_DET_MODEL.
# - Face feature model copied to FACE_FEAT_MODEL.
# - Optional face database copied to FACE_DB_PATH.
# - Enrollment is manual; this example does not add or save new faces.
import json
from maix import app, camera, display, err, fs, image, nn, pinmap, uart


FACE_DET_MODEL = "/root/models/yolov8n_face.mud"
FACE_FEAT_MODEL = "/root/models/face_feature.mud"
FACE_DB_PATH = "/root/models/faces.bin"
UART_DEVICE = "/dev/ttyS1"
BAUDRATE = 115200
TX_PIN = "A19"
RX_PIN = "A18"


err.check_raise(pinmap.set_pin_function(TX_PIN, "UART1_TX"), "Failed to set A19 as UART1_TX")
err.check_raise(pinmap.set_pin_function(RX_PIN, "UART1_RX"), "Failed to set A18 as UART1_RX")
serial = uart.UART(UART_DEVICE, BAUDRATE)

recognizer = nn.FaceRecognizer(
    detect_model=FACE_DET_MODEL,
    feature_model=FACE_FEAT_MODEL,
    dual_buff=True,
)
if fs.exists(FACE_DB_PATH):
    err.check_raise(recognizer.load_faces(FACE_DB_PATH), "Failed to load face database")
else:
    print("Face database not found; recognition labels will fall back to unknown:", FACE_DB_PATH)

cam = camera.Camera(recognizer.input_width(), recognizer.input_height(), recognizer.input_format())
disp = display.Display()


def label_for(face):
    labels = getattr(recognizer, "labels", [])
    idx = int(getattr(face, "class_id", 0))
    if 0 <= idx < len(labels):
        return labels[idx]
    return "unknown"


def send_face(label, score=0.0, x=0, y=0, w=0, h=0):
    payload = {
        "type": "face",
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
    faces = recognizer.recognize(img, conf_th=0.5, iou_th=0.45, compare_th=0.8)
    for face in faces:
        label = label_for(face)
        send_face(label, face.score, face.x, face.y, face.w, face.h)
        img.draw_rect(face.x, face.y, face.w, face.h, image.COLOR_GREEN)
        img.draw_string(face.x, face.y, label, image.COLOR_GREEN)
    disp.show(img)
