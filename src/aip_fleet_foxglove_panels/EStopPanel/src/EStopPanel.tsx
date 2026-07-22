import { PanelExtensionContext } from "@foxglove/extension";
import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";

const VEHICLES = ["aip1", "aip2", "aip3", "peer_1", "peer_2", "peer_3"];
const DEBOUNCE_MS = 200;

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

function EStopPanel({ context }: { context: PanelExtensionContext }) {
  const [armed, setArmed] = useState(false);
  const [lastAction, setLastAction] = useState("Ready");
  const lastFireRef = useRef(0);
  const lastClearRef = useRef(0);

  useLayoutEffect(() => {
    context.advertise?.("/fleet/override", "aip_fleet_msgs/msg/OverrideCommand");
    for (const id of VEHICLES) {
      context.advertise?.(`/${id}/estop`, "std_msgs/msg/Bool");
      context.advertise?.(`/${id}/override_cmd_vel`, "geometry_msgs/msg/Twist");
    }
    return () => {
      for (const id of VEHICLES) {
        context.publish?.(`/${id}/override_cmd_vel`, zeroTwist());
        context.unadvertise?.(`/${id}/override_cmd_vel`);
        context.unadvertise?.(`/${id}/estop`);
      }
      context.unadvertise?.("/fleet/override");
    };
  }, [context]);

  const publishFleetOverride = useCallback((vehicleId: string, command: number) => {
    context.publish?.("/fleet/override", {
      vehicle_id: vehicleId,
      stamp: nowStamp(),
      command,
      manual_cmd_vel: zeroTwist(),
    });
  }, [context]);

  const publishVehicleEStop = useCallback((vehicleId: string, active: boolean) => {
    context.publish?.(`/${vehicleId}/estop`, { data: active });
    context.publish?.(`/${vehicleId}/override_cmd_vel`, zeroTwist());
  }, [context]);

  const fireAll = useCallback(() => {
    const now = Date.now();
    if (now - lastFireRef.current < DEBOUNCE_MS) return;
    lastFireRef.current = now;
    publishFleetOverride("*", 3);
    for (const id of VEHICLES) {
      publishVehicleEStop(id, true);
    }
    setLastAction(`Fleet E-Stop fired at ${new Date(now).toLocaleTimeString()}`);
  }, [publishFleetOverride, publishVehicleEStop]);

  const fireOne = useCallback((vehicleId: string) => {
    const now = Date.now();
    if (now - lastFireRef.current < DEBOUNCE_MS) return;
    lastFireRef.current = now;
    publishFleetOverride(vehicleId, 3);
    publishVehicleEStop(vehicleId, true);
    setLastAction(`${vehicleId} E-Stop fired at ${new Date(now).toLocaleTimeString()}`);
  }, [publishFleetOverride, publishVehicleEStop]);

  const clearAll = useCallback(() => {
    const now = Date.now();
    if (now - lastClearRef.current < DEBOUNCE_MS) return;
    const ok = window.confirm("Clear E-Stop on all vehicles? Motion may resume if autonomy is active.");
    if (!ok) return;
    lastClearRef.current = now;
    publishFleetOverride("*", 0);
    for (const id of VEHICLES) {
      publishVehicleEStop(id, false);
    }
    setLastAction(`Fleet E-Stop cleared at ${new Date(now).toLocaleTimeString()}`);
  }, [publishFleetOverride, publishVehicleEStop]);

  return (
    <div style={S.root}>
      <button
        style={armed ? S.estopArmed : S.estop}
        onMouseDown={() => setArmed(true)}
        onMouseUp={() => setArmed(false)}
        onMouseLeave={() => setArmed(false)}
        onTouchStart={() => setArmed(true)}
        onTouchEnd={() => setArmed(false)}
        onClick={fireAll}
      >
        EMERGENCY STOP
      </button>

      <div style={S.status}>{lastAction}</div>

      <div style={S.vehicleGrid}>
        {VEHICLES.map((id) => (
          <button key={id} style={S.vehicleBtn} onClick={() => fireOne(id)}>
            {id}
          </button>
        ))}
      </div>

      <button style={S.clearBtn} onClick={clearAll}>
        Clear E-Stop All
      </button>
    </div>
  );
}

const S: Record<string, CSSProperties> = {
  root: {
    minHeight: "100%",
    padding: 12,
    boxSizing: "border-box",
    background: "#0f172a",
    color: "#e5e7eb",
    fontFamily: "Inter, Segoe UI, sans-serif",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    textAlign: "center",
  },
  estop: {
    width: "100%",
    height: 130,
    border: "none",
    borderRadius: 8,
    background: "#991b1b",
    color: "#fff",
    fontSize: 28,
    fontWeight: 900,
    cursor: "pointer",
    letterSpacing: 0,
  },
  estopArmed: {
    width: "100%",
    height: 130,
    border: "3px solid #fecaca",
    borderRadius: 8,
    background: "#dc2626",
    color: "#fff",
    fontSize: 28,
    fontWeight: 900,
    cursor: "pointer",
    letterSpacing: 0,
  },
  status: { color: "#cbd5e1", fontSize: 12 },
  vehicleGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 },
  vehicleBtn: {
    border: "1px solid #7f1d1d",
    borderRadius: 4,
    padding: "7px 4px",
    background: "#1f2937",
    color: "#fecaca",
    fontWeight: 800,
    cursor: "pointer",
  },
  clearBtn: {
    border: "none",
    borderRadius: 4,
    padding: 9,
    background: "#334155",
    color: "#e5e7eb",
    fontWeight: 800,
    cursor: "pointer",
  },
};

export function initEStopPanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<EStopPanel context={context} />);
  return () => root.unmount();
}
