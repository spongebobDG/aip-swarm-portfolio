import { PanelExtensionContext } from "@foxglove/extension";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";

type Cmd = 0 | 1 | 2 | 3 | 4;

interface LockMessage {
  operator_id: string;
  vehicle_id: string;
  locked: boolean;
  stamp_ms: number;
}

const VEHICLES = ["aip1", "aip2", "aip3", "peer_1", "peer_2", "peer_3"];
const CMD_CLEAR: Cmd = 0;
const CMD_PAUSE: Cmd = 1;
const CMD_RESUME: Cmd = 2;
const CMD_ESTOP: Cmd = 3;
const CMD_MANUAL: Cmd = 4;
const DRIVE_HZ_MS = 100;
const LOCK_STALE_MS = 3000;

function nowStamp() {
  const now = Date.now();
  return { sec: Math.floor(now / 1000), nanosec: (now % 1000) * 1_000_000 };
}

function zeroTwist() {
  return {
    linear: { x: 0, y: 0, z: 0 },
    angular: { x: 0, y: 0, z: 0 },
  };
}

function twist(linearX: number, angularZ: number) {
  return {
    linear: { x: linearX, y: 0, z: 0 },
    angular: { x: 0, y: 0, z: angularZ },
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function OverridePanel({ context }: { context: PanelExtensionContext }) {
  const operatorId = useMemo(
    () => `op-${Math.random().toString(36).slice(2, 8)}-${Date.now().toString(36)}`,
    [],
  );
  const [vehicle, setVehicle] = useState(VEHICLES[0]!);
  const [linearX, setLinearX] = useState(0);
  const [angularZ, setAngularZ] = useState(0);
  const [lockedBy, setLockedBy] = useState<LockMessage | null>(null);
  const [pressedKeys, setPressedKeys] = useState<Set<string>>(() => new Set());
  const driveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lockTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const latestRef = useRef({ vehicle, linearX, angularZ, locked: false });

  const hasOwnLock = lockedBy?.locked === true && lockedBy.operator_id === operatorId;
  const hasForeignLock =
    lockedBy?.locked === true &&
    lockedBy.operator_id !== operatorId &&
    Date.now() - lockedBy.stamp_ms < LOCK_STALE_MS;
  const viewOnly = hasForeignLock || !hasOwnLock;

  useEffect(() => {
    latestRef.current = { vehicle, linearX, angularZ, locked: hasOwnLock };
  }, [vehicle, linearX, angularZ, hasOwnLock]);

  const publishOverride = useCallback((command: Cmd, manualTwist = zeroTwist()) => {
    context.publish?.("/fleet/override", {
      vehicle_id: latestRef.current.vehicle,
      stamp: nowStamp(),
      command,
      manual_cmd_vel: manualTwist,
    });
  }, [context]);

  const publishTwist = useCallback((manualTwist = zeroTwist()) => {
    const target = latestRef.current.vehicle;
    context.publish?.(`/${target}/override_cmd_vel`, manualTwist);
  }, [context]);

  const publishLock = useCallback((locked: boolean, target?: string) => {
    const vehicleId = target ?? latestRef.current.vehicle;
    const payload: LockMessage = {
      operator_id: operatorId,
      vehicle_id: vehicleId,
      locked,
      stamp_ms: Date.now(),
    };
    context.publish?.("/fleet/control_lock", { data: JSON.stringify(payload) });
    setLockedBy(payload);
  }, [context, operatorId]);

  const failSafeStop = useCallback(() => {
    publishTwist(zeroTwist());
    publishOverride(CMD_PAUSE, zeroTwist());
  }, [publishOverride, publishTwist]);

  useLayoutEffect(() => {
    context.advertise?.("/fleet/override", "aip_fleet_msgs/msg/OverrideCommand");
    context.advertise?.("/fleet/control_lock", "std_msgs/msg/String");
    for (const id of VEHICLES) {
      context.advertise?.(`/${id}/override_cmd_vel`, "geometry_msgs/msg/Twist");
    }
    context.subscribe([{ topic: "/fleet/control_lock" }]);
    context.onRender = (renderState, done) => {
      for (const { topic, message } of renderState.currentFrame ?? []) {
        if (topic !== "/fleet/control_lock") continue;
        try {
          const data = JSON.parse(String((message as Record<string, unknown>)["data"] ?? "{}")) as LockMessage;
          if (!data.vehicle_id || data.vehicle_id === latestRef.current.vehicle || data.vehicle_id === "*") {
            setLockedBy(data);
          }
        } catch {
          // Ignore malformed lock frames from older clients.
        }
      }
      done();
    };
    context.watch("currentFrame");

    return () => {
      failSafeStop();
      publishLock(false, latestRef.current.vehicle);
      for (const id of VEHICLES) {
        context.unadvertise?.(`/${id}/override_cmd_vel`);
      }
      context.unadvertise?.("/fleet/control_lock");
      context.unadvertise?.("/fleet/override");
    };
  }, [context, failSafeStop, publishLock]);

  useEffect(() => {
    if (!hasOwnLock) {
      if (lockTimerRef.current) clearInterval(lockTimerRef.current);
      lockTimerRef.current = null;
      return;
    }
    lockTimerRef.current = setInterval(() => publishLock(true, latestRef.current.vehicle), 1000);
    return () => {
      if (lockTimerRef.current) clearInterval(lockTimerRef.current);
      lockTimerRef.current = null;
    };
  }, [hasOwnLock, publishLock]);

  const stopDriving = useCallback(() => {
    if (driveTimerRef.current) {
      clearInterval(driveTimerRef.current);
      driveTimerRef.current = null;
    }
    failSafeStop();
  }, [failSafeStop]);

  const publishManualFrame = useCallback(() => {
    const frame = twist(latestRef.current.linearX, latestRef.current.angularZ);
    publishTwist(frame);
    publishOverride(CMD_MANUAL, frame);
  }, [publishOverride, publishTwist]);

  const startDriving = useCallback(() => {
    if (viewOnly) return;
    publishManualFrame();
    if (!driveTimerRef.current) {
      driveTimerRef.current = setInterval(publishManualFrame, DRIVE_HZ_MS);
    }
  }, [publishManualFrame, viewOnly]);

  useEffect(() => {
    return () => stopDriving();
  }, [stopDriving]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (viewOnly) return;
      const key = event.key.toLowerCase();
      if (!["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright", " "].includes(key)) {
        return;
      }
      event.preventDefault();
      setPressedKeys((prev) => new Set(prev).add(key));
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      setPressedKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [viewOnly]);

  useEffect(() => {
    if (viewOnly || pressedKeys.size === 0) {
      stopDriving();
      return;
    }
    const forward = pressedKeys.has("w") || pressedKeys.has("arrowup") ? 1 : 0;
    const reverse = pressedKeys.has("s") || pressedKeys.has("arrowdown") ? 1 : 0;
    const left = pressedKeys.has("a") || pressedKeys.has("arrowleft") ? 1 : 0;
    const right = pressedKeys.has("d") || pressedKeys.has("arrowright") ? 1 : 0;
    const eStop = pressedKeys.has(" ");
    if (eStop) {
      publishOverride(CMD_ESTOP, zeroTwist());
      stopDriving();
      return;
    }
    setLinearX(clamp((forward - reverse) * 0.45, -0.5, 0.5));
    setAngularZ(clamp((left - right) * 1.2, -1.5, 1.5));
    startDriving();
  }, [pressedKeys, publishOverride, startDriving, stopDriving, viewOnly]);

  const takeControl = useCallback(() => {
    if (hasForeignLock) {
      const ok = window.confirm("Another operator lock is active. Take over control?");
      if (!ok) return;
    }
    publishLock(true);
    publishOverride(CMD_PAUSE, zeroTwist());
  }, [hasForeignLock, publishLock, publishOverride]);

  const releaseControl = useCallback(() => {
    stopDriving();
    publishLock(false);
    publishOverride(CMD_CLEAR, zeroTwist());
  }, [publishLock, publishOverride, stopDriving]);

  const sendCommand = useCallback((command: Cmd) => {
    if (viewOnly && command !== CMD_ESTOP) return;
    if (command === CMD_ESTOP) {
      const ok = window.confirm(`Emergency stop ${vehicle}?`);
      if (!ok) return;
    }
    publishOverride(command, zeroTwist());
    if (command === CMD_PAUSE || command === CMD_ESTOP) {
      publishTwist(zeroTwist());
    }
  }, [publishOverride, publishTwist, vehicle, viewOnly]);

  const lockText = hasOwnLock
    ? `Locked by this panel (${operatorId})`
    : hasForeignLock
      ? `View-only: ${lockedBy?.operator_id ?? "other operator"}`
      : "No active control lock";

  return (
    <div style={S.root}>
      <header style={S.header}>
        <div>
          <div style={S.title}>AIP Override</div>
          <div style={hasOwnLock ? S.lockOwn : hasForeignLock ? S.lockForeign : S.lockIdle}>{lockText}</div>
        </div>
        <select
          style={S.select}
          value={vehicle}
          onChange={(event) => {
            stopDriving();
            setVehicle(event.target.value);
            if (hasOwnLock) publishLock(true, event.target.value);
          }}
        >
          {VEHICLES.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </header>

      <div style={S.lockButtons}>
        <button style={S.primaryBtn} onClick={takeControl}>Take control</button>
        <button style={S.secondaryBtn} onClick={releaseControl} disabled={!hasOwnLock}>Release</button>
      </div>

      <div style={S.commandGrid}>
        <button style={S.secondaryBtn} disabled={viewOnly} onClick={() => sendCommand(CMD_PAUSE)}>Pause</button>
        <button style={S.secondaryBtn} disabled={viewOnly} onClick={() => sendCommand(CMD_RESUME)}>Resume</button>
        <button style={S.secondaryBtn} disabled={viewOnly} onClick={() => sendCommand(CMD_CLEAR)}>Clear</button>
        <button style={S.dangerBtn} onClick={() => sendCommand(CMD_ESTOP)}>E-Stop</button>
      </div>

      <section style={S.driveBox}>
        <div style={S.panelTitle}>Manual velocity</div>
        <label style={S.sliderRow}>
          <span>linear.x</span>
          <input
            type="range"
            min={-0.5}
            max={0.5}
            step={0.05}
            value={linearX}
            disabled={viewOnly}
            onChange={(event) => setLinearX(parseFloat(event.target.value))}
          />
          <strong>{linearX.toFixed(2)}</strong>
        </label>
        <label style={S.sliderRow}>
          <span>angular.z</span>
          <input
            type="range"
            min={-1.5}
            max={1.5}
            step={0.1}
            value={angularZ}
            disabled={viewOnly}
            onChange={(event) => setAngularZ(parseFloat(event.target.value))}
          />
          <strong>{angularZ.toFixed(2)}</strong>
        </label>
        <button
          style={viewOnly ? S.disabledHoldBtn : S.holdBtn}
          disabled={viewOnly}
          onMouseDown={startDriving}
          onMouseUp={stopDriving}
          onMouseLeave={stopDriving}
          onTouchStart={startDriving}
          onTouchEnd={stopDriving}
        >
          HOLD TO DRIVE
        </button>
      </section>
    </div>
  );
}

const S: Record<string, CSSProperties> = {
  root: {
    padding: 12,
    minHeight: "100%",
    boxSizing: "border-box",
    background: "#0f172a",
    color: "#e5e7eb",
    fontFamily: "Inter, Segoe UI, sans-serif",
    fontSize: 12,
    display: "flex",
    flexDirection: "column",
    gap: 10,
  },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 },
  title: { fontSize: 16, fontWeight: 800 },
  lockOwn: { color: "#86efac", fontSize: 11 },
  lockForeign: { color: "#fbbf24", fontSize: 11 },
  lockIdle: { color: "#94a3b8", fontSize: 11 },
  select: { background: "#111827", color: "#e5e7eb", border: "1px solid #334155", borderRadius: 4, padding: "4px 6px" },
  lockButtons: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 },
  commandGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 },
  primaryBtn: { border: "none", borderRadius: 4, padding: 8, background: "#2563eb", color: "#fff", fontWeight: 800, cursor: "pointer" },
  secondaryBtn: { border: "none", borderRadius: 4, padding: 8, background: "#334155", color: "#e5e7eb", fontWeight: 700, cursor: "pointer" },
  dangerBtn: { border: "none", borderRadius: 4, padding: 8, background: "#991b1b", color: "#fff", fontWeight: 800, cursor: "pointer" },
  driveBox: { border: "1px solid #253044", borderRadius: 6, padding: 10, background: "#111827", display: "flex", flexDirection: "column", gap: 8 },
  panelTitle: { fontWeight: 800, color: "#cbd5e1" },
  sliderRow: { display: "grid", gridTemplateColumns: "70px 1fr 46px", gap: 8, alignItems: "center" },
  holdBtn: { border: "none", borderRadius: 4, padding: 10, background: "#16a34a", color: "#fff", fontWeight: 900, cursor: "pointer" },
  disabledHoldBtn: { border: "none", borderRadius: 4, padding: 10, background: "#475569", color: "#94a3b8", fontWeight: 900 },
};

export function initOverridePanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<OverridePanel context={context} />);
  return () => root.unmount();
}
