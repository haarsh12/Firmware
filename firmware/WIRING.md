# Voice-agent wiring

Use a common ground for the ESP32, MAX98357A, LCD, LEDs, touch sensor, and any
external 5 V supply. GPIO numbers below match
`esp32_inmp441_voice/esp32_inmp441_voice.ino`.

| Part | Module pin | ESP32 / supply connection |
|---|---|---|
| INMP441 | VDD | 3V3 |
| INMP441 | GND | GND |
| INMP441 | SCK/BCLK | GPIO 26 |
| INMP441 | WS/LRCL | GPIO 25 |
| INMP441 | SD/DOUT | GPIO 22 |
| TTP223 touch | VCC | 3V3 |
| TTP223 touch | GND | GND |
| TTP223 touch | OUT | GPIO 18 |
| Recording LED | anode | GPIO 4 through a 220–330 Ω resistor |
| Ready LED | anode | GPIO 5 through a 220–330 Ω resistor |
| Backend-connected LED | anode | GPIO 27 through a 220–330 Ω resistor |
| AI/TTS-active LED | anode | GPIO 14 through a 220–330 Ω resistor |
| All LEDs | cathode | GND |
| I²C LCD | VCC | 3V3 preferred; 5V only with I²C level shifting |
| I²C LCD | GND | GND |
| I²C LCD | SDA | GPIO 21 |
| I²C LCD | SCL | GPIO 15 |
| MAX98357A | VIN | stable 5V supply |
| MAX98357A | GND | common GND |
| MAX98357A | BCLK | GPIO 32 |
| MAX98357A | LRC / WS | GPIO 33 |
| MAX98357A | DIN | GPIO 19 |
| MAX98357A | SD / MODE | leave as supplied by the module or configure per module guide; never pull it directly to GND while testing |
| MAX98357A | GAIN | leave unconnected for its typical default gain while testing |
| 4 Ω speaker | `SPK+`, `SPK-` | connect directly across these two amplifier terminals |

## Important MAX98357A notes

- `SPK-` is an amplified bridge output, **not ground**. Never connect either
  speaker wire to ESP32 GND.
- A 10 W speaker is safe to use; its 10 W number is a rating, not a demand.
  A MAX98357A delivers only about 2.5–3 W into 4 Ω from 5 V, so it cannot
  drive the speaker at 10 W.
- Use a stable 5 V supply with adequate current (preferably 1 A or more) for
  the amplifier. Connect that supply's ground to ESP32 ground. Do not try to
  power the amplifier/speaker from a weak 3.3 V ESP32 pin.
- Some inexpensive MAX98357A modules label shutdown/channel selection as
  `SD`, `MODE`, or `SD_MODE`; module resistor layouts differ. The test sketch
  uses left-channel I²S output. If there is no sound, first check VIN/GND/DIN/
  BCLK/LRC and then check that your module's SD/MODE configuration is enabled.
- An I²C LCD backpack powered at 5 V can pull SDA/SCL up to 5 V, which is not
  safe for ESP32 GPIO. Power the backpack at 3.3 V if it works at that voltage,
  or use a bidirectional I²C level shifter when the LCD requires 5 V.

The module and output behavior are documented by the [MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max98357a-max98357b.pdf)
and the [MAX98357A breakout pin guide](https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp/pinouts?view=all).
