#include "protocol.h"

namespace {
    struct Slot { ProtocolHandler cb = nullptr; size_t len = 0; };
    Slot     slots[256];
    uint32_t bad_count_total  = 0;
    uint32_t bad_count_window = 0;

    uint8_t xorChecksum(uint8_t type, const uint8_t* buf, size_t n) {
        uint8_t cs = type;
        for (size_t i = 0; i < n; i++) cs ^= buf[i];
        return cs;
    }
    inline void bumpBad() {
        bad_count_total++;
        if (bad_count_window < 0xFFFF) bad_count_window++;
    }

    enum RxState : uint8_t { WAIT_H1, WAIT_H2, WAIT_TYPE, WAIT_PAYLOAD, WAIT_CKS };
    RxState rx_state = WAIT_H1;
    uint8_t rx_type  = 0;
    size_t  rx_len   = 0;
    size_t  rx_idx   = 0;
    uint8_t rx_buf[64];
}

void Protocol::begin(unsigned long baud) {
    Serial.begin(baud);
    Serial.setTimeout(50);
}

void Protocol::registerHandler(uint8_t type, ProtocolHandler cb, size_t payloadLen) {
    slots[type].cb  = cb;
    slots[type].len = payloadLen;
}

void Protocol::poll() {
    while (Serial.available() > 0) {
        uint8_t b = (uint8_t)Serial.read();
        switch (rx_state) {
            case WAIT_H1:
                if (b == PKT_H1) rx_state = WAIT_H2;
                break;
            case WAIT_H2:
                if      (b == PKT_H2) rx_state = WAIT_TYPE;
                else if (b == PKT_H1) rx_state = WAIT_H2;
                else                  rx_state = WAIT_H1;
                break;
            case WAIT_TYPE: {
                rx_type = b;
                Slot& s = slots[rx_type];
                if (!s.cb || s.len == 0 || s.len > sizeof(rx_buf)) {
                    bumpBad();
                    rx_state = WAIT_H1;
                } else {
                    rx_len   = s.len;
                    rx_idx   = 0;
                    rx_state = WAIT_PAYLOAD;
                }
                break;
            }
            case WAIT_PAYLOAD:
                rx_buf[rx_idx++] = b;
                if (rx_idx >= rx_len) rx_state = WAIT_CKS;
                break;
            case WAIT_CKS:
                if (xorChecksum(rx_type, rx_buf, rx_len) == b) slots[rx_type].cb(rx_buf, rx_len);
                else                                            bumpBad();
                rx_state = WAIT_H1;
                break;
        }
    }
}

void Protocol::sendMotorFb(int32_t enc1, int32_t enc2) {
    MotorFbPacket p;
    p.enc1 = enc1; p.enc2 = enc2;
    p.checksum = xorChecksum(p.type,
        reinterpret_cast<uint8_t*>(&p.enc1), sizeof(int32_t) * 2);
    if (Serial.availableForWrite() >= (int)sizeof(p))
        Serial.write(reinterpret_cast<uint8_t*>(&p), sizeof(p));
}

void Protocol::sendServoFb(const uint8_t angles[4]) {
    ServoFbPacket p;
    p.angles[0] = angles[0];
    p.angles[1] = angles[1];
    p.angles[2] = angles[2];
    p.angles[3] = angles[3];
    p.checksum = xorChecksum(p.type, p.angles, 4);
    if (Serial.availableForWrite() >= (int)sizeof(p))
        Serial.write(reinterpret_cast<uint8_t*>(&p), sizeof(p));
}

void Protocol::sendStatus(uint32_t uptime_ms, uint16_t flags,
                          uint16_t bad_packets, uint16_t loop_hz, uint16_t free_heap_kb) {
    StatusPacket p;
    p.uptime_ms    = uptime_ms;
    p.flags        = flags;
    p.bad_packets  = bad_packets;
    p.loop_hz      = loop_hz;
    p.free_heap_kb = free_heap_kb;
    p.checksum = xorChecksum(p.type,
        reinterpret_cast<uint8_t*>(&p.uptime_ms), sizeof(p) - 4);
    if (Serial.availableForWrite() >= (int)sizeof(p))
        Serial.write(reinterpret_cast<uint8_t*>(&p), sizeof(p));
}

uint32_t Protocol::badCount() { return bad_count_total; }

uint16_t Protocol::badCountAndReset() {
    uint16_t v = (uint16_t)bad_count_window;
    bad_count_window = 0;
    return v;
}
