#pragma once
#include "config.h"

namespace ServoControl {
    void begin();
    void setAngle(uint8_t idx, uint8_t deg);
    void setAll(const uint8_t deg[4]);
    void requestRelease(uint8_t mode = 0);
    void getCurrent(uint8_t out[4]);
    void tick();
    bool consumeOOR();
}