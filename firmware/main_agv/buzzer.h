#pragma once
#include <Arduino.h>

#if BUZZER_ENABLED

namespace Buzzer {
    enum Pattern : uint8_t {
        SINGLE = 0,  // 단음 1회
        DOUBLE = 1,  // 이중음 2회
        BOOT   = 2,  // 부팅 완료 (낮은음→높은음 상승)
        ERROR  = 3,  // 오류 (3회 빠른)
    };

    void begin();
    void play(Pattern p);
    void tick();
    bool isBusy();
}

#else  // BUZZER_ENABLED == 0 : 모든 호출을 noop으로 대체
namespace Buzzer {
    enum Pattern : uint8_t { SINGLE=0, DOUBLE=1, BOOT=2, ERROR=3 };
    inline void begin() {}
    inline void play(Pattern) {}
    inline void tick() {}
    inline bool isBusy() { return false; }
}
#endif
