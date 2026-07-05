# Legacy upy-gen-driver Rules

Preserve these rules from `G:\MicroPython_Skills\upy-gen-driver` while changing the I/O mechanism to plugin protocol messages.

- Accept PDF datasheets, Arduino/C/C++ code, GitHub Arduino repositories, or chip model names.
- `extract_pdf.py` only extracts page text. LLM performs protocol/register understanding.
- `convert_arduino.py` only maps API calls and extracts source structure. LLM rewrites logic in MicroPython style.
- Arduino translation must not be line-by-line mechanical translation.
- Generate a debug single-file driver before production code.
- Debug driver must print clear English self-test output, expected vs actual values, and hints.
- Hardware verification is the normal gate before production driver generation.
- Use `mpremote resume run` or equivalent REPL run behavior for fast iteration; do not flash unless explicitly requested.
- Verification loop is bounded to 10 rounds.
- Step 4 production driver must not run before either `SELF_TEST_PASS` or explicit user skip with warning.
- I2C/SPI/UART bus objects must be injected from outside the driver class.
- All polling/wait loops must include timeout.
- Convert low-level `OSError` into descriptive `RuntimeError` with address/register/action context.
- Prefer preallocated `bytearray` for repeated MicroPython bus I/O.
- Track shadow state per setter; do not let one setter silently mutate another setting.
- Keep datasheet page/table evidence in comments where useful.
- Generated strings printed or raised by device-side code should be ASCII/English.
