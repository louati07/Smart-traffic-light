/**
 * Smart Intersection Digital Twin - Wokwi ESP32 Firmware
 * 
 * Safety Invariants Guaranteed Locally (S1-S7):
 * - S1: NS and EW never green simultaneously.
 * - S2: G->G or R->G without Y and ALL_RED in between is prevented.
 * - S3: Normal clearance stays 3s yellow + 2s all-red; simulation priority clearance is 2s + 1s.
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
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// ============================================================================
// FSM ENUMS & TYPES (Declared before functions for C++ prototypes)
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

// Set to 1 to run offline without Wi-Fi (serial standalone verification)
#define LOCAL_TEST 0

// ============================================================================
// CONFIGURATION & PIN MAP
// ============================================================================
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// Firebase Realtime DB URL (REST API). Update with your project if live.
const char* FIREBASE_HOST = "https://emergency-traffic-controller-default-rtdb.europe-west1.firebasedatabase.app";
// Set this locally for a protected Firebase project. Never commit a real token.
const char* FIREBASE_AUTH = "";
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

// FSM Timings (ms) - Instant Emergency Demo Profile
const unsigned long GREEN_MS = 10000;
const unsigned long YELLOW_MS = 3000;
const unsigned long ALL_RED_MS = 2000;
// Simulation-only fast preemption profile. Normal signal timings remain unchanged.
const unsigned long PRIORITY_YELLOW_MS = 2000;
const unsigned long PRIORITY_ALL_RED_MS = 1000;
const unsigned long MIN_GREEN_MS = 5000;
const unsigned long PRIORITY_MAX_MS = 30000;
const unsigned long HEARTBEAT_TIMEOUT_MS = 10000;
// Avoid saturating the safety loop with blocking TLS mailbox reads.
const unsigned long POLL_MS = 1000;
// Keep Firebase and the dashboard close to the controller's live phase while
// still limiting REST traffic to two state writes per second.
const unsigned long STATE_REPORT_INTERVAL_MS = 500;

// State Variables
Phase currentPhase = NS_GREEN;
Phase lastPhase = NS_GREEN;
Mode currentMode = NORMAL;
Mode lastReportedMode = NORMAL;
long lastReportedSeq = -1;

unsigned long phaseStartMs = 0;
unsigned long lastStateReportMs = 0;
unsigned long lastStateReportAttemptMs = 0;
unsigned long lastCommandPollMs = 0;
unsigned long lastHeartbeatRxMs = 0;
int lastHeartbeatVal = 0;
bool heartbeatSeen = false;

// Priority tracking
Axis activePriorityAxis = AXIS_NONE;
Axis targetPriorityAxis = AXIS_NONE;
char activePriorityApproach = '\0';
char targetPriorityApproach = '\0';
bool holdGreenActive = false;
bool priorityClearanceActive = false;
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
  if (holdGreenActive && activePriorityApproach != '\0') {
    if (p == NS_GREEN && activePriorityAxis == AXIS_NS) {
      setLights(activePriorityApproach == 'N' ? 'G' : 'R', 'R', activePriorityApproach == 'S' ? 'G' : 'R', 'R');
      return;
    }
    if (p == EW_GREEN && activePriorityAxis == AXIS_EW) {
      setLights('R', activePriorityApproach == 'E' ? 'G' : 'R', 'R', activePriorityApproach == 'W' ? 'G' : 'R');
      return;
    }
  }
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
  targetPriorityApproach = '\0';
  activePriorityAxis = AXIS_NONE;
  activePriorityApproach = '\0';
  priorityClearanceActive = false;
  applyPhaseLights(currentPhase);
  if (currentMode == PRIORITY) {
    currentMode = NORMAL;
  }
}

void tickFSM(unsigned long nowMs) {
  // Invariant S6: Heartbeat watchdog for FALLBACK mode
  bool heartbeatExpired = heartbeatSeen && (nowMs - lastHeartbeatRxMs) > HEARTBEAT_TIMEOUT_MS;
  if (heartbeatExpired) {
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
          priorityClearanceActive = true;
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
      // Normal yellow stays 3s; priority-originated clearance uses its explicit demo interval.
      if (elapsed >= (priorityClearanceActive ? PRIORITY_YELLOW_MS : YELLOW_MS)) {
        transitionTo(ALL_RED_TO_EW, nowMs);
        if (currentMode == PRIORITY && targetPriorityAxis != AXIS_NONE) priorityClearanceActive = true;
      }
      break;

    case ALL_RED_TO_EW:
      // Normal all-red stays 2s; priority clearance uses its explicit demo interval.
      if (elapsed >= (priorityClearanceActive ? PRIORITY_ALL_RED_MS : ALL_RED_MS)) {
        if (targetPriorityAxis == AXIS_NS && currentMode == PRIORITY) {
          // Emergency vehicle on NS: grant green directly since all lights are already Red
          transitionTo(NS_GREEN, nowMs);
          activePriorityAxis = AXIS_NS;
          activePriorityApproach = targetPriorityApproach;
          holdGreenActive = true;
          priorityStartMs = nowMs;
          priorityCmdRxMs = nowMs;
          applyPhaseLights(currentPhase);
          Serial.println("[PRIORITY] NS_GREEN granted directly from ALL-RED");
        } else {
          transitionTo(EW_GREEN, nowMs);
          if (targetPriorityAxis == AXIS_EW && currentMode == PRIORITY) {
            activePriorityAxis = AXIS_EW;
            activePriorityApproach = targetPriorityApproach;
            holdGreenActive = true;
            priorityStartMs = nowMs;
            priorityCmdRxMs = nowMs;
            applyPhaseLights(currentPhase);
            Serial.println("[PRIORITY] EW_GREEN held for emergency vehicle");
          }
        }
        priorityClearanceActive = false;
      }
      break;

    case EW_GREEN:
      if (targetPriorityAxis == AXIS_NS && currentMode == PRIORITY) {
        // Invariant S4: Min green before cutting
        if (elapsed >= MIN_GREEN_MS) {
          priorityClearanceActive = true;
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
      // Normal yellow stays 3s; priority-originated clearance uses its explicit demo interval.
      if (elapsed >= (priorityClearanceActive ? PRIORITY_YELLOW_MS : YELLOW_MS)) {
        transitionTo(ALL_RED_TO_NS, nowMs);
        if (currentMode == PRIORITY && targetPriorityAxis != AXIS_NONE) priorityClearanceActive = true;
      }
      break;

    case ALL_RED_TO_NS:
      // Normal all-red stays 2s; priority clearance uses its explicit demo interval.
      if (elapsed >= (priorityClearanceActive ? PRIORITY_ALL_RED_MS : ALL_RED_MS)) {
        if (targetPriorityAxis == AXIS_EW && currentMode == PRIORITY) {
          // Emergency vehicle on EW: grant green directly since all lights are already Red
          transitionTo(EW_GREEN, nowMs);
          activePriorityAxis = AXIS_EW;
          activePriorityApproach = targetPriorityApproach;
          holdGreenActive = true;
          priorityStartMs = nowMs;
          priorityCmdRxMs = nowMs;
          applyPhaseLights(currentPhase);
          Serial.println("[PRIORITY] EW_GREEN granted directly from ALL-RED");
        } else {
          transitionTo(NS_GREEN, nowMs);
          if (targetPriorityAxis == AXIS_NS && currentMode == PRIORITY) {
            activePriorityAxis = AXIS_NS;
            activePriorityApproach = targetPriorityApproach;
            holdGreenActive = true;
            priorityStartMs = nowMs;
            priorityCmdRxMs = nowMs;
            applyPhaseLights(currentPhase);
            Serial.println("[PRIORITY] NS_GREEN held for emergency vehicle");
          }
        }
        priorityClearanceActive = false;
      }
      break;
  }
}

// ============================================================================
// NETWORK & FIREBASE REST
// ============================================================================
WiFiClientSecure secureClient;
HTTPClient firebaseHttp;

struct StateReportSnapshot {
  Phase phase;
  Mode mode;
  char lights[4];
  long lastSeq;
  bool hasPriorityApproach;
  char priorityApproach;
  unsigned long phaseElapsedMs;
  unsigned long uptimeMs;
  long rejectedCmds;
};

QueueHandle_t stateReportQueue = nullptr;

const char* lightToString(char light) {
  switch (light) {
    case 'G': return "G";
    case 'Y': return "Y";
    default: return "R";
  }
}

void stateReporterTask(void*) {
#if !LOCAL_TEST
  WiFiClientSecure stateSecureClient;
  stateSecureClient.setInsecure();
  HTTPClient stateHttp;
  stateHttp.setReuse(true);
  stateHttp.setConnectTimeout(2500);
  stateHttp.setTimeout(2500);

  StateReportSnapshot snapshot;
  for (;;) {
    if (xQueueReceive(stateReportQueue, &snapshot, portMAX_DELAY) != pdTRUE) continue;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[STATE] Skipping upload while Wi-Fi is disconnected; newer snapshot will replace it");
      continue;
    }

    StaticJsonDocument<512> doc;
    doc["phase"] = phaseToString(snapshot.phase);
    doc["mode"] = modeToString(snapshot.mode);
    JsonObject lights = doc.createNestedObject("lights");
    lights["N"] = lightToString(snapshot.lights[0]);
    lights["E"] = lightToString(snapshot.lights[1]);
    lights["S"] = lightToString(snapshot.lights[2]);
    lights["W"] = lightToString(snapshot.lights[3]);
    doc["last_seq"] = snapshot.lastSeq;
    if (snapshot.hasPriorityApproach) {
      doc["priority_approach"] = String(snapshot.priorityApproach);
    } else {
      doc["priority_approach"] = nullptr;
    }
    doc["phase_elapsed_ms"] = snapshot.phaseElapsedMs;
    doc["uptime_ms"] = snapshot.uptimeMs;
    doc["controller_id"] = "wokwi";
    doc["rejected_cmds"] = snapshot.rejectedCmds;

    String output;
    serializeJson(doc, output);
    String url = buildFirebaseUrl("/intersections/" + String(INTERSECTION_ID) + "/state");
    if (!stateHttp.begin(stateSecureClient, url)) {
      Serial.println("[STATE] Could not start Firebase request; waiting for next snapshot");
      continue;
    }
    int status = stateHttp.PUT(output);
    stateHttp.end();
    if (status < 200 || status >= 300) {
      Serial.printf("[STATE] Firebase PUT failed: %d (%s)\n", status, HTTPClient::errorToString(status).c_str());
    }
  }
#else
  vTaskDelete(nullptr);
#endif
}

bool queueStateReport(unsigned long nowMs) {
#if !LOCAL_TEST
  if (!stateReportQueue) return false;

  StateReportSnapshot snapshot;
  snapshot.phase = currentPhase;
  snapshot.mode = currentMode;
  snapshot.lastSeq = lastSeq;
  snapshot.phaseElapsedMs = nowMs - phaseStartMs;
  snapshot.uptimeMs = nowMs;
  snapshot.rejectedCmds = rejectedCmds;

  snapshot.hasPriorityApproach = holdGreenActive && activePriorityApproach != '\0' &&
      ((currentPhase == NS_GREEN && activePriorityAxis == AXIS_NS) ||
       (currentPhase == EW_GREEN && activePriorityAxis == AXIS_EW));
  snapshot.priorityApproach = snapshot.hasPriorityApproach ? activePriorityApproach : '\0';

  if (snapshot.hasPriorityApproach) {
    snapshot.lights[0] = activePriorityApproach == 'N' ? 'G' : 'R';
    snapshot.lights[1] = activePriorityApproach == 'E' ? 'G' : 'R';
    snapshot.lights[2] = activePriorityApproach == 'S' ? 'G' : 'R';
    snapshot.lights[3] = activePriorityApproach == 'W' ? 'G' : 'R';
  } else {
    switch (currentPhase) {
      case NS_GREEN:       snapshot.lights[0] = 'G'; snapshot.lights[1] = 'R'; snapshot.lights[2] = 'G'; snapshot.lights[3] = 'R'; break;
      case NS_YELLOW:      snapshot.lights[0] = 'Y'; snapshot.lights[1] = 'R'; snapshot.lights[2] = 'Y'; snapshot.lights[3] = 'R'; break;
      case ALL_RED_TO_EW:
      case ALL_RED_TO_NS:  snapshot.lights[0] = 'R'; snapshot.lights[1] = 'R'; snapshot.lights[2] = 'R'; snapshot.lights[3] = 'R'; break;
      case EW_GREEN:       snapshot.lights[0] = 'R'; snapshot.lights[1] = 'G'; snapshot.lights[2] = 'R'; snapshot.lights[3] = 'G'; break;
      case EW_YELLOW:      snapshot.lights[0] = 'R'; snapshot.lights[1] = 'Y'; snapshot.lights[2] = 'R'; snapshot.lights[3] = 'Y'; break;
    }
  }

  return xQueueOverwrite(stateReportQueue, &snapshot) == pdPASS;
#else
  return true;
#endif
}

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

void pollFirebaseMailbox(unsigned long nowMs) {
#if !LOCAL_TEST
  if (WiFi.status() != WL_CONNECTED) return;

  firebaseHttp.setReuse(true);
  firebaseHttp.setConnectTimeout(500);
  firebaseHttp.setTimeout(500);
  String url = buildFirebaseUrl("/intersections/" + String(INTERSECTION_ID));
  if (!firebaseHttp.begin(secureClient, url)) return;
  int code = firebaseHttp.GET();

  if (code == 200) {
    String payload = firebaseHttp.getString();
    DynamicJsonDocument doc(2048);
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      int counter = doc["heartbeat"] | 0;
      if (counter != lastHeartbeatVal) {
        lastHeartbeatVal = counter;
        lastHeartbeatRxMs = nowMs;
        heartbeatSeen = true;
        if (currentMode == FALLBACK) {
          currentMode = NORMAL;
          Serial.println("[SAFETY] Heartbeat restored. Returning to NORMAL mode.");
        }
      }

      JsonVariantConst commandValue = doc["command"];
      if (commandValue.is<JsonObjectConst>()) {
        JsonObjectConst command = commandValue.as<JsonObjectConst>();
        long seq = command["seq"] | 0;
        const char* cmd = command["cmd"] | "";
        const char* axisStr = command["axis"] | "";
        const char* approachStr = command["approach"] | "";
        int ttl = command["ttl_s"] | 15;

        // Invariant S6: Seq must strictly increase
        if (seq > lastSeq) {
          lastSeq = seq;
          if (strcmp(cmd, "PRIORITY") == 0) {
            Axis reqAxis = AXIS_NONE;
            if (strcmp(axisStr, "NS") == 0) reqAxis = AXIS_NS;
            else if (strcmp(axisStr, "EW") == 0) reqAxis = AXIS_EW;

            char reqApproach = '\0';
            bool invalidApproach = false;
            if (strlen(approachStr) == 1 &&
                (approachStr[0] == 'N' || approachStr[0] == 'E' ||
                 approachStr[0] == 'S' || approachStr[0] == 'W')) {
              reqApproach = approachStr[0];
              bool approachMatchesAxis =
                  ((reqApproach == 'N' || reqApproach == 'S') && reqAxis == AXIS_NS) ||
                  ((reqApproach == 'E' || reqApproach == 'W') && reqAxis == AXIS_EW);
              if (!approachMatchesAxis) invalidApproach = true;
            } else if (strlen(approachStr) > 0) {
              invalidApproach = true;
            }

            if (reqAxis != AXIS_NONE && !invalidApproach && ttl > 0) {
              targetPriorityAxis = reqAxis;
              targetPriorityApproach = reqApproach;
              currentMode = PRIORITY;
              priorityCmdRxMs = nowMs;
              priorityTtlMs = ttl * 1000UL;

              // Rule 1: If axis is already green, hold immediately
              if ((currentPhase == NS_GREEN && reqAxis == AXIS_NS) ||
                  (currentPhase == EW_GREEN && reqAxis == AXIS_EW)) {
                activePriorityAxis = reqAxis;
                activePriorityApproach = reqApproach;
                holdGreenActive = true;
                priorityStartMs = nowMs;
                priorityCmdRxMs = nowMs;
                applyPhaseLights(currentPhase);
              }
              Serial.printf("[CMD] PRIORITY seq=%ld for axis=%s\n", seq, axisStr);
            } else {
              rejectedCmds++;
              Serial.printf("[SAFETY] Rejected malformed PRIORITY seq=%ld\n", seq);
            }
          } else if (strcmp(cmd, "CLEAR") == 0) {
            releasePriority();
            Serial.printf("[CMD] CLEAR seq=%ld\n", seq);
          } else {
            rejectedCmds++;
          }
        }
      }
    }
  }
  firebaseHttp.end();
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
#if !LOCAL_TEST
  stateReportQueue = xQueueCreate(1, sizeof(StateReportSnapshot));
  if (stateReportQueue && xTaskCreatePinnedToCore(stateReporterTask, "firebase_state", 8192, nullptr, 1, nullptr, 0) == pdPASS) {
    Serial.println("[STATE] Asynchronous Firebase reporter started");
  } else {
    Serial.println("[STATE] Could not start Firebase reporter task");
  }
#endif
  Serial.println("System initialized. Starting safety control loop.");
}

void loop() {
  unsigned long now = millis();

  // 1. Advance FSM and check invariants
  tickFSM(now);

  // 2. Drive status LED and buzzer
  updateStatusIndicators(now);

  // 3. Poll command and heartbeat together to avoid duplicate TLS requests.
  if (now - lastCommandPollMs >= POLL_MS) {
    lastCommandPollMs = now;
    pollFirebaseMailbox(now);
  }

  // 4. Queue the newest state without blocking the safety control loop.
  bool phaseChanged = (lastPhase != currentPhase);
  bool modeChanged = (lastReportedMode != currentMode);
  bool commandChanged = (lastReportedSeq != lastSeq);
  bool timerExpired = (now - lastStateReportMs >= STATE_REPORT_INTERVAL_MS);
  bool retryReady = (now - lastStateReportAttemptMs >= 500);
  if ((phaseChanged || modeChanged || commandChanged || timerExpired) && retryReady) {
    lastStateReportAttemptMs = now;
    if (queueStateReport(now)) {
      lastPhase = currentPhase;
      lastReportedMode = currentMode;
      lastReportedSeq = lastSeq;
      lastStateReportMs = now;
    }
  }
}
