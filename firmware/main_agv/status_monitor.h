#pragma once
#include "config.h"

namespace StatusMonitor {
    void     begin();
    void     noteLoopIter();
    void     tick();
    uint16_t currentFlags();
}