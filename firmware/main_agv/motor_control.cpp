#include "motor_control.h"
#include "config.h"
#include <Arduino.h>

// ===================================================================
//  MotorControl  (per-wheel FF + PI 속도루프 + 대칭 동기)
// ===================================================================
namespace {
    // ---- 엔코더 위치(ISR에서 갱신) ----
    volatile int32_t m1_pos = 0;
    volatile int32_t m2_pos = 0;

    // ---- 목표 / 지령 상태 ----
    float target_v1 = 0.0f, target_v2 = 0.0f;
    float target_spd1 = 0.0f, target_spd2 = 0.0f;
    int   cur_spd1 = 0, cur_spd2 = 0;
    float ipart1 = 0.0f, ipart2 = 0.0f;

    // ---- 동기 PID ----
    int32_t last_m1_pos = 0, last_m2_pos = 0;
    float   prev_v1 = 0.0f, prev_v2 = 0.0f;
    int32_t accum_error = 0, last_error = 0;
    float   integral = 0.0f;
    int     base_adj = 0;

    // ---- 워치독 / 스톨 ----
    uint32_t last_cmd_time = 0;
    bool     watchdog_tripped = false;
    int32_t  stall_last_m1 = 0, stall_last_m2 = 0;
    uint32_t stall_t1 = 0, stall_t2 = 0;

    // ---- ISR (4체배 증분, QUAD_LUT) ----
    const int8_t QUAD_LUT[16] = {0,+1,-1,0,-1,0,0,+1,+1,0,0,-1,0,-1,+1,0};
    volatile uint8_t m1_prev = 0, m2_prev = 0;

    inline void m1_isr() {
        uint8_t s = (digitalRead(M1_ENC_A) << 1) | digitalRead(M1_ENC_B);
        m1_pos += -QUAD_LUT[(m1_prev << 2) | s];
        m1_prev = s;
    }
    inline void m2_isr() {
        uint8_t s = (digitalRead(M2_ENC_A) << 1) | digitalRead(M2_ENC_B);
        m2_pos += +QUAD_LUT[(m2_prev << 2) | s];
        m2_prev = s;
    }
    void IRAM_ATTR m1_isr_a() { m1_isr(); }
    void IRAM_ATTR m1_isr_b() { m1_isr(); }
    void IRAM_ATTR m2_isr_a() { m2_isr(); }
    void IRAM_ATTR m2_isr_b() { m2_isr(); }

    // ---- 속도→PWM 선형 환산(floor 없음) ----
    inline int velToPwm(float v) {
        if (fabsf(v) < 0.005f) return 0;
        int pwm = (int)(fabsf(v) / MAX_WHEEL_VEL * 255.0f);
        return (v > 0.0f) ? pwm : -pwm;
    }

    // ---- affine 데드밴드: 0이 아니면 floor에서 시작해 255까지 선형 ----
    inline int applyDeadband(int u, int floor) {
        if (u == 0) return 0;
        int mag = floor + (int)((255 - floor) * (abs(u) / 255.0f));
        mag = constrain(mag, 0, 255);
        return (u > 0) ? mag : -mag;
    }

    // ---- 부호고정: 명령이 목표속도 부호를 반대로 넘지 않도록 ----
    inline float signLock(float cmd, float tv) {
        if (tv >  0.005f) return (cmd < 1.0f)  ? 1.0f  : cmd;
        if (tv < -0.005f) return (cmd > -1.0f) ? -1.0f : cmd;
        return cmd;
    }
    inline int signf(float x) { return (x > 0.005f) ? 1 : (x < -0.005f ? -1 : 0); }


    // ---- PWM 출력 (부호=방향, 크기 0..255) ----
    inline void setMotor1PWM(int u) {
        u = constrain(u, -255, 255);
        if (u >= 0) { ledcWrite(M1_R_CH, u);     ledcWrite(M1_L_CH, 0); }
        else        { ledcWrite(M1_R_CH, 0);     ledcWrite(M1_L_CH, -u); }
    }
    inline void setMotor2PWM(int u) {
        u = constrain(u, -255, 255);
        if (u >= 0) { ledcWrite(M2_L_CH, u);     ledcWrite(M2_R_CH, 0); }
        else        { ledcWrite(M2_L_CH, 0);     ledcWrite(M2_R_CH, -u); }
    }
}

void MotorControl::begin() {
    pinMode(M1_ENC_A, INPUT_PULLUP); pinMode(M1_ENC_B, INPUT_PULLUP);
    pinMode(M2_ENC_A, INPUT_PULLUP); pinMode(M2_ENC_B, INPUT_PULLUP);

    ledcSetup(M1_R_CH, DC_PWM_FREQ, DC_PWM_RES); ledcAttachPin(M1_RPWM, M1_R_CH);
    ledcSetup(M1_L_CH, DC_PWM_FREQ, DC_PWM_RES); ledcAttachPin(M1_LPWM, M1_L_CH);
    ledcSetup(M2_R_CH, DC_PWM_FREQ, DC_PWM_RES); ledcAttachPin(M2_RPWM, M2_R_CH);
    ledcSetup(M2_L_CH, DC_PWM_FREQ, DC_PWM_RES); ledcAttachPin(M2_LPWM, M2_L_CH);

    pinMode(M1_REN, OUTPUT); pinMode(M1_LEN, OUTPUT);
    pinMode(M2_REN, OUTPUT); pinMode(M2_LEN, OUTPUT);
    digitalWrite(M1_REN, HIGH); digitalWrite(M1_LEN, HIGH);
    digitalWrite(M2_REN, HIGH); digitalWrite(M2_LEN, HIGH);

    m1_prev = (digitalRead(M1_ENC_A) << 1) | digitalRead(M1_ENC_B);
    m2_prev = (digitalRead(M2_ENC_A) << 1) | digitalRead(M2_ENC_B);
    attachInterrupt(digitalPinToInterrupt(M1_ENC_A), m1_isr_a, CHANGE);
    attachInterrupt(digitalPinToInterrupt(M1_ENC_B), m1_isr_b, CHANGE);
    attachInterrupt(digitalPinToInterrupt(M2_ENC_A), m2_isr_a, CHANGE);
    attachInterrupt(digitalPinToInterrupt(M2_ENC_B), m2_isr_b, CHANGE);

    setMotor1PWM(0); setMotor2PWM(0);
    last_cmd_time = millis();
}

void MotorControl::setTargetVelocities(float vl, float vr) {
    float new_v1 = constrain(vl, -MAX_WHEEL_VEL, MAX_WHEEL_VEL);
    float new_v2 = constrain(vr, -MAX_WHEEL_VEL, MAX_WHEEL_VEL);
    if (signf(new_v1) != signf(target_v1)) ipart1 = 0.0f;
    if (signf(new_v2) != signf(target_v2)) ipart2 = 0.0f;
    target_v1 = new_v1;
    target_v2 = new_v2;
}

void MotorControl::notifyCmdReceived() {
    last_cmd_time = millis();
    if (watchdog_tripped) watchdog_tripped = false;
}

void MotorControl::checkWatchdog() {
    if (millis() - last_cmd_time > WATCHDOG_MS) {
        target_v1 = target_v2 = 0.0f;
        target_spd1 = target_spd2 = 0.0f;
        ipart1 = ipart2 = 0.0f;
        cur_spd1 = cur_spd2 = 0;
        setMotor1PWM(0); setMotor2PWM(0);
        watchdog_tripped = true;
    }
}

bool MotorControl::isWatchdogTripped() { return watchdog_tripped; }

void MotorControl::tickAccel() {
    static uint32_t t = 0;
    if (millis() - t < ACCEL_INTERVAL) return;
    t = millis();
    int ts1 = (int)target_spd1, ts2 = (int)target_spd2;
    if (cur_spd1 < ts1) cur_spd1 = min(cur_spd1 + ACCEL_STEP, ts1);
    else if (cur_spd1 > ts1) cur_spd1 = max(cur_spd1 - ACCEL_STEP, ts1);
    if (cur_spd2 < ts2) cur_spd2 = min(cur_spd2 + ACCEL_STEP, ts2);
    else if (cur_spd2 > ts2) cur_spd2 = max(cur_spd2 - ACCEL_STEP, ts2);
}

void MotorControl::tickSyncPID() {
    int32_t snap_m1, snap_m2;
    noInterrupts(); snap_m1 = m1_pos; snap_m2 = m2_pos; interrupts();

    int32_t delta_m1 = snap_m1 - last_m1_pos;
    int32_t delta_m2 = snap_m2 - last_m2_pos;
    last_m1_pos = snap_m1;
    last_m2_pos = snap_m2;

    if (target_v1 != prev_v1 || target_v2 != prev_v2) {
        accum_error = 0; integral = 0.0f; last_error = 0; base_adj = 0;
        prev_v1 = target_v1; prev_v2 = target_v2;
    }

    bool    apply_pid  = false;
    bool    is_straight = false;
    int32_t step_error = 0;
    if (target_v1 != 0.0f && target_v2 != 0.0f) {
        if (fabsf(target_v1 - target_v2) < 0.001f) {
            step_error  = delta_m1 - delta_m2;
            is_straight = true;
            apply_pid   = true;
        } else if (fabsf(target_v1 + target_v2) < 0.001f) {
            step_error  = abs(delta_m1) - abs(delta_m2);
            apply_pid   = true;
        }
    }

    if (apply_pid) {
        accum_error += step_error;
        integral    += (float)accum_error;
        integral     = constrain(integral, -150.0f, 150.0f);
        int32_t deriv = accum_error - last_error;
        float pid_out = (SYNC_KP * accum_error) + (SYNC_KI * integral) + (SYNC_KD * deriv);
        base_adj      = constrain((int)pid_out, -50, 50);
        last_error    = accum_error;
    } else {
        base_adj = 0;
    }

    int s1 = cur_spd1;
    int s2 = cur_spd2;
    if (apply_pid) {
        int half = base_adj / 2;
        if (is_straight) {
            s1 = cur_spd1 - half;
            s2 = cur_spd2 + (base_adj - half);
        } else {
            int adj1 = (target_v1 >= 0.0f) ? -half : +half;
            int adj2 = (target_v2 >= 0.0f) ? +(base_adj - half) : -(base_adj - half);
            s1 = cur_spd1 + adj1;
            s2 = cur_spd2 + adj2;
        }
    }

    s1 = (int)signLock((float)s1, target_v1);
    s2 = (int)signLock((float)s2, target_v2);

    setMotor1PWM(applyDeadband(s1, MIN_PWM));
    setMotor2PWM(applyDeadband(s2, MIN_PWM));
}

static inline void runVelWheel(float tv, float v, float& ipart, float& tspd) {
    if (fabsf(tv) < 0.005f) { tspd = 0.0f; ipart = 0.0f; return; }
    float ff   = (float)velToPwm(tv);
    float err  = tv - v;
    ipart += KI_VEL * err;
    ipart  = constrain(ipart, -VEL_I_MAX, VEL_I_MAX);
    float raw = ff + KP_VEL_P * err + ipart;
    float out = signLock(raw, tv);
    out = constrain(out, -255.0f, 255.0f);
    ipart += (out - raw);
    ipart  = constrain(ipart, -VEL_I_MAX, VEL_I_MAX);
    tspd   = out;
}

void MotorControl::tickVelPID() {
    static int32_t prev_m1 = 0, prev_m2 = 0;
    int32_t snap_m1, snap_m2;
    noInterrupts(); snap_m1 = m1_pos; snap_m2 = m2_pos; interrupts();

    const float DT = (float)FEEDBACK_MS / 1000.0f;
    const float TICK2M = (2.0f * 3.14159265f * WHEEL_RADIUS) / (float)CPR;
    float v1 = (snap_m1 - prev_m1) * TICK2M / DT;
    float v2 = (snap_m2 - prev_m2) * TICK2M / DT;
    prev_m1 = snap_m1; prev_m2 = snap_m2;

    uint32_t now = millis();
    if (fabsf(target_v1) > 0.005f && abs(snap_m1 - stall_last_m1) < 2) {
        if (now - stall_t1 > ENC_STALL_MS) { /* stalled */ }
    } else { stall_last_m1 = snap_m1; stall_t1 = now; }
    if (fabsf(target_v2) > 0.005f && abs(snap_m2 - stall_last_m2) < 2) {
        if (now - stall_t2 > ENC_STALL_MS) { /* stalled */ }
    } else { stall_last_m2 = snap_m2; stall_t2 = now; }

    runVelWheel(target_v1, v1, ipart1, target_spd1);
    runVelWheel(target_v2, v2, ipart2, target_spd2);
}

void MotorControl::snapshotEncoders(int32_t& e1, int32_t& e2) {
    noInterrupts(); e1 = m1_pos; e2 = m2_pos; interrupts();
}

bool MotorControl::isEncoderStalled(int idx) {
    uint32_t now = millis();
    if (idx == 0) return (fabsf(target_v1) > 0.005f) && (now - stall_t1 > ENC_STALL_MS);
    else          return (fabsf(target_v2) > 0.005f) && (now - stall_t2 > ENC_STALL_MS);
}
