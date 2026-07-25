# maix.audio

Official URL: https://wiki.sipeed.com/maixpy/api/maix/audio.html

Status: seed_reference

Brief: audio module.

Stage A policy: indexed for future audio/vision workflows. Do not generate audio record/playback code unless the user explicitly asks for audio and the hardware path is known.

Indexed classes:

- `Wave`
- `Recorder`
- `Player`

Officially indexed callable surface:

```python
from maix import audio

wave = audio.Wave(sample_rate=16000, channels=1, bits_per_sample=16)
wave.load(path, sample_rate=16000, channels=1, bits_per_sample=16)
wave.save(path)
wave.get_pcm()
wave.set_pcm(data, copy=True)

rec = audio.Recorder(path="", sample_rate=48000, format=..., channel=1, block=True)
rec.volume()
rec.mute()
rec.record()
rec.finish()

player = audio.Player(path="", sample_rate=48000, format=..., channel=1, block=True)
player.volume()
player.play(data=b"")
player.reset(start=False)
```

Restrictions:

- Do not assume microphone, DAC, speaker amp, or I2S routing from the generic module page.
- Do not add audio to vision JSONL exports unless a task-specific audio reference exists.
