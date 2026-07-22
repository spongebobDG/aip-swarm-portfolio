#pragma once
#include "config.h"

namespace MotorControl {
    void begin();
    void setTargetVelocities(float vel_left, float vel_right);

    void tickAccel();
    void tickSyncPID();
    void tickVelPID();

    void notifyCmdReceived();
    void checkWatchdog();

    void snapshotEncoders(int32_t& e1, int32_t& e2);

    // ★ STATUS
    bool isWatchdogTripped();
    bool isEncoderStalled(int idx);
}