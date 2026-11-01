# Smart Intersection Firmware (Wokwi ESP32)

This directory contains the complete C++ firmware and circuit definition for simulating the physical traffic light controller in [Wokwi](https://wokwi.com).

## Hardware Setup (Wokwi Pinout)

- **Microcontroller:** ESP32 DevKit V1
- **Traffic Light Signal LEDs (12 LEDs):**
  - **North (N):** Red = GPIO 16, Yellow = GPIO 17, Green = GPIO 18
  - **East (E):** Red = GPIO 19, Yellow = GPIO 21, Green = GPIO 22
  - **South (S):** Red = GPIO 23, Yellow = GPIO 25, Green = GPIO 26
  - **West (W):** Red = GPIO 27, Yellow = GPIO 32, Green = GPIO 33
- **Indicators:**
  - **Status LED:** GPIO 2 (Solid = NORMAL, Slow Blink = PRIORITY, Fast Blink = FALLBACK)
  - **Buzzer:** GPIO 4 (Chirp on emergency vehicle arrival & fallback alert)

## How to Run in Wokwi

1. Open [wokwi.com](https://wokwi.com) and start a new **ESP32** project.
2. In the code tab, paste the contents of [`sketch.ino`](sketch.ino).
3. In the diagram tab, paste the contents of [`diagram.json`](diagram.json).
4. In the Library Manager tab, add `ArduinoJson` (or paste [`libraries.txt`](libraries.txt)).
5. Click **Play** to start simulation.
6. Set `FIREBASE_HOST` and, for a protected database, `FIREBASE_AUTH` in the sketch. Keep real credentials out of Git. The ESP32 then connects to Wokwi virtual Wi-Fi (`Wokwi-GUEST`) and syncs state with Firebase.

The firmware timing constants mirror `config.yaml`: green 10 s, yellow 3 s, all-red 2 s, minimum green 5 s, and command polling 700 ms. Update both copies together. The firmware currently does not verify HMAC signatures.

Priority commands carry both `axis` and `approach`. During the priority hold, only the requested approach is green; the other three are red. If priority arrives while the other axis is green, the controller finishes its minimum-green, yellow, and all-red clearance first.
