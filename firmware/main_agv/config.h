#pragma once
#include <Arduino.h>
#include <stdint.h>

// arduino-esp32 v2.x LEDC API(ledcSetup/ledcAttachPin) 전용.
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
#error "arduino-esp32 v3.x는 LEDC API가 달라 컴파일되지 않습니다. 코어를 2.x로 고정하거나 ledcAttach로 포팅하세요."
#endif

// ── 물리 파라미터 ────────────────────────────────
constexpr float WHEEL_RADIUS  = 0.056f;    // 실측 (URDF wheel_radius)
constexpr float TRACK_WIDTH   = 0.3015f;    // 실측 (URDF wheel_separation)
constexpr float MAX_WHEEL_VEL = 1.50f;
constexpr int   PPR           = 700;
constexpr int   CPR           = PPR * 4;

// ── DC 모터 핀맵 (BTS7960 ×2) ────────────────────
constexpr int M1_RPWM = 21, M1_LPWM = 19, M1_REN = 18, M1_LEN = 17, M1_ENC_A = 23, M1_ENC_B = 22;
constexpr int M2_RPWM = 25, M2_LPWM = 26, M2_REN = 27, M2_LEN = 14, M2_ENC_A = 32, M2_ENC_B = 33;

// ── PWM (LEDC) 채널 ──────────────────────────────
constexpr int DC_PWM_FREQ = 5000, DC_PWM_RES = 8;
constexpr int M1_R_CH = 0, M1_L_CH = 1, M2_R_CH = 2, M2_L_CH = 3;

// ── 서보 핀맵 (MG996R ×4) ────────────────────────
constexpr int SERVO_PINS[4] = { 16, 4, 15, 13 };
constexpr int SERVO_CH[4]   = { 4, 5, 6, 7 };
constexpr int SERVO_FREQ    = 50;
constexpr int SERVO_RES     = 16;

constexpr int           SERVO_PULSE_MIN_US     = 500;
constexpr int           SERVO_PULSE_MAX_US     = 2500;
constexpr int           SERVO_PERIOD_US        = 20000;
constexpr uint8_t       SERVO_ANGLE_MIN        = 0;
constexpr uint8_t       SERVO_ANGLE_MAX        = 180;
constexpr uint8_t       SERVO_ANGLE_HOME       = 90;
constexpr unsigned long SERVO_TICK_MS          = 20;

// ── 서보 모션 프로파일 (오버슈트/진자 진동 억제) ───────
// 인덱스별 최대 각속도[deg/s]. 1번(=인덱스 1, 암 전체 부하)은 느리게.
constexpr float SERVO_MAX_DPS[4]          = { 60.0f, 15.0f, 15.0f, 60.0f };
// 목표 접근율[1/s]: 남은 각도에 비례해 속도를 줄여 부드럽게 안착(작을수록 더 부드러움).
constexpr float SERVO_APPROACH_RATE[4]    = { 12.0f,  3.0f, 3.0f, 12.0f };
// 목표 근처 스납 임계값[deg] — 미세 크리프 방지.
constexpr float SERVO_SNAP_DEG            = 0.5f;
// 비대칭 감속: 암 서보가 '중력 보조 방향'으로 움직일 때 속도·접근율 배율(0~1).
constexpr int   SERVO_ARM_IDX             = 1;     // 암 부하 서보(GPIO4)
constexpr int   SERVO_ARM_DESCEND_DIR     = -1;    // 중력보조(하강) 방향의 각도변화 부호. 반대로 흔들리면 +1로
constexpr float SERVO_GRAVITY_SPEED_SCALE = 0.5f;  // 중력보조 방향 속도·접근율 배율
// 자세: 부팅 시 유지 / 해제 전 정렬
constexpr uint8_t SERVO_BOOT_POSE[4]      = { 90, 60, 90, 125 };  // 기동 시 목표 자세(무게중심 안정)
constexpr uint8_t SERVO_PARK_POSE[4]      = { 90,  0,  0, 90 };  // 해제 전 정렬 자세(이 자세에서 detach)

// ── 주행 / 제어 주기 ────────────────────────────
constexpr int           MIN_PWM        = 15;
constexpr int           ACCEL_STEP     = 5;
constexpr int           ACCEL_INTERVAL = 15;
constexpr int           SYNC_INTERVAL  = 20;
constexpr unsigned long FEEDBACK_MS    = 50;
constexpr unsigned long WATCHDOG_MS    = 1000;
constexpr unsigned long ENC_STALL_MS   = 1000;
// ── 속도 루프(per-wheel FF + PI) 게인 ───────────
constexpr float         KP_VEL_P  = 35.0f;
constexpr float         KI_VEL    = 18.0f;
constexpr float         VEL_I_MAX = 110.0f;

// ── STATUS 보고 ─────────────────────────────────
constexpr unsigned long STATUS_FB_MS      = 1000;
constexpr unsigned long LOOP_HZ_WINDOW_MS = 1000;

// ── PID 게인 ────────────────────────────────────
constexpr float SYNC_KP = 1.2f, SYNC_KI = 0.05f, SYNC_KD = 0.3f;

// ── 패킷 헤더 / 타입 ────────────────────────────
constexpr uint8_t PKT_H1 = 0xAA;
constexpr uint8_t PKT_H2 = 0x55;

enum PacketType : uint8_t {
    PKT_CMD_VEL       = 0x01,  // PC → ESP32
    PKT_MOTOR_FB      = 0x02,  // ESP32 → PC
    PKT_SERVO         = 0x03,  // PC → ESP32
    PKT_SERVO_FB      = 0x04,  // ESP32 → PC
    PKT_STATUS        = 0x05,  // ESP32 → PC
    PKT_SERVO_RELEASE = 0x06,  // PC → ESP32 (정렬 자세 이동 후 전체 detach)
    PKT_RESET         = 0x07,  // PC → ESP32 (esp_restart, payload 1B: mode=0x00)
    PKT_BEEP          = 0x08,  // PC → ESP32 (비프음 요청,  payload 1B: Buzzer::Pattern)
};

// ── 부저 ────────────────────────────────────────
// 패시브 부저(LEDC PWM 구동). 부저 미장착 시 0으로 변경.
#define BUZZER_ENABLED 1
// 실제 연결 GPIO 핀으로 변경하세요 (GPIO0/1/6-11 제외).
constexpr int BUZZER_PIN = 2;
// 모터(0-3) + 서보(4-7) 이후 빈 채널.
constexpr int BUZZER_CH  = 8;

// ── STATUS flags 비트마스크 ────────────────────
constexpr uint16_t STAT_WATCHDOG_TRIPPED = 1 << 0;
constexpr uint16_t STAT_ENC1_STALL       = 1 << 1;
constexpr uint16_t STAT_ENC2_STALL       = 1 << 2;
constexpr uint16_t STAT_SERVO_CMD_OOR    = 1 << 3;
constexpr uint16_t STAT_BOOT_BROWNOUT    = 1 << 4;
