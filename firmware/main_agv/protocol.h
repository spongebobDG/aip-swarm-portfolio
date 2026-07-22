#pragma once
#include "config.h"

#pragma pack(push, 1)
// ── RX payload (PC → ESP32) ─────────────────────
struct CmdVelPacket {
    float linear_ms;
    float angular_rads;
};

struct ServoPacket {
    uint8_t angles[4];
};

struct ServoReleasePacket {
    uint8_t mode;   // 0 = SERVO_PARK_POSE 정렬 후 전체 detach
};

struct ResetPacket {
    uint8_t mode;   // 0 = 소프트 리셋 (esp_restart)
};

struct BeepPacket {
    uint8_t pattern;  // Buzzer::Pattern (0=단음, 1=이중, 2=부팅, 3=오류)
};

// ── TX framed (ESP32 → PC) ──────────────────────
struct MotorFbPacket {
    uint8_t h1   = PKT_H1;
    uint8_t h2   = PKT_H2;
    uint8_t type = PKT_MOTOR_FB;
    int32_t enc1;
    int32_t enc2;
    uint8_t checksum;
};

struct ServoFbPacket {
    uint8_t h1   = PKT_H1;
    uint8_t h2   = PKT_H2;
    uint8_t type = PKT_SERVO_FB;
    uint8_t angles[4];
    uint8_t checksum;
};

struct StatusPacket {
    uint8_t  h1   = PKT_H1;
    uint8_t  h2   = PKT_H2;
    uint8_t  type = PKT_STATUS;
    uint32_t uptime_ms;
    uint16_t flags;
    uint16_t bad_packets;
    uint16_t loop_hz;
    uint16_t free_heap_kb;
    uint8_t  checksum;
};
#pragma pack(pop)

using ProtocolHandler = void (*)(const uint8_t* payload, size_t len);

namespace Protocol {
    void     begin(unsigned long baud = 115200);
    void     registerHandler(uint8_t type, ProtocolHandler cb, size_t payloadLen);
    void     poll();
    void     sendMotorFb(int32_t enc1, int32_t enc2);
    void     sendServoFb(const uint8_t angles[4]);
    void     sendStatus(uint32_t uptime_ms, uint16_t flags,
                        uint16_t bad_packets, uint16_t loop_hz, uint16_t free_heap_kb);
    uint32_t badCount();
    uint16_t badCountAndReset();
}