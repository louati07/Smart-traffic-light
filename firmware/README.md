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
2. In the code tab, paste the contents of [`sketch.ino`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/sketch.ino).
3. In the diagram tab, paste the contents of [`diagram.json`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/diagram.json).
4. In the Library Manager tab, add `ArduinoJson` (or paste [`libraries.txt`](file:///c:/poly/SecondYearEng/S1/IOT/project/firmware/libraries.txt)).
5. Click **Play** to start simulation.
6. The simulated ESP32 connects to Wokwi virtual Wi-Fi (`Wokwi-GUEST`) and syncs live state with Firebase.
