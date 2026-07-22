#include "buzzer.h"
#include "config.h"

#if BUZZER_ENABLED

namespace {

// Note : {주파수_Hz, 지속_ms}. freq=0 → 묵음(쉼표). ms=0 → 시퀀스 종료 sentinel.
struct Note { uint16_t freq_hz; uint16_t ms; };

// 부팅 완료: 낮은음 → 쉼표 → 높은음
static const Note SEQ_BOOT[]   = { {880, 80}, {0, 30}, {1320, 150}, {0, 0} };
// 단음
static const Note SEQ_SINGLE[] = { {1000, 100}, {0, 0} };
// 이중음
static const Note SEQ_DOUBLE[] = { {1000, 80}, {0, 50}, {1000, 80}, {0, 0} };
// 오류: 3회 빠른 비프
static const Note SEQ_ERROR[]  = { {880, 60}, {0, 30}, {880, 60}, {0, 30}, {880, 60}, {0, 0} };

static const Note* const ALL_SEQS[] = { SEQ_SINGLE, SEQ_DOUBLE, SEQ_BOOT, SEQ_ERROR };
static constexpr int SEQ_COUNT = (int)(sizeof(ALL_SEQS) / sizeof(ALL_SEQS[0]));

// 재생 상태
static const Note* s_seq    = nullptr;
static int         s_idx    = 0;
static uint32_t    s_note_t0 = 0;

void applyNote(const Note& n) {
    if (n.freq_hz > 0) {
        ledcWriteTone(BUZZER_CH, n.freq_hz);
    } else {
        ledcWrite(BUZZER_CH, 0);
    }
}

}  // namespace

void Buzzer::begin() {
    ledcSetup(BUZZER_CH, 2000, 8);
    ledcAttachPin(BUZZER_PIN, BUZZER_CH);
    ledcWrite(BUZZER_CH, 0);
}

void Buzzer::play(Pattern p) {
    if ((int)p >= SEQ_COUNT) return;
    s_seq    = ALL_SEQS[(int)p];
    s_idx    = 0;
    s_note_t0 = millis();
    applyNote(s_seq[0]);
}

void Buzzer::tick() {
    if (!s_seq) return;
    const uint32_t now = millis();
    const Note& cur = s_seq[s_idx];
    if (cur.ms == 0) {              // sentinel — 시퀀스 끝
        ledcWrite(BUZZER_CH, 0);
        s_seq = nullptr;
        return;
    }
    if (now - s_note_t0 >= (uint32_t)cur.ms) {
        s_idx++;
        s_note_t0 = now;
        const Note& next = s_seq[s_idx];
        if (next.ms == 0) {
            ledcWrite(BUZZER_CH, 0);
            s_seq = nullptr;
        } else {
            applyNote(next);
        }
    }
}

bool Buzzer::isBusy() { return s_seq != nullptr; }

#endif  // BUZZER_ENABLED
