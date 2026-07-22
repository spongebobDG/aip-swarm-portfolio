#include "status_monitor.h"
#include "protocol.h"
#include "motor_control.h"
#include "servo_control.h"
#include <esp_system.h>

namespace {
    uint16_t s_boot_flag      = 0;
    uint16_t s_last_flags     = 0xFFFF;
    uint32_t s_last_status_ms = 0;

    uint32_t s_loop_count     = 0;
    uint32_t s_loop_hz_t0     = 0;
    uint16_t s_loop_hz_cache  = 0;

    uint16_t composeFlags() {
        uint16_t f = s_boot_flag;
        if (MotorControl::isWatchdogTripped()) f |= STAT_WATCHDOG_TRIPPED;
        if (MotorControl::isEncoderStalled(1)) f |= STAT_ENC1_STALL;
        if (MotorControl::isEncoderStalled(2)) f |= STAT_ENC2_STALL;
        if (ServoControl::consumeOOR())        f |= STAT_SERVO_CMD_OOR;
        return f;
    }
}

void StatusMonitor::begin() {
    s_last_flags     = 0xFFFF;
    s_last_status_ms = 0;
    s_loop_count     = 0;
    s_loop_hz_t0     = millis();
    s_loop_hz_cache  = 0;

    esp_reset_reason_t r = esp_reset_reason();
    s_boot_flag = (r == ESP_RST_BROWNOUT) ? STAT_BOOT_BROWNOUT : 0;
}

void StatusMonitor::noteLoopIter() {
    s_loop_count++;
    const uint32_t now = millis();
    if (now - s_loop_hz_t0 >= LOOP_HZ_WINDOW_MS) {
        s_loop_hz_cache = (uint16_t)((s_loop_count > 65535u) ? 65535u : s_loop_count);
        s_loop_count = 0;
        s_loop_hz_t0 = now;
    }
}

void StatusMonitor::tick() {
    const uint32_t now = millis();
    const uint16_t f   = composeFlags();
    const bool flag_changed = (f != s_last_flags);
    if (!flag_changed && (now - s_last_status_ms < STATUS_FB_MS)) return;

    s_last_flags     = f;
    s_last_status_ms = now;
    Protocol::sendStatus(
        now,
        f,
        Protocol::badCountAndReset(),
        s_loop_hz_cache,
        (uint16_t)(ESP.getFreeHeap() / 1024)
    );
}

uint16_t StatusMonitor::currentFlags() { return composeFlags(); }
