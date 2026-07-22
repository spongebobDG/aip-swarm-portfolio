#include "servo_control.h"
#include <Preferences.h>

namespace {
    // Windows(CP210x) 에서 포트 close 시 DTR->EN 토글로 ESP32 가 리셋되어도
    // 직전 SERVO_RELEASE(정상 종료)면 PARK_POSE 로 부팅하기 위한 NVS 플래그.
    Preferences  prefs;
    const char*  NVS_NS        = "servo";
    const char*  NVS_KEY_PARK  = "boot_park";
    bool         nvs_park_set  = false;   // NVS 플래그 RAM 미러(반복 flash write 방지)

    float    target_deg[4]   = {90, 90, 90, 90};
    float    current_deg[4]  = {90, 90, 90, 90};
    bool     servo_armed[4]  = {false, false, false, false};
    bool     oor_flag        = false;
    bool     releasing       = false;     // 정렬 자세 이동 후 전체 detach 시퀀스
    uint32_t last_tick_ms    = 0;

    inline uint32_t degToDuty(float deg) {
        deg = constrain(deg, (float)SERVO_ANGLE_MIN, (float)SERVO_ANGLE_MAX);
        uint32_t us = SERVO_PULSE_MIN_US +
                      (uint32_t)((deg / 180.0f) * (SERVO_PULSE_MAX_US - SERVO_PULSE_MIN_US));
        const uint32_t maxDuty = (1UL << SERVO_RES) - 1;
        return (uint32_t)((uint64_t)us * maxDuty / SERVO_PERIOD_US);
    }

    inline int sgnf(float x) { return (x > 0.0f) ? 1 : (x < 0.0f ? -1 : 0); }
}

void ServoControl::begin() {
    // 종료-리셋(Windows close 시 DTR->EN 토글) 판별: 직전에 SERVO_RELEASE 를
    // 받았으면(=정상 종료) BOOT_POSE 대신 PARK_POSE 로 부팅한다.
    // consume-once: 읽는 즉시 플래그를 0 으로 지워, '다음' 부팅(세션 시작 open-reset)은
    // 정상적으로 BOOT_POSE 로 기동하도록 한다.
    bool park_boot = false;
    prefs.begin(NVS_NS, false);
    if (prefs.getUChar(NVS_KEY_PARK, 0) == 1) {
        park_boot = true;
        prefs.putUChar(NVS_KEY_PARK, 0);
    }
    prefs.end();
    nvs_park_set = false;

    for (int i = 0; i < 4; i++) {
        ledcSetup(SERVO_CH[i], SERVO_FREQ, SERVO_RES);
        ledcAttachPin(SERVO_PINS[i], SERVO_CH[i]);
        // 직전 종료가 정렬 자세(SERVO_PARK_POSE)에서 detach됐다고 가정하고,
        // 일반 부팅은 그 위치에서 부팅 자세(SERVO_BOOT_POSE)로 '천천히' 이행.
        // 종료-리셋이면 PARK 에 그대로 머문다(target=current=PARK -> 무동작).
        current_deg[i] = (float)SERVO_PARK_POSE[i];
        target_deg[i]  = park_boot ? (float)SERVO_PARK_POSE[i]
                                   : (float)SERVO_BOOT_POSE[i];
        servo_armed[i] = true;
        ledcWrite(SERVO_CH[i], degToDuty(current_deg[i]));
    }
    releasing    = false;
    last_tick_ms = millis();
}

void ServoControl::setAngle(uint8_t idx, uint8_t deg) {
    if (idx >= 4) return;
    if (deg > SERVO_ANGLE_MAX) { oor_flag = true; deg = SERVO_ANGLE_MAX; }
    releasing = false;                       // 새 명령이 오면 해제 시퀀스 취소
    if (nvs_park_set) {                       // 실제 구동 명령 -> 종료-PARK 의도 취소
        prefs.begin(NVS_NS, false);
        prefs.putUChar(NVS_KEY_PARK, 0);
        prefs.end();
        nvs_park_set = false;
    }
    target_deg[idx] = (float)deg;
    if (!servo_armed[idx]) {
        current_deg[idx] = target_deg[idx];  // detach 상태에서 재명령 시 현재값 동기화
        servo_armed[idx] = true;
    }
}

void ServoControl::setAll(const uint8_t deg[4]) {
    for (uint8_t i = 0; i < 4; ++i) setAngle(i, deg[i]);
}

void ServoControl::requestRelease(uint8_t /*mode*/) {
    // 정렬 자세로 이동시킨 뒤(tick에서 안착 확인) 전체 detach.
    releasing = true;
    for (int i = 0; i < 4; ++i) {
        target_deg[i]  = (float)SERVO_PARK_POSE[i];
        servo_armed[i] = true;
    }
    // 종료-리셋(Windows close) 후에도 PARK 로 복귀하도록 NVS 플래그 기록.
    prefs.begin(NVS_NS, false);
    prefs.putUChar(NVS_KEY_PARK, 1);
    prefs.end();
    nvs_park_set = true;
}

void ServoControl::getCurrent(uint8_t out[4]) {
    for (int i = 0; i < 4; ++i) out[i] = (uint8_t)(current_deg[i] + 0.5f);
}

void ServoControl::tick() {
    const uint32_t now = millis();
    if (now - last_tick_ms < SERVO_TICK_MS) return;
    float dt = (now - last_tick_ms) / 1000.0f;
    last_tick_ms = now;
    if (dt > 0.1f) dt = 0.1f;                // 비정상적으로 큰 dt 방어

    bool all_settled = true;
    for (int i = 0; i < 4; ++i) {
        if (!servo_armed[i]) { ledcWrite(SERVO_CH[i], 0); continue; }

        float diff = target_deg[i] - current_deg[i];

        // 인덱스별 속도 상한 + 비대칭(중력 보조 방향) 감속
        float vmax = SERVO_MAX_DPS[i];
        float rate = SERVO_APPROACH_RATE[i];
        if (i == SERVO_ARM_IDX && sgnf(diff) == SERVO_ARM_DESCEND_DIR) {
            vmax *= SERVO_GRAVITY_SPEED_SCALE;
            rate *= SERVO_GRAVITY_SPEED_SCALE;
        }

        if (fabsf(diff) <= SERVO_SNAP_DEG) {
            current_deg[i] = target_deg[i];          // 스납(미세 크리프 방지)
        } else {
            // ease-out: 남은 각도에 비례해 속도를 줄여 부드럽게 안착 -> 오버슈트 억제
            float speed = rate * fabsf(diff);        // [deg/s]
            if (speed > vmax) speed = vmax;
            float step = speed * dt;
            current_deg[i] += (diff > 0.0f) ? step : -step;
            all_settled = false;
        }
        ledcWrite(SERVO_CH[i], degToDuty(current_deg[i]));
    }

    // 정렬 자세 도달 시 전체 detach (전류/락 해제)
    if (releasing && all_settled) {
        for (int i = 0; i < 4; ++i) {
            ledcWrite(SERVO_CH[i], 0);
            servo_armed[i] = false;
        }
        releasing = false;
    }
}

bool ServoControl::consumeOOR() {
    bool v = oor_flag;
    oor_flag = false;
    return v;
}
