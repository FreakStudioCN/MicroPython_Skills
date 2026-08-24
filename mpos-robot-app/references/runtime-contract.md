# Robot runtime contract

## Protected layer

Copy `assets/app-template/robot_runtime` without model-authored changes. It owns PWM conversion, motion limits, half-duplex I2S lifecycle, profile persistence, action validation, cancellation, and idempotent execution.

The generated App may define named poses and business behavior but must call the protected layer through logical joints and structured actions.

## Logical joints

- `left_arm`
- `right_arm`
- `left_leg_upper`
- `right_leg_upper`
- `left_leg_lower`
- `right_leg_lower`

## LLM response

Require a JSON object with:

```json
{
  "operation_id": "conversation-operation-id",
  "reply_text": "text to speak",
  "emotion": "neutral",
  "requires_confirmation": false,
  "actions": [
    {"type": "move_joint", "joint": "left_arm", "angle": 90, "duration_ms": 500},
    {"type": "pose", "name": "greeting", "duration_ms": 700},
    {"type": "wait", "duration_ms": 200}
  ]
}
```

Reject unknown fields that could produce side effects. Reject raw GPIO, duty cycle, pulse width, Python, URL, file, script, shell, serial, and device-command actions.

## Conversation state

Use this first-version state machine:

```text
IDLE -> LISTENING -> ASR -> THINKING -> SPEAKING_AND_ACTING -> COOLDOWN -> IDLE
```

Transition to `ERROR` on unrecoverable failure. Cancellation must stop motion interpolation, mute the amplifier, deinitialize I2S, retain the last valid checkpoint, and return a structured cancellation result.

Use half-duplex audio. Disable microphone RX during TTS playback and disable speaker TX during recording. Do not implement acoustic echo cancellation or voice interruption unless explicitly requested in a later version.

## Context boundaries

Send the LLM only personality, recent dialog, the logical action catalog, current logical joint state, previous action outcome, and required non-secret device status. Never expose pins, PWM values, Wi-Fi credentials, provider secrets, or unrestricted tool descriptions.

## Generated surface

Allow generation of:

- MPOS Activity and settings UI
- user-editable hardware profile forms
- personality and prompt text
- named poses and action compositions
- provider endpoints, model names, and non-secret options
- credential-entry UI that stores secrets only on the device

Do not allow generation of replacements for protected runtime modules.
