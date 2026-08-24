EXPECTED_BOARD = "waveshare_esp32_s3_touch_lcd_2"
EXPECTED_JOINTS = (
    "left_arm",
    "right_arm",
    "left_leg_upper",
    "right_leg_upper",
    "left_leg_lower",
    "right_leg_lower",
)
RESERVED_PINS = (
    0,
    1,
    5,
    19,
    20,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    39,
    40,
    42,
    43,
    44,
    45,
    47,
    48,
)


def validate_profile(profile):
    errors = []
    if not isinstance(profile, dict):
        return ["profile must be a dict"]
    if profile.get("board_id") != EXPECTED_BOARD:
        errors.append("unsupported board_id")
    camera = profile.get("camera", {})
    if camera.get("enabled") is not False or camera.get("physically_connected") is not False:
        errors.append("camera must be disabled and physically disconnected")
    servos = profile.get("servos")
    if not isinstance(servos, list) or len(servos) != 6:
        errors.append("exactly six servos are required")
        servos = servos if isinstance(servos, list) else []
    ids = []
    joints = []
    claims = {}

    def claim(pin, role):
        if not isinstance(pin, int) or isinstance(pin, bool) or pin < 0 or pin > 48:
            errors.append("invalid pin for %s" % role)
            return
        if pin in RESERVED_PINS:
            errors.append("reserved pin %s for %s" % (pin, role))
        if pin in claims:
            errors.append("pin %s conflicts between %s and %s" % (pin, claims[pin], role))
        else:
            claims[pin] = role

    for index, servo in enumerate(servos):
        if not isinstance(servo, dict):
            errors.append("invalid servo %s" % index)
            continue
        ids.append(servo.get("servo_id"))
        joints.append(servo.get("joint"))
        claim(servo.get("pin"), "servo.%s" % servo.get("joint"))
        if servo.get("frequency_hz") != 50:
            errors.append("servo %s must use 50 Hz" % index)
        minimum = servo.get("min_us")
        center = servo.get("center_us")
        maximum = servo.get("max_us")
        if not isinstance(minimum, int) or not isinstance(center, int) or not isinstance(maximum, int) or not minimum < center < maximum:
            errors.append("invalid pulse range for servo %s" % index)
    if sorted(ids) != [1, 2, 3, 4, 5, 6]:
        errors.append("servo_id values must be 1 through 6")
    if sorted(joints) != sorted(EXPECTED_JOINTS):
        errors.append("logical joint mapping is incomplete")
    audio = profile.get("audio", {})
    speaker = audio.get("speaker", {})
    microphone = audio.get("microphone", {})
    for name in ("sck", "ws", "sd", "gain", "shutdown"):
        claim(speaker.get(name), "speaker.%s" % name)
    for name in ("sck", "ws", "sd"):
        claim(microphone.get(name), "microphone.%s" % name)
    return errors


class ProfileStore:
    def __init__(self, app_fullname, default_profile):
        from mpos import SharedPreferences

        self._prefs = SharedPreferences(app_fullname, filename="robot_hardware.json")
        self._default = default_profile

    def candidate(self):
        return self._prefs.get_dict("candidate", self._default)

    def active(self):
        return self._prefs.get_dict("active", self._default)

    def last_known_good(self):
        return self._prefs.get_dict("last_known_good", self._default)

    def save_candidate(self, profile):
        errors = validate_profile(profile)
        if errors:
            return False, errors
        self._prefs.edit().put_dict("candidate", profile).commit()
        return True, []

    def activate(self, probe):
        candidate = self.candidate()
        errors = validate_profile(candidate)
        if errors:
            return False, errors
        previous = self.active()
        try:
            probe(candidate)
        except Exception as exc:
            return False, [str(exc)]
        editor = self._prefs.edit()
        editor.put_dict("last_known_good", previous)
        editor.put_dict("active", candidate)
        editor.commit()
        return True, []

    def rollback(self):
        profile = self.last_known_good()
        errors = validate_profile(profile)
        if errors:
            return False, errors
        self._prefs.edit().put_dict("active", profile).commit()
        return True, []
