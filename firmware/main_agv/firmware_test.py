#!/usr/bin/env python3
"""
AGV Firmware Test GUI
ESP32 펀웨어 (DC + Servo + Status) 통합 검증용

주의: 이 펀웨어는 전원(전압) 테레메트리를 보내지 않습니다.
구 전원보드 GUI의 V_batt/V_servo 관련 기능은 제거되었습니다.
"""
import sys, struct, time, csv, math
from collections import deque
from PyQt5 import QtCore, QtWidgets
import pyqtgraph as pg
import serial
import serial.tools.list_ports

# ─────────────────── 기구학 상수 ───────────────────
# 펀웨어 config.h / URDF 와 일치
WHEEL_RADIUS = 0.060
TRACK_WIDTH  = 0.300
CPR          = 2800        # 4× 풀쿼드러처 (PPR 700 × 4)

# ────────────────── 프로토콜 정의 ──────────────────
FEEDBACK_MS  = 50
FEEDBACK_DT  = FEEDBACK_MS / 1000.0
HEAD0, HEAD1 = 0xAA, 0x55
PKT_CMD_VEL  = 0x01
PKT_MOTOR_FB = 0x02
PKT_SERVO    = 0x03
PKT_SERVO_FB = 0x04
PKT_STATUS   = 0x05

# 펀웨어 송신 payload 길이 (체크섬 제외)
#   MOTOR_FB <ll>=8, SERVO_FB 4, STATUS <IHHHH>=12
PAYLOAD_LEN = {
    PKT_MOTOR_FB: 8,
    PKT_SERVO_FB: 4,
    PKT_STATUS:  12,
}

# config.h STATUS flags 비트와 정확히 일치
FLAG_BITS = [
    (1 << 0, "WATCHDOG",      "#e67e22"),
    (1 << 1, "ENC1_STALL",    "#e74c3c"),
    (1 << 2, "ENC2_STALL",    "#e74c3c"),
    (1 << 3, "SERVO_OOR",     "#9b59b6"),
    (1 << 4, "BOOT_BROWNOUT", "#c0392b"),
]

def make_packet(ptype: int, payload: bytes) -> bytes:
    cks = ptype
    for b in payload:
        cks ^= b
    return bytes([HEAD0, HEAD1, ptype]) + payload + bytes([cks & 0xFF])


# ────────────────── 시리얼 스레드 ──────────────────
class SerialWorker(QtCore.QThread):
    motor_fb  = QtCore.pyqtSignal(int, int)
    servo_fb  = QtCore.pyqtSignal(int, int, int, int)
    status    = QtCore.pyqtSignal(int, int, int, int, int)   # uptime, flags, bad, hz, heap
    info      = QtCore.pyqtSignal(bool, str)

    def __init__(self, port: str, baud: int = 115200):
        super().__init__()
        self.port, self.baud = port, baud
        self._stop = False
        self._ser  = None
        self._lock = QtCore.QMutex()

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.02)
            try:
                self._ser.set_buffer_size(rx_size=65536, tx_size=8192)
            except (AttributeError, OSError):
                pass
            time.sleep(0.4)
            self._ser.reset_input_buffer()
            self.info.emit(True, f"opened {self.port}")
        except Exception as e:
            self.info.emit(False, str(e))
            return

        st, ptype, plen, buf = 0, 0, 0, bytearray()
        while not self._stop:
            try:
                n = self._ser.in_waiting
                if n:
                    data = self._ser.read(min(n, 4096))
                else:
                    data = self._ser.read(1)
            except Exception:
                break
            for b in data:
                if st == 0:
                    if b == HEAD0: st = 1
                elif st == 1:
                    st = 2 if b == HEAD1 else (1 if b == HEAD0 else 0)
                elif st == 2:
                    ptype = b
                    plen  = PAYLOAD_LEN.get(ptype, 0)
                    if plen == 0:
                        st = 0
                    else:
                        buf = bytearray()
                        st = 3
                elif st == 3:
                    buf.append(b)
                    if len(buf) >= plen: st = 4
                elif st == 4:
                    cks = ptype
                    for x in buf: cks ^= x
                    if (cks & 0xFF) == b:
                        self._dispatch(ptype, bytes(buf))
                    st = 0

        if self._ser: self._ser.close()
        self.info.emit(False, "closed")

    def _dispatch(self, ptype, payload):
        if ptype == PKT_MOTOR_FB:
            e1, e2 = struct.unpack('<ll', payload)
            self.motor_fb.emit(e1, e2)
        elif ptype == PKT_SERVO_FB:
            s1, s2, s3, s4 = struct.unpack('<BBBB', payload)
            self.servo_fb.emit(s1, s2, s3, s4)
        elif ptype == PKT_STATUS:
            up, fl, bad, hz, heap = struct.unpack('<IHHHH', payload)
            self.status.emit(up, fl, bad, hz, heap)

    def send(self, ptype, payload):
        if not self._ser or not self._ser.is_open: return
        self._lock.lock()
        try:
            self._ser.write(make_packet(ptype, payload))
        finally:
            self._lock.unlock()

    def stop(self):
        self._stop = True
        self.wait(1500)


# ────────────────── 자동 시나리오 ──────────────────
class Scenario:
    def __init__(self, name, duration, fn):
        self.name, self.duration, self.fn = name, duration, fn
    def at(self, t):
        return None if t > self.duration else self.fn(t)

def s_idle(t):     return (0.0, 0.0, [90,90,90,90])
def s_dc(t):       return (0.5, 0.0, [90,90,90,90])
def s_servo(t):
    a = 90 + 30 * math.sin(2*math.pi*0.5*t)
    return (0.0, 0.0, [int(a), int(180-a), int(a), int(180-a)])
def s_combined(t):
    a = 90 + 30 * math.sin(2*math.pi*0.5*t)
    return (0.5, 0.0, [int(a), int(180-a), int(a), int(180-a)])
def s_step(t):
    v = 0.0 if (int(t) % 2 == 0) else 0.7
    a = 60 if (int(t*2) % 2 == 0) else 120
    return (v, 0.0, [a, a, a, a])
def s_spin(t):
    return (0.0, 0.6, [90,90,90,90])

SCENARIOS = [
    Scenario("Idle baseline",            5, s_idle),
    Scenario("DC only",                 10, s_dc),
    Scenario("Servo only (sine)",       10, s_servo),
    Scenario("DC + Servo combined",     20, s_combined),
    Scenario("Step load",               15, s_step),
    Scenario("Spin in place",           10, s_spin),
    Scenario("Long duration combined", 300, s_combined),
]


# ────────────────── 메인 윈도우 ──────────────────
class MainWindow(QtWidgets.QMainWindow):
    BUF = 1200
    PLOT_REFRESH_MS = 250

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AGV Firmware Test")
        self.resize(1280, 800)

        self.worker = None
        self.servo  = [90]*4
        self.v, self.w = 0.0, 0.0
        self.t_start = time.time()
        self.t0_test = None
        self.scenario = None
        self.csv_file = None
        self.csv_writer = None
        self.last_uptime = 0
        self.reboot_count = 0
        self.last_status = (0, 0, 0, 0, 0)

        self.e1_buf = deque(maxlen=self.BUF)
        self.e2_buf = deque(maxlen=self.BUF)
        self.cr1_buf = deque(maxlen=self.BUF)
        self.cr2_buf = deque(maxlen=self.BUF)
        self.t_enc  = deque(maxlen=self.BUF)
        self.j_act_buf = [deque(maxlen=self.BUF) for _ in range(4)]
        self.j_cmd_buf = [deque(maxlen=self.BUF) for _ in range(4)]
        self.t_srv  = deque(maxlen=self.BUF)
        self.prev_e1 = self.prev_e2 = None
        self.enc1_cum = self.enc2_cum = 0
        self.enc1_rate = self.enc2_rate = 0.0
        self.actual_servo = [90]*4

        self._build_ui()

        self.tx_timer = QtCore.QTimer(self)
        self.tx_timer.setInterval(50)
        self.tx_timer.timeout.connect(self._tx_step)
        self.tx_timer.start()

        self.plot_dirty = False
        self.plot_timer = QtCore.QTimer(self)
        self.plot_timer.setInterval(self.PLOT_REFRESH_MS)
        self.plot_timer.timeout.connect(self._refresh_plots)
        self.plot_timer.start()

    def _build_ui(self):
        self.tabs = QtWidgets.QTabWidget(); self.setCentralWidget(self.tabs)
        self.tabs.addTab(self._tab_connect(), "1. Connect")
        self.tabs.addTab(self._tab_manual(),  "2. Manual")
        self.tabs.addTab(self._tab_auto(),    "3. Auto Test")
        self.telemetry_tab = self._tab_plot()
        self.tabs.addTab(self.telemetry_tab, "4. Telemetry")
        self.lbl_bar = QtWidgets.QLabel("disconnected")
        self.statusBar().addPermanentWidget(self.lbl_bar)

    def _tab_connect(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QFormLayout(w)
        self.cb_port = QtWidgets.QComboBox()
        for p in serial.tools.list_ports.comports():
            self.cb_port.addItem(p.device)
        btn_refresh = QtWidgets.QPushButton("Refresh ports")
        btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_open = QtWidgets.QPushButton("Open / Close")
        self.btn_open.clicked.connect(self._toggle_open)
        self.lbl_status = QtWidgets.QLabel("idle")
        lay.addRow("Port",   self.cb_port)
        lay.addRow("",       btn_refresh)
        lay.addRow("",       self.btn_open)
        lay.addRow("Status", self.lbl_status)
        return w

    def _refresh_ports(self):
        self.cb_port.clear()
        for p in serial.tools.list_ports.comports():
            self.cb_port.addItem(p.device)

    def _tab_manual(self):
        w = QtWidgets.QWidget(); g = QtWidgets.QGridLayout(w)
        g.addWidget(QtWidgets.QLabel("<b>DC motor (cmd_vel)</b>"), 0, 0, 1, 3)
        self.sld_v = self._slider(-100, 100, 0)
        self.sld_w = self._slider(-100, 100, 0)
        self.lbl_v = QtWidgets.QLabel("0.00 m/s")
        self.lbl_w = QtWidgets.QLabel("0.00 rad/s")
        self.sld_v.valueChanged.connect(self._on_sld_v)
        self.sld_w.valueChanged.connect(self._on_sld_w)
        g.addWidget(QtWidgets.QLabel("v (linear)"), 1, 0); g.addWidget(self.sld_v, 1, 1); g.addWidget(self.lbl_v, 1, 2)
        g.addWidget(QtWidgets.QLabel("\u03c9 (angular)"),2, 0); g.addWidget(self.sld_w, 2, 1); g.addWidget(self.lbl_w, 2, 2)

        g.addWidget(QtWidgets.QLabel("<b>Servos (deg)</b>"), 3, 0, 1, 3)
        self.sld_s, self.lbl_s = [], []
        for i in range(4):
            s = self._slider(0, 180, 90)
            l = QtWidgets.QLabel("90\u00b0")
            s.valueChanged.connect(lambda x, i=i, l=l: self._on_sld_servo(i, x, l))
            g.addWidget(QtWidgets.QLabel(f"J{i+1}"), 4+i, 0)
            g.addWidget(s, 4+i, 1)
            g.addWidget(l, 4+i, 2)
            self.sld_s.append(s); self.lbl_s.append(l)

        btn_home = QtWidgets.QPushButton("Home pose (90\u00b0\u00d74)")
        btn_home.clicked.connect(self._home_servos)
        btn_stop = QtWidgets.QPushButton("E-STOP")
        btn_stop.setStyleSheet("background:#d9534f;color:white;font-weight:bold;font-size:16px;padding:8px;")
        btn_stop.clicked.connect(self._estop)
        g.addWidget(btn_home, 8, 0, 1, 3)
        g.addWidget(btn_stop, 9, 0, 1, 3)
        return w

    def _on_sld_v(self, x):
        self.v = x / 100.0
        self.lbl_v.setText(f"{self.v:+.2f} m/s")

    def _on_sld_w(self, x):
        self.w = x / 100.0 * 2.0
        self.lbl_w.setText(f"{self.w:+.2f} rad/s")

    def _on_sld_servo(self, i, x, lbl):
        self.servo[i] = x
        lbl.setText(f"{x}\u00b0")

    def _home_servos(self):
        for s in self.sld_s: s.setValue(90)

    def _estop(self):
        self.v = self.w = 0.0
        self.sld_v.setValue(0); self.sld_w.setValue(0)

    def _tab_auto(self):
        w = QtWidgets.QWidget(); lay = QtWidgets.QVBoxLayout(w)
        self.cb_scn = QtWidgets.QComboBox()
        for s in SCENARIOS:
            self.cb_scn.addItem(f"{s.name} ({s.duration}s)")
        btn_run  = QtWidgets.QPushButton("\u25b6 Run scenario")
        btn_stop = QtWidgets.QPushButton("\u25a0 Stop")
        self.chk_log = QtWidgets.QCheckBox("Log telemetry to CSV during test")
        self.lbl_run = QtWidgets.QLabel("idle")
        btn_run.clicked.connect(self._scn_start)
        btn_stop.clicked.connect(self._scn_stop)
        for x in (self.cb_scn, btn_run, btn_stop, self.chk_log, self.lbl_run):
            lay.addWidget(x)
        lay.addStretch()
        return w

    def _tab_plot(self):
        w = QtWidgets.QWidget(); h = QtWidgets.QHBoxLayout(w)

        left = QtWidgets.QWidget(); vl = QtWidgets.QVBoxLayout(left)
        pg.setConfigOptions(antialias=True)
        self.p2 = pg.PlotWidget(title="Encoder rate (ticks/s) \u2014 solid=actual, dashed=cmd")
        self.p2.addLegend()
        self.cv_e1  = self.p2.plot(pen=pg.mkPen('g', width=2),                              name='ENC1 act')
        self.cv_e2  = self.p2.plot(pen=pg.mkPen('r', width=2),                              name='ENC2 act')
        self.cv_cr1 = self.p2.plot(pen=pg.mkPen('g', width=1, style=QtCore.Qt.DashLine),    name='ENC1 cmd')
        self.cv_cr2 = self.p2.plot(pen=pg.mkPen('r', width=1, style=QtCore.Qt.DashLine),    name='ENC2 cmd')
        self.p3 = pg.PlotWidget(title="Servo angle (deg) \u2014 solid=actual, dashed=cmd")
        self.p3.addLegend()
        self.p3.setYRange(0, 180)
        servo_colors = ['#3498db', '#2ecc71', '#e67e22', '#9b59b6']
        self.cv_js_act, self.cv_js_cmd = [], []
        for i, c in enumerate(servo_colors):
            self.cv_js_act.append(self.p3.plot(pen=pg.mkPen(c, width=2),                            name=f'J{i+1} act'))
            self.cv_js_cmd.append(self.p3.plot(pen=pg.mkPen(c, width=1, style=QtCore.Qt.DashLine), name=f'J{i+1} cmd'))
        for p in (self.p2, self.p3):
            p.showGrid(x=True, y=True)
            vl.addWidget(p)
        h.addWidget(left, 3)

        right = QtWidgets.QWidget(); vr = QtWidgets.QVBoxLayout(right)
        vr.addWidget(QtWidgets.QLabel("<b>Board STATUS</b>"))
        info = QtWidgets.QFormLayout()
        self.lbl_uptime  = QtWidgets.QLabel("\u2014")
        self.lbl_hz      = QtWidgets.QLabel("\u2014")
        self.lbl_heap    = QtWidgets.QLabel("\u2014")
        self.lbl_bad     = QtWidgets.QLabel("\u2014")
        self.lbl_reboots = QtWidgets.QLabel("0")
        info.addRow("Uptime (s)",      self.lbl_uptime)
        info.addRow("Loop Hz",         self.lbl_hz)
        info.addRow("Free heap (KB)",  self.lbl_heap)
        info.addRow("Bad pkts / win",  self.lbl_bad)
        info.addRow("Reboots",         self.lbl_reboots)
        vr.addLayout(info)

        vr.addWidget(QtWidgets.QLabel("<b>Flags</b>"))
        self.flag_labels = {}
        for bit, name, color in FLAG_BITS:
            l = QtWidgets.QLabel(name)
            l.setStyleSheet("padding:4px 8px;border-radius:4px;background:#bdc3c7;color:#7f8c8d;")
            self.flag_labels[bit] = (l, color)
            vr.addWidget(l)
        vr.addStretch()
        h.addWidget(right, 1)
        return w

    def _slider(self, lo, hi, v):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setRange(lo, hi); s.setValue(v)
        s.setTickInterval(max(1, (hi-lo)//10))
        s.setTickPosition(QtWidgets.QSlider.TicksBelow)
        return s

    def _toggle_open(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker = None
            self.lbl_status.setText("closed")
            self.lbl_bar.setText("disconnected")
            return
        port = self.cb_port.currentText()
        if not port:
            self.lbl_status.setText("no port selected"); return
        self.worker = SerialWorker(port)
        self.worker.info.connect(lambda ok, msg: self.lbl_status.setText(msg), QtCore.Qt.QueuedConnection)
        self.worker.motor_fb.connect(self._on_fb, QtCore.Qt.QueuedConnection)
        self.worker.servo_fb.connect(self._on_servo_fb, QtCore.Qt.QueuedConnection)
        self.worker.status.connect(self._on_st, QtCore.Qt.QueuedConnection)
        self.worker.start()

    def _on_fb(self, e1, e2):
        t = time.time() - self.t_start
        self.enc1_cum, self.enc2_cum = e1, e2
        if self.prev_e1 is not None:
            self.enc1_rate = (e1 - self.prev_e1) / FEEDBACK_DT
            self.enc2_rate = (e2 - self.prev_e2) / FEEDBACK_DT
            cr1, cr2 = self._cmd_wheel_rates()
            self.e1_buf.append(self.enc1_rate)
            self.e2_buf.append(self.enc2_rate)
            self.cr1_buf.append(cr1)
            self.cr2_buf.append(cr2)
            self.t_enc.append(t)
            self.plot_dirty = True
            if self.csv_writer:
                self._log_row(t, cr1, cr2)
        self.prev_e1, self.prev_e2 = e1, e2

    def _on_servo_fb(self, s1, s2, s3, s4):
        t = time.time() - self.t_start
        self.actual_servo = [s1, s2, s3, s4]
        for i, v in enumerate(self.actual_servo):
            self.j_act_buf[i].append(v)
            self.j_cmd_buf[i].append(self.servo[i])
        self.t_srv.append(t)
        self.plot_dirty = True

    def _cmd_wheel_rates(self):
        vL = self.v - self.w * TRACK_WIDTH / 2.0
        vR = self.v + self.w * TRACK_WIDTH / 2.0
        k  = CPR / (2.0 * math.pi * WHEEL_RADIUS)
        return vL * k, vR * k

    def _log_row(self, t, cr1, cr2):
        self.csv_writer.writerow([
            f"{t:.3f}",
            f"{self.v:.3f}", f"{self.w:.3f}",
            self.enc1_cum, self.enc2_cum,
            f"{self.enc1_rate:.1f}", f"{self.enc2_rate:.1f}",
            f"{cr1:.1f}", f"{cr2:.1f}",
            *self.servo, *self.actual_servo,
            *self.last_status,
        ])

    def _refresh_plots(self):
        if not self.plot_dirty:
            return
        if self.tabs.currentWidget() is not self.telemetry_tab:
            return
        te = list(self.t_enc)
        self.cv_e1.setData(te, list(self.e1_buf))
        self.cv_e2.setData(te, list(self.e2_buf))
        self.cv_cr1.setData(te, list(self.cr1_buf))
        self.cv_cr2.setData(te, list(self.cr2_buf))
        ts = list(self.t_srv)
        for i in range(4):
            self.cv_js_act[i].setData(ts, list(self.j_act_buf[i]))
            self.cv_js_cmd[i].setData(ts, list(self.j_cmd_buf[i]))
        self.plot_dirty = False

    def _on_st(self, uptime, flags, bad, hz, heap):
        if uptime < self.last_uptime:
            self.reboot_count += 1
            self.lbl_reboots.setText(str(self.reboot_count))
        self.last_uptime = uptime
        self.last_status = (uptime, flags, bad, hz, heap)

        self.lbl_uptime.setText(f"{uptime/1000:.1f}")
        self.lbl_hz.setText(str(hz))
        self.lbl_heap.setText(str(heap))
        self.lbl_bad.setText(str(bad))
        self.lbl_bar.setText(f"up {uptime/1000:.0f}s | {hz} Hz | heap {heap} KB | bad {bad}")

        for bit, name, color in FLAG_BITS:
            lbl, c = self.flag_labels[bit]
            if flags & bit:
                lbl.setStyleSheet(f"padding:4px 8px;border-radius:4px;background:{c};color:white;font-weight:bold;")
            else:
                lbl.setStyleSheet("padding:4px 8px;border-radius:4px;background:#bdc3c7;color:#7f8c8d;")

    def _tx_step(self):
        if self.scenario:
            t = time.time() - self.t0_test
            r = self.scenario.at(t)
            if r is None:
                self._scn_stop(); return
            self.v, self.w = r[0], r[1]
            for i in range(4):
                self.servo[i] = int(max(0, min(180, r[2][i])))
            self.lbl_run.setText(f"{self.scenario.name}: {t:5.1f}/{self.scenario.duration}s")

        if self.worker and self.worker.isRunning():
            self.worker.send(PKT_CMD_VEL, struct.pack('<ff', float(self.v), float(self.w)))
            self.worker.send(PKT_SERVO,   bytes([int(x) & 0xFF for x in self.servo]))

    def _scn_start(self):
        self.scenario = SCENARIOS[self.cb_scn.currentIndex()]
        self.t0_test  = time.time()
        if self.chk_log.isChecked():
            fn = f"fw_test_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            self.csv_file   = open(fn, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow([
                "t_sec",
                "v_cmd", "w_cmd",
                "enc1_cum", "enc2_cum",
                "enc1_rate", "enc2_rate",
                "cmd1_rate", "cmd2_rate",
                "j1_cmd", "j2_cmd", "j3_cmd", "j4_cmd",
                "j1_act", "j2_act", "j3_act", "j4_act",
                "uptime_ms", "flags", "bad", "loop_hz", "heap_kb",
            ])

    def _scn_stop(self):
        self.scenario = None
        self.v = self.w = 0.0
        self.servo = [90]*4
        for s in self.sld_s: s.setValue(90)
        self.sld_v.setValue(0); self.sld_w.setValue(0)
        self.lbl_run.setText("idle")
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = self.csv_writer = None

    def closeEvent(self, e):
        self._estop()
        if self.worker: self.worker.stop()
        if self.csv_file: self.csv_file.close()
        super().closeEvent(e)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
