#include "config.h"
#include "protocol.h"
#include "motor_control.h"
#include "servo_control.h"
#include "status_monitor.h"
#include "buzzer.h"
#include <string.h>
#include <esp_system.h>

static void onCmdVel(const uint8_t* payload, size_t) {
    CmdVelPacket pkt;
    memcpy(&pkt, payload, sizeof(pkt));
    float vl = pkt.linear_ms - pkt.angular_rads * (TRACK_WIDTH / 2.0f);
    float vr = pkt.linear_ms + pkt.angular_rads * (TRACK_WIDTH / 2.0f);
    MotorControl::setTargetVelocities(vl, vr);
    MotorControl::notifyCmdReceived();
}
static void onServo(const uint8_t* payload, size_t) {
    ServoPacket pkt;
    memcpy(&pkt, payload, sizeof(pkt));
    ServoControl::setAll(pkt.angles);
}
static void onServoRelease(const uint8_t* payload, size_t) {
    ServoReleasePacket pkt;
    memcpy(&pkt, payload, sizeof(pkt));
    ServoControl::requestRelease(pkt.mode);
}
static void onReset(const uint8_t*, size_t) {
    // 모터 정지 후 시리얼 플러시, 그 뒤 소프트 리셋
    MotorControl::setTargetVelocities(0.0f, 0.0f);
    Serial.flush();
    delay(30);
    esp_restart();
}
static void onBeep(const uint8_t* payload, size_t) {
    Buzzer::play(static_cast<Buzzer::Pattern>(payload[0]));
}

uint32_t lastAccel = 0, lastSync = 0, lastMotorFb = 0, lastServoFb = 0;

void setup() {
    Protocol::begin(115200);
    MotorControl::begin();
    ServoControl::begin();
    StatusMonitor::begin();
    Buzzer::begin();
    Protocol::registerHandler(PKT_CMD_VEL,       onCmdVel,       sizeof(CmdVelPacket));
    Protocol::registerHandler(PKT_SERVO,         onServo,        sizeof(ServoPacket));
    Protocol::registerHandler(PKT_SERVO_RELEASE, onServoRelease, sizeof(ServoReleasePacket));
    Protocol::registerHandler(PKT_RESET,         onReset,        sizeof(ResetPacket));
    Protocol::registerHandler(PKT_BEEP,          onBeep,         sizeof(BeepPacket));
    Buzzer::play(Buzzer::BOOT);  // 초기화 완료 신호
}

void loop() {
    const uint32_t now = millis();
    StatusMonitor::noteLoopIter();
    Protocol::poll();
    Buzzer::tick();

    if (now - lastAccel >= (uint32_t)ACCEL_INTERVAL) { lastAccel = now; MotorControl::tickAccel();   }
    if (now - lastSync  >= (uint32_t)SYNC_INTERVAL)  { lastSync  = now; MotorControl::tickSyncPID(); }

    if (now - lastMotorFb >= FEEDBACK_MS) {
        lastMotorFb = now;
        MotorControl::tickVelPID();
        int32_t e1, e2; MotorControl::snapshotEncoders(e1, e2);
        Protocol::sendMotorFb(e1, e2);
    }

    ServoControl::tick();

    if (now - lastServoFb >= FEEDBACK_MS) {
        lastServoFb = now;
        uint8_t s[4];
        ServoControl::getCurrent(s);
        Protocol::sendServoFb(s);
    }

    StatusMonitor::tick();
    MotorControl::checkWatchdog();
}