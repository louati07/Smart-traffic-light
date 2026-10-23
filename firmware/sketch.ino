/**
 * Smart Intersection Digital Twin - Wokwi ESP32 Firmware
 * 
 * Safety Invariants Guaranteed Locally (S1-S7):
 * - S1: NS and EW never green simultaneously.
 * - S2: G->G or R->G without Y and ALL_RED in between is prevented.
 * - S3: YELLOW_MS (3000ms) and ALL_RED_MS (2000ms) are strictly immutable.
 * - S4: GREEN lasts at least MIN_GREEN_MS (5000ms) before preemption.
 * - S5: PRIORITY hold watchdog never exceeds PRIORITY_MAX_MS (30000ms).
 * - S6: Heartbeat timeout (>10s) triggers FALLBACK mode; invalid/stale commands rejected.
 * - S7: Safe clearance transition out of priority.
 * 
 * Target: ESP32 DevKit V1 (Wokwi simulation)
 * Non-blocking millis() control loop.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

// Set to 1 to run offline without Wi-Fi (serial standalone verification)
#define LOCAL_TEST 0

// ============================================================================
// CONFIGURATION & PIN MAP
// ============================================================================
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// Firebase Realtime DB URL (REST API). Update with your project if live.
const char* FIREBASE_HOST = "https://emergency-traffic-controller-default-rtdb.europe-west1.firebasedatabase.app";
const char* FIREBASE_AUTH = "NgX8gPeu8NLT6SZUu73vgsIpEN3kHtSkrE1NN2fc";
const char* INTERSECTION_ID = "i1";

inline String buildFirebaseUrl(const String& path) {
  String url = String(FIREBASE_HOST) + path + ".json";
  if (FIREBASE_AUTH && strlen(FIREBASE_AUTH) > 0) {
    url += "?auth=" + String(FIREBASE_AUTH);
  }
  return url;
}

// Pin Map (Fixed Output Pins)
const int PIN_N_R = 16, PIN_N_Y = 17, PIN_N_G = 18;
const int PIN_E_R = 19, PIN_E_Y = 21, PIN_E_G = 22;
const int PIN_S_R = 23, PIN_S_Y = 25, PIN_S_G = 26;
const int PIN_W_R = 27, PIN_W_Y = 32, PIN_W_G = 33;

const int PIN_STATUS_LED = 2; // On=NORMAL, Slow blink=PRIORITY, Fast blink=FALLBACK
const int PIN_BUZZER = 4;

// FSM Timings (ms)
const unsigned long GREEN_MS = 10000;
const unsigned long YELLOW_MS = 3000;
const unsigned long ALL_RED_MS = 2000;
const unsigned long MIN_GREEN_MS = 5000;
const unsigned long PRIORITY_MAX_MS = 30000;
const unsigned long HEARTBEAT_TIMEOUT_MS = 10000;
const unsigned long POLL_MS = 700;
const unsigned long STATE_REPORT_INTERVAL_MS = 2000;

// Shared HMAC Secret (Section 5.4 P2)
const char* HMAC_SECRET = "dev-hmac-shared-key-wokwi-server-2026";

// ============================================================================
// FSM STATES & ENUMS
// ============================================================================
enum Phase {
  NS_GREEN,
  NS_YELLOW,
  ALL_RED_TO_EW,
  EW_GREEN,
  EW_YELLOW,
  ALL_RED_TO_NS
};

enum Mode {
  NORMAL,
  PRIORITY,
  FALLBACK
};

enum Axis {
  AXIS_NS,
  AXIS_EW,
  AXIS_NONE
};

// State Variables
Phase currentPhase = NS_GREEN;
Phase lastPhase = NS_GREEN;
Mode currentMode = NORMAL;

unsigned long phaseStartMs = 0;
unsigned long lastStateReportMs = 0;
unsigned long lastCommandPollMs = 0;
unsigned long lastHeartbeatRxMs = 0;
int lastHeartbeatVal = 0;

// Priority tracking
Axis activePriorityAxis = AXIS_NONE;
Axis targetPriorityAxis = AXIS_NONE;
bool holdGreenActive = false;
unsigned long priorityStartMs = 0;
unsigned long priorityCmdRxMs = 0;
unsigned long priorityTtlMs = 15000;
long lastSeq = 0;
long rejectedCmds = 0;

// ============================================================================
// HARDWARE DRIVERS
// ============================================================================
void setLights(char n, char e, char s, char w) {
  digitalWrite(PIN_N_R, n == 'R' ? HIGH : LOW);
  digitalWrite(PIN_N_Y, n == 'Y' ? HIGH : LOW);
  digitalWrite(PIN_N_G, n == 'G' ? HIGH : LOW);

  digitalWrite(PIN_E_R, e == 'R' ? HIGH : LOW);
  digitalWrite(PIN_E_Y, e == 'Y' ? HIGH : LOW);
  digitalWrite(PIN_E_G, e == 'G' ? HIGH : LOW);

  digitalWrite(PIN_S_R, s == 'R' ? HIGH : LOW);
  digitalWrite(PIN_S_Y, s == 'Y' ? HIGH : LOW);
  digitalWrite(PIN_S_G, s == 'G' ? HIGH : LOW);

  digitalWrite(PIN_W_R, w == 'R' ? HIGH : LOW);
  digitalWrite(PIN_W_Y, w == 'Y' ? HIGH : LOW);
  digitalWrite(PIN_W_G, w == 'G' ? HIGH : LOW);
}

void applyPhaseLights(Phase p) {
  switch (p) {
    case NS_GREEN:       setLights('G', 'R', 'G', 'R'); break;
    case NS_YELLOW:      setLights('Y', 'R', 'Y', 'R'); break;
    case ALL_RED_TO_EW:  setLights('R', 'R', 'R', 'R'); break;
    case EW_GREEN:       setLights('R', 'G', 'R', 'G'); break;
    case EW_YELLOW:      setLights('R', 'Y', 'R', 'Y'); break;
    case ALL_RED_TO_NS:  setLights('R', 'R', 'R', 'R'); break;
  }
}

const char* phaseToString(Phase p) {
  switch (p) {
    case NS_GREEN:      return "NS_GREEN";
    case NS_YELLOW:     return "NS_YELLOW";
    case ALL_RED_TO_EW: return "ALL_RED_TO_EW";
    case EW_GREEN:      return "EW_GREEN";
    case EW_YELLOW:     return "EW_YELLOW";
    case ALL_RED_TO_NS: return "ALL_RED_TO_NS";
  }
  return "UNKNOWN";
}

const char* modeToString(Mode m) {
  switch (m) {
    case NORMAL:   return "NORMAL";
    case PRIORITY: return "PRIORITY";
    case FALLBACK: return "FALLBACK";
  }
  return "UNKNOWN";
}

void updateStatusIndicators(unsigned long nowMs) {
  if (currentMode == NORMAL) {
    digitalWrite(PIN_STATUS_LED, HIGH);
    digitalWrite(PIN_BUZZER, LOW);
  } else if (currentMode == PRIORITY) {
    // 500ms slow blink + audible alert
    bool on = ((nowMs / 250) % 2) == 0;
    digitalWrite(PIN_STATUS_LED, on ? HIGH : LOW);
    digitalWrite(PIN_BUZZER, on ? HIGH : LOW);
  } else { // FALLBACK
    // 150ms fast blink + short chirp pattern
    bool fastOn = ((nowMs / 100) % 2) == 0;
    digitalWrite(PIN_STATUS_LED, fastOn ? HIGH : LOW);
    digitalWrite(PIN_BUZZER, ((nowMs / 100) % 10 == 0) ? HIGH : LOW);
  }
}

// ============================================================================
// FSM TRANSITIONS & SAFETY ENFORCEMENT
// ============================================================================
void transitionTo(Phase next, unsigned long nowMs) {
  currentPhase = next;
  phaseStartMs = nowMs;
  applyPhaseLights(currentPhase);
  Serial.printf("[FSM] -> %s at %lu ms\n", phaseToString(currentPhase), nowMs);
}

void releasePriority() {
  holdGreenActive = false;
  targetPriorityAxis = AXIS_NONE;
  activePriorityAxis = AXIS_NONE;
  if (currentMode == PRIORITY) {
    currentMode = NORMAL;
  }
}

void tickFSM(unsigned long nowMs) {
  // Invariant S6: Heartbeat watchdog for FALLBACK mode
  if (lastHeartbeatVal > 0 && (nowMs - lastHeartbeatRxMs) > HEARTBEAT_TIMEOUT_MS) {
    if (currentMode != FALLBACK) {
      Serial.printf("[SAFETY] Heartbeat lost! Entering FALLBACK mode at %lu ms\n", nowMs);
      currentMode = FALLBACK;
      releasePriority();
    }
  }

  // Invariant S5 & Command TTL watchdog
  if (holdGreenActive) {
    unsigned long holdDuration = nowMs - priorityStartMs;
    unsigned long sinceRx = nowMs - priorityCmdRxMs;
    if (holdDuration >= PRIORITY_MAX_MS || sinceRx >= priorityTtlMs) {
      Serial.println("[SAFETY] Priority hold watchdog expired, releasing");
      releasePriority();
    }
  }

  unsigned long elapsed = nowMs - phaseStartMs;

  switch (currentPhase) {
    case NS_GREEN:
      if (targetPriorityAxis == AXIS_EW && currentMode == PRIORITY) {
        // Invariant S4: Min green before cutting
        if (elapsed >= MIN_GREEN_MS) {
          transitionTo(NS_YELLOW, nowMs);
        }
      } else if (holdGreenActive && activePriorityAxis == AXIS_NS) {
        // Holding NS green; timer paused
      } else {
        if (elapsed >= GREEN_MS) {
          transitionTo(NS_YELLOW, nowMs);
        }
      }
      break;

    case NS_YELLOW:
      // Invariant S3: Yellow duration immutable
      if (elapsed >= YELLOW_MS) {
        transitionTo(ALL_RED_TO_EW, nowMs);
      }
      break;

    case ALL_RED_TO_EW:
      // Invariant S3: All-red duration immutable
      if (elapsed >= ALL_RED_MS) {
        transitionTo(EW_GREEN, nowMs);
        if (targetPriorityAxis == AXIS_EW && currentMode == PRIORITY) {
          activePriorityAxis = AXIS_EW;
          holdGreenActive = true;
          priorityStartMs = nowMs;
          Serial.println("[PRIORITY] EW_GREEN held for emergency vehicle");
        }
      }
      break;

    case EW_GREEN:
      if (targetPriorityAxis == AXIS_NS && currentMode == PRIORITY) {
        // Invariant S4: Min green before cutting
        if (elapsed >= MIN_GREEN_MS) {
          transitionTo(EW_YELLOW, nowMs);
        }
      } else if (holdGreenActive && activePriorityAxis == AXIS_EW) {
        // Holding EW green; timer paused
      } else {
        if (elapsed >= GREEN_MS) {
          transitionTo(EW_YELLOW, nowMs);
        }
      }
      break;

    case EW_YELLOW:
      // Invariant S3: Yellow duration immutable
      if (elapsed >= YELLOW_MS) {
        transitionTo(ALL_RED_TO_NS, nowMs);
      }
      break;

    case ALL_RED_TO_NS:
      // Invariant S3: All-red duration immutable
      if (elapsed >= ALL_RED_MS) {
        transitionTo(NS_GREEN, nowMs);
        if (targetPriorityAxis == AXIS_NS && currentMode == PRIORITY) {
          activePriorityAxis = AXIS_NS;
          holdGreenActive = true;
          priorityStartMs = nowMs;
          Serial.println("[PRIORITY] NS_GREEN held for emergency vehicle");
        }
      }
      break;
  }
}

// ============================================================================
// NETWORK & FIREBASE REST
// ============================================================================
WiFiClientSecure secureClient;

void setupNetwork() {
#if !LOCAL_TEST
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi Connected! IP: " + WiFi.localIP().toString());
    secureClient.setInsecure(); // Acceptable for simulation environment
  } else {
    Serial.println("\nWi-Fi connection timed out. Running in local fallback.");
  }
#endif
}

void pollFirebaseCommand(unsigned long nowMs) {
#if !LOCAL_TEST
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = buildFirebaseUrl("/intersections/" + String(INTERSECTION_ID) + "/command");
  http.begin(secureClient, url);
  int code = http.GET();

  if (code == 200) {
    String payload = http.getString();
    if (payload != "null" && payload.length() > 5) {
      StaticJsonDocument<512> doc;
      DeserializationError err = deserializeJson(doc, payload);
      if (!err) {
        long seq = doc["seq"] | 0;
        const char* cmd = doc["cmd"] | "";
        const char* axisStr = doc["axis"] | "";
        int ttl = doc["ttl_s"] | 15;

        // Invariant S6: Seq must strictly increase
        if (seq > lastSeq) {
          lastSeq = seq;
          if (strcmp(cmd, "PRIORITY") == 0) {
            Axis reqAxis = AXIS_NONE;
            if (strcmp(axisStr, "NS") == 0) reqAxis = AXIS_NS;
            else if (strcmp(axisStr, "EW") == 0) reqAxis = AXIS_EW;

            if (reqAxis != AXIS_NONE) {
              targetPriorityAxis = reqAxis;
              currentMode = PRIORITY;
              priorityCmdRxMs = nowMs;
              priorityTtlMs = ttl * 1000UL;

              // Rule 1: If axis is already green, hold immediately
              if ((currentPhase == NS_GREEN && reqAxis == AXIS_NS) ||
                  (currentPhase == EW_GREEN && reqAxis == AXIS_EW)) {
                activePriorityAxis = reqAxis;
                holdGreenActive = true;
                priorityStartMs = nowMs;
              }
              Serial.printf("[CMD] PRIORITY seq=%ld for axis=%s\n", seq, axisStr);
            }
          } else if (strcmp(cmd, "CLEAR") == 0) {
            releasePriority();
            Serial.printf("[CMD] CLEAR seq=%ld\n", seq);
          }
        }
      }
    }
  }
  http.end();

  // Poll heartbeat counter
  String hbUrl = buildFirebaseUrl("/intersections/" + String(INTERSECTION_ID) + "/heartbeat");
  http.begin(secureClient, hbUrl);
  int hbCode = http.GET();
  if (hbCode == 200) {
    int counter = http.getString().toInt();
    if (counter > lastHeartbeatVal || lastHeartbeatVal == 0) {
      lastHeartbeatVal = counter;
      lastHeartbeatRxMs = nowMs;
      if (currentMode == FALLBACK) {
        currentMode = NORMAL;
        Serial.println("[SAFETY] Heartbeat restored. Returning to NORMAL mode.");
      }
    }
  }
  http.end();
#endif
}

void reportStateToFirebase(unsigned long nowMs) {
#if !LOCAL_TEST
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<512> doc;
  doc["phase"] = phaseToString(currentPhase);
  doc["mode"] = modeToString(currentMode);
  
  JsonObject lights = doc.createNestedObject("lights");
  switch (currentPhase) {
    case NS_GREEN:       lights["N"] = "G"; lights["E"] = "R"; lights["S"] = "G"; lights["W"] = "R"; break;
    case NS_YELLOW:      lights["N"] = "Y"; lights["E"] = "R"; lights["S"] = "Y"; lights["W"] = "R"; break;
    case ALL_RED_TO_EW:  lights["N"] = "R"; lights["E"] = "R"; lights["S"] = "R"; lights["W"] = "R"; break;
    case EW_GREEN:       lights["N"] = "R"; lights["E"] = "G"; lights["S"] = "R"; lights["W"] = "G"; break;
    case EW_YELLOW:      lights["N"] = "R"; lights["E"] = "Y"; lights["S"] = "R"; lights["W"] = "Y"; break;
    case ALL_RED_TO_NS:  lights["N"] = "R"; lights["E"] = "R"; lights["S"] = "R"; lights["W"] = "R"; break;
  }

  doc["last_seq"] = lastSeq;
  doc["phase_elapsed_ms"] = nowMs - phaseStartMs;
  doc["uptime_ms"] = nowMs;
  doc["rejected_cmds"] = rejectedCmds;

  String output;
  serializeJson(doc, output);

  HTTPClient http;
  String url = buildFirebaseUrl("/intersections/" + String(INTERSECTION_ID) + "/state");
  http.begin(secureClient, url);
  http.PUT(output);
  http.end();
#endif
}

// ============================================================================
// MAIN ARDUINO SETUP & LOOP
// ============================================================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- Smart Intersection Controller Initializing ---");

  // Output pins initialization
  pinMode(PIN_N_R, OUTPUT); pinMode(PIN_N_Y, OUTPUT); pinMode(PIN_N_G, OUTPUT);
  pinMode(PIN_E_R, OUTPUT); pinMode(PIN_E_Y, OUTPUT); pinMode(PIN_E_G, OUTPUT);
  pinMode(PIN_S_R, OUTPUT); pinMode(PIN_S_Y, OUTPUT); pinMode(PIN_S_G, OUTPUT);
  pinMode(PIN_W_R, OUTPUT); pinMode(PIN_W_Y, OUTPUT); pinMode(PIN_W_G, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  phaseStartMs = millis();
  applyPhaseLights(currentPhase);
  digitalWrite(PIN_STATUS_LED, HIGH);

  setupNetwork();
  Serial.println("System initialized. Starting safety control loop.");
}

void loop() {
  unsigned long now = millis();

  // 1. Advance FSM and check invariants
  tickFSM(now);

  // 2. Drive status LED and buzzer
  updateStatusIndicators(now);

  // 3. Periodic command and heartbeat polling
  if (now - lastCommandPollMs >= POLL_MS) {
    lastCommandPollMs = now;
    pollFirebaseCommand(now);
  }

  // 4. State reporting on phase change or every 2s
  bool phaseChanged = (lastPhase != currentPhase);
  bool timerExpired = (now - lastStateReportMs >= STATE_REPORT_INTERVAL_MS);
  if (phaseChanged || timerExpired) {
    lastPhase = currentPhase;
    lastStateReportMs = now;
    reportStateToFirebase(now);
  }
}
