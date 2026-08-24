#!/usr/bin/env python3
import argparse
import json
import sys


BOARD_ID = "waveshare_esp32_s3_touch_lcd_2"
EXPECTED_JOINTS = {
    "left_arm",
    "right_arm",
    "left_leg_upper",
    "right_leg_upper",
    "left_leg_lower",
    "right_leg_lower",
}
HARD_RESERVED_PINS = {
    0,
    1,
    5,
    19,
    20,
    *range(26, 41),
    42,
    43,
    44,
    45,
    47,
    48,
}
DEFAULT_RECLAIMED_PINS = {2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}


def read_json(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def error(errors, code, message, path=None, details=None):
    item = {"code": code, "message": message}
    if path is not None:
        item["path"] = path
    if details:
        item["details"] = details
    errors.append(item)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_pin(pin, role, claims, errors):
    if not integer(pin) or not 0 <= pin <= 48:
        error(errors, "ROBOT_PIN_INVALID", "GPIO must be an integer from 0 to 48", role)
        return
    if pin in HARD_RESERVED_PINS:
        error(errors, "ROBOT_PIN_RESERVED", "GPIO is reserved by the target board", role, {"pin": pin})
    previous = claims.get(pin)
    if previous is not None:
        error(
            errors,
            "ROBOT_PIN_CONFLICT",
            "GPIO is assigned to more than one robot signal",
            role,
            {"pin": pin, "other_role": previous},
        )
    else:
        claims[pin] = role


def validate_servo(item, index, claims, errors):
    path = "servos[%s]" % index
    if not isinstance(item, dict):
        error(errors, "ROBOT_SERVO_INVALID", "Servo entry must be an object", path)
        return
    validate_pin(item.get("pin"), path + ".pin", claims, errors)
    if item.get("frequency_hz") != 50:
        error(errors, "ROBOT_PWM_FREQUENCY_INVALID", "Direct servos must use 50 Hz PWM", path + ".frequency_hz")
    pulse_values = [item.get("min_us"), item.get("center_us"), item.get("max_us")]
    if not all(integer(value) for value in pulse_values) or not pulse_values[0] < pulse_values[1] < pulse_values[2]:
        error(errors, "ROBOT_SERVO_PULSE_INVALID", "Require integer min_us < center_us < max_us", path)
    angles = [item.get("min_angle"), item.get("safe_angle"), item.get("max_angle")]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in angles):
        error(errors, "ROBOT_SERVO_ANGLE_INVALID", "Servo angles must be numeric", path)
    elif not angles[0] <= angles[1] <= angles[2]:
        error(errors, "ROBOT_SERVO_ANGLE_INVALID", "Require min_angle <= safe_angle <= max_angle", path)
    speed = item.get("max_speed_deg_s")
    if not isinstance(speed, (int, float)) or isinstance(speed, bool) or speed <= 0:
        error(errors, "ROBOT_SERVO_SPEED_INVALID", "max_speed_deg_s must be positive", path + ".max_speed_deg_s")
    if not isinstance(item.get("inverted"), bool):
        error(errors, "ROBOT_SERVO_INVERTED_INVALID", "inverted must be boolean", path + ".inverted")


def validate_profile(profile):
    errors = []
    warnings = []
    claims = {}
    if not isinstance(profile, dict):
        return {
            "ok": False,
            "board_id": None,
            "claims": {},
            "errors": [{"code": "ROBOT_PROFILE_INVALID", "message": "Profile must be an object"}],
            "warnings": [],
        }

    if profile.get("board_id") != BOARD_ID:
        error(
            errors,
            "ROBOT_BOARD_UNSUPPORTED",
            "Profile must target the MicroPythonOS Waveshare 2-inch board",
            "board_id",
            {"expected": BOARD_ID, "actual": profile.get("board_id")},
        )

    camera = profile.get("camera")
    if not isinstance(camera, dict) or camera.get("enabled") is not False or camera.get("physically_connected") is not False:
        error(
            errors,
            "ROBOT_CAMERA_CONFLICT",
            "The camera must be disabled and physically disconnected because robot pins reuse its interface",
            "camera",
        )

    declared_reserved = profile.get("reserved_pins")
    if not isinstance(declared_reserved, list) or not all(integer(pin) for pin in declared_reserved):
        error(errors, "ROBOT_RESERVED_PINS_INVALID", "reserved_pins must be an integer array", "reserved_pins")
    else:
        missing = sorted(HARD_RESERVED_PINS.difference(declared_reserved))
        if missing:
            error(
                errors,
                "ROBOT_RESERVED_PINS_INCOMPLETE",
                "Profile omits board-reserved GPIOs",
                "reserved_pins",
                {"missing": missing},
            )

    servos = profile.get("servos")
    if not isinstance(servos, list) or len(servos) != 6:
        error(errors, "ROBOT_SERVO_COUNT_INVALID", "Exactly six servos are required", "servos")
        servos = servos if isinstance(servos, list) else []

    ids = []
    joints = []
    for index, item in enumerate(servos):
        validate_servo(item, index, claims, errors)
        if isinstance(item, dict):
            ids.append(item.get("servo_id"))
            joints.append(item.get("joint"))
    if set(ids) != set(range(1, 7)) or len(ids) != len(set(ids)):
        error(errors, "ROBOT_SERVO_ID_INVALID", "servo_id values must be unique integers 1 through 6", "servos")
    if set(joints) != EXPECTED_JOINTS or len(joints) != len(set(joints)):
        error(
            errors,
            "ROBOT_JOINT_MAPPING_INVALID",
            "Servo joints must contain one arm and two leg joints per side",
            "servos",
            {"expected": sorted(EXPECTED_JOINTS)},
        )

    audio = profile.get("audio")
    if not isinstance(audio, dict):
        error(errors, "ROBOT_AUDIO_INVALID", "audio must be an object", "audio")
    else:
        if audio.get("sample_rate_hz") != 16000 or audio.get("bits") != 16 or audio.get("channels") != 1:
            error(errors, "ROBOT_AUDIO_FORMAT_INVALID", "Default voice audio must be 16 kHz, 16-bit mono", "audio")
        speaker = audio.get("speaker")
        microphone = audio.get("microphone")
        if not isinstance(speaker, dict):
            error(errors, "ROBOT_SPEAKER_INVALID", "speaker must be an object", "audio.speaker")
        else:
            for field in ("sck", "ws", "sd", "gain", "shutdown"):
                validate_pin(speaker.get(field), "audio.speaker." + field, claims, errors)
        if not isinstance(microphone, dict):
            error(errors, "ROBOT_MICROPHONE_INVALID", "microphone must be an object", "audio.microphone")
        else:
            for field in ("sck", "ws", "sd"):
                validate_pin(microphone.get(field), "audio.microphone." + field, claims, errors)

    non_default = sorted(pin for pin in claims if pin not in DEFAULT_RECLAIMED_PINS)
    if non_default:
        warnings.append(
            {
                "code": "ROBOT_NON_DEFAULT_GPIO",
                "message": "Profile uses GPIOs outside the camera-reclaimed default set; verify physical wiring",
                "pins": non_default,
            }
        )

    return {
        "ok": not errors,
        "board_id": profile.get("board_id"),
        "profile_id": profile.get("profile_id"),
        "claims": {str(pin): role for pin, role in sorted(claims.items())},
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate the MPOS six-servo robot hardware profile")
    parser.add_argument("profile", nargs="?", default="-", help="JSON path or '-' for stdin")
    args = parser.parse_args()
    try:
        profile = read_json(args.profile)
        result = validate_profile(profile)
    except Exception as exc:
        result = {
            "ok": False,
            "board_id": None,
            "claims": {},
            "errors": [{"code": "ROBOT_PROFILE_READ_FAILED", "message": str(exc)}],
            "warnings": [],
        }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
