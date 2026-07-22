import { PanelExtensionContext } from "@foxglove/extension";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";

type VehicleState = 0 | 1 | 2 | 3 | 4;

interface TimeMsg {
  sec?: number;
  nanosec?: number;
}

interface Heartbeat {
  vehicle_id: string;
  stamp?: TimeMsg;
  state: VehicleState;
  battery_pct: number;
  cpu_load: number;
  active_behaviors?: string[];
}

interface FleetStatus {
  stamp?: TimeMsg;
  vehicles: Heartbeat[];
  offline_vehicle_ids: string[];
}

interface PerceptionAlert {
  vehicle_id: string;
  alert_level: number;
  max_temp_c: number;
  thermal_zone?: number;
  rgb_bbox_x?: number;
  rgb_bbox_y?: number;
  rgb_bbox_w?: number;
  rgb_bbox_h?: number;
  confidence?: number;
  map_position?: { x: number; y: number; z?: number };
}

interface OccupancyGrid {
  info: {
    width: number;
    height: number;
    resolution: number;
    origin: { position: { x: number; y: number } };
  };
  data: number[];
}

interface DetectionBox {
  id: string;
  label: string;
  score: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface VehicleView {
  id: string;
  heartbeat?: Heartbeat;
  offline: boolean;
  lastSeenMs?: number;
}

const DEFAULT_VEHICLES = ["aip1", "aip2", "aip3", "peer_1", "peer_2", "peer_3"];
const THROTTLE_MS = 125;

const STATE_LABEL: Record<VehicleState, string> = {
  0: "IDLE",
  1: "AUTO",
  2: "MANUAL",
  3: "ESTOP",
  4: "FAULT",
};

const STATE_COLOR: Record<VehicleState, string> = {
  0: "#7a8496",
  1: "#26a269",
  2: "#3b82f6",
  3: "#dc2626",
  4: "#f97316",
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function numberFrom(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function messageBytesToDataUrl(message: Record<string, unknown>): string | undefined {
  const data = message["data"];
  const format = String(message["format"] ?? "jpeg").toLowerCase();
  const mime = format.includes("png") ? "image/png" : "image/jpeg";
  let bytes: number[] | undefined;

  if (data instanceof Uint8Array) {
    bytes = Array.from(data);
  } else if (Array.isArray(data)) {
    bytes = data.map((v) => Number(v) & 0xff);
  }
  if (!bytes || bytes.length === 0) {
    return undefined;
  }

  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return `data:${mime};base64,${btoa(binary)}`;
}

function normalizeDetection(message: Record<string, unknown>, fallbackId: string): DetectionBox[] {
  const source = Array.isArray(message["detections"])
    ? (message["detections"] as unknown[])
    : Array.isArray(message["boxes"])
      ? (message["boxes"] as unknown[])
      : Array.isArray(message["objects"])
        ? (message["objects"] as unknown[])
        : [];

  return source.flatMap((raw, index) => {
    const item = raw as Record<string, unknown>;
    const bbox = (item["bbox"] ?? item["bounding_box"] ?? item) as Record<string, unknown>;
    const x = numberFrom(bbox["x"] ?? bbox["center_x"] ?? bbox["xmin"] ?? bbox["left"], NaN);
    const y = numberFrom(bbox["y"] ?? bbox["center_y"] ?? bbox["ymin"] ?? bbox["top"], NaN);
    const w = numberFrom(bbox["w"] ?? bbox["width"] ?? (numberFrom(bbox["xmax"], NaN) - x), NaN);
    const h = numberFrom(bbox["h"] ?? bbox["height"] ?? (numberFrom(bbox["ymax"], NaN) - y), NaN);
    if (![x, y, w, h].every(Number.isFinite) || w <= 0 || h <= 0) {
      return [];
    }
    return [{
      id: `${fallbackId}-${index}`,
      label: String(item["label"] ?? item["class_name"] ?? item["class"] ?? "object"),
      score: numberFrom(item["score"] ?? item["confidence"], 0),
      x,
      y,
      w,
      h,
    }];
  });
}

function alertToDetection(alert: PerceptionAlert): DetectionBox | undefined {
  const x = alert.rgb_bbox_x ?? -1;
  const y = alert.rgb_bbox_y ?? -1;
  const w = alert.rgb_bbox_w ?? -1;
  const h = alert.rgb_bbox_h ?? -1;
  if (x < 0 || y < 0 || w <= 0 || h <= 0) {
    return undefined;
  }
  return {
    id: `alert-${alert.vehicle_id}`,
    label: alert.alert_level >= 2 ? "fire/high-temp" : "hotspot",
    score: alert.confidence ?? 0,
    x,
    y,
    w,
    h,
  };
}

function drawOccupancyGrid(ctx: CanvasRenderingContext2D, grid: OccupancyGrid, width: number, height: number) {
  const offscreen = document.createElement("canvas");
  offscreen.width = grid.info.width;
  offscreen.height = grid.info.height;
  const octx = offscreen.getContext("2d");
  if (!octx) {
    return;
  }

  const image = octx.createImageData(grid.info.width, grid.info.height);
  for (let i = 0; i < grid.data.length; i += 1) {
    const value = grid.data[i] ?? -1;
    const p = i * 4;
    if (value < 0) {
      image.data[p] = 45;
      image.data[p + 1] = 50;
      image.data[p + 2] = 58;
      image.data[p + 3] = 210;
    } else if (value === 0) {
      image.data[p] = 224;
      image.data[p + 1] = 231;
      image.data[p + 2] = 239;
      image.data[p + 3] = 255;
    } else {
      const shade = clamp(95 - value, 18, 95);
      image.data[p] = shade;
      image.data[p + 1] = shade;
      image.data[p + 2] = shade;
      image.data[p + 3] = 255;
    }
  }

  octx.putImageData(image, 0, 0);
  ctx.save();
  ctx.translate(0, height);
  ctx.scale(width / grid.info.width, -height / grid.info.height);
  ctx.drawImage(offscreen, 0, 0);
  ctx.restore();
}

function worldToCanvas(x: number, y: number, grid: OccupancyGrid, width: number, height: number) {
  const px = (x - grid.info.origin.position.x) / grid.info.resolution;
  const py = (y - grid.info.origin.position.y) / grid.info.resolution;
  return {
    x: (px / grid.info.width) * width,
    y: height - (py / grid.info.height) * height,
  };
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = clamp((value / max) * 100, 0, 100);
  return (
    <div style={S.barShell}>
      <div style={{ ...S.barFill, width: `${pct}%`, background: color }} />
    </div>
  );
}

function VehicleCard({ vehicle }: { vehicle: VehicleView }) {
  const state: VehicleState = vehicle.offline ? 4 : (vehicle.heartbeat?.state ?? 0);
  const stateColor = vehicle.offline ? "#6b7280" : STATE_COLOR[state];
  const battery = clamp(vehicle.heartbeat?.battery_pct ?? 0, 0, 100);
  const cpuPct = clamp((vehicle.heartbeat?.cpu_load ?? 0) * 100, 0, 100);
  const batteryColor = battery > 50 ? "#26a269" : battery > 20 ? "#f59e0b" : "#dc2626";
  const cpuColor = cpuPct < 65 ? "#3b82f6" : cpuPct < 85 ? "#f59e0b" : "#dc2626";

  return (
    <div style={{ ...S.vehicleCard, borderColor: stateColor }}>
      <div style={S.vehicleHead}>
        <strong>{vehicle.id}</strong>
        <span style={{ ...S.badge, background: stateColor }}>
          {vehicle.offline ? "OFFLINE" : STATE_LABEL[state]}
        </span>
      </div>
      <div style={S.metricRow}>
        <span>Battery</span>
        <span>{vehicle.heartbeat ? `${battery.toFixed(0)}%` : "--"}</span>
      </div>
      <Bar value={battery} max={100} color={batteryColor} />
      <div style={S.metricRow}>
        <span>CPU</span>
        <span>{vehicle.heartbeat ? `${cpuPct.toFixed(0)}%` : "--"}</span>
      </div>
      <Bar value={cpuPct} max={100} color={cpuColor} />
      <div style={S.tags}>
        {(vehicle.heartbeat?.active_behaviors ?? []).slice(0, 3).map((label) => (
          <span key={label} style={S.tag}>{label}</span>
        ))}
        {vehicle.lastSeenMs != null && (
          <span style={S.muted}>{Math.round(vehicle.lastSeenMs / 1000)}s ago</span>
        )}
      </div>
    </div>
  );
}

function FleetDashboard({ context }: { context: PanelExtensionContext }) {
  const videoCanvasRef = useRef<HTMLCanvasElement>(null);
  const mapCanvasRef = useRef<HTMLCanvasElement>(null);
  const lastFlushRef = useRef(0);
  const heartbeatsRef = useRef<Record<string, Heartbeat>>({});
  const lastSeenRef = useRef<Record<string, number>>({});
  const latestImageRef = useRef<Record<string, string>>({});
  const detectionsRef = useRef<Record<string, DetectionBox[]>>({});
  const alertsRef = useRef<Record<string, PerceptionAlert>>({});
  const gridRef = useRef<OccupancyGrid | null>(null);
  const thermalRef = useRef<Record<string, number>>({});

  const [vehicles, setVehicles] = useState<VehicleView[]>(
    () => DEFAULT_VEHICLES.map((id) => ({ id, offline: true })),
  );
  const [selectedVehicle, setSelectedVehicle] = useState(DEFAULT_VEHICLES[0]!);
  const [alerts, setAlerts] = useState<PerceptionAlert[]>([]);
  const [thermal, setThermal] = useState<Record<string, number>>({});
  const [imageRevision, setImageRevision] = useState(0);
  const [mapRevision, setMapRevision] = useState(0);
  const [showThermalLayer, setShowThermalLayer] = useState(true);

  const flushTelemetry = useCallback(() => {
    const ids = new Set<string>(DEFAULT_VEHICLES);
    for (const id of Object.keys(heartbeatsRef.current)) ids.add(id);
    for (const id of Object.keys(lastSeenRef.current)) ids.add(id);

    const now = Date.now();
    setVehicles(Array.from(ids).sort().map((id) => {
      const heartbeat = heartbeatsRef.current[id];
      const lastSeen = lastSeenRef.current[id];
      const lastSeenMs = lastSeen != null ? now - lastSeen : undefined;
      return {
        id,
        heartbeat,
        offline: heartbeat == null || (lastSeenMs ?? Infinity) > 2500,
        lastSeenMs,
      };
    }));
    setAlerts(Object.values(alertsRef.current).filter((alert) => alert.alert_level > 0));
    setThermal({ ...thermalRef.current });
  }, []);

  useLayoutEffect(() => {
    const topics = [
      { topic: "/fleet/status" },
      { topic: "/fleet/alerts" },
      { topic: "/map_static" },
      { topic: "/peer_1/map_relay" },
      ...DEFAULT_VEHICLES.flatMap((id) => [
        { topic: `/${id}/heartbeat` },
        { topic: `/${id}/thermal_temp` },
        { topic: `/${id}/thermal_viz` },
        { topic: `/${id}/image_raw/compressed` },
        { topic: `/fleet/perception_viz/${id}` },
        { topic: `/${id}/detections` },
      ]),
    ];
    context.subscribe(topics);

    context.onRender = (renderState, done) => {
      for (const { topic, message } of renderState.currentFrame ?? []) {
        const msg = message as Record<string, unknown>;

        if (topic === "/fleet/status") {
          const status = msg as unknown as FleetStatus;
          for (const hb of status.vehicles ?? []) {
            heartbeatsRef.current[hb.vehicle_id] = hb;
            lastSeenRef.current[hb.vehicle_id] = Date.now();
          }
          for (const id of status.offline_vehicle_ids ?? []) {
            lastSeenRef.current[id] = 0;
          }
        } else if (topic.endsWith("/heartbeat")) {
          const heartbeat = msg as unknown as Heartbeat;
          const id = heartbeat.vehicle_id || topic.split("/")[1] || "";
          if (id) {
            heartbeatsRef.current[id] = { ...heartbeat, vehicle_id: id };
            lastSeenRef.current[id] = Date.now();
          }
        } else if (topic === "/fleet/alerts") {
          const alert = msg as unknown as PerceptionAlert;
          if (alert.vehicle_id) {
            alertsRef.current[alert.vehicle_id] = alert;
            const detection = alertToDetection(alert);
            if (detection) {
              detectionsRef.current[alert.vehicle_id] = [detection, ...(detectionsRef.current[alert.vehicle_id] ?? [])].slice(0, 8);
            }
          }
        } else if (topic.endsWith("/thermal_temp")) {
          const id = topic.split("/")[1];
          if (id) {
            thermalRef.current[id] = numberFrom(msg["data"], 0);
          }
        } else if (topic === "/map_static" || topic === "/peer_1/map_relay") {
          gridRef.current = msg as unknown as OccupancyGrid;
          setMapRevision((value) => value + 1);
        } else if (topic.endsWith("/image_raw/compressed") || topic.includes("/fleet/perception_viz/")) {
          const parts = topic.split("/");
          const id = topic.includes("/fleet/perception_viz/")
            ? parts[parts.length - 1]
            : parts[1];
          const url = messageBytesToDataUrl(msg);
          if (id && url) {
            latestImageRef.current[id] = url;
            setSelectedVehicle((prev) => latestImageRef.current[prev] ? prev : id);
            setImageRevision((value) => value + 1);
          }
        } else if (topic.endsWith("/thermal_viz")) {
          const id = topic.split("/")[1];
          const url = messageBytesToDataUrl(msg);
          if (id && url && !latestImageRef.current[id]) {
            latestImageRef.current[id] = url;
            setImageRevision((value) => value + 1);
          }
        } else if (topic.endsWith("/detections")) {
          const id = topic.split("/")[1] ?? selectedVehicle;
          detectionsRef.current[id] = normalizeDetection(msg, id);
        }
      }

      const now = performance.now();
      if (now - lastFlushRef.current >= THROTTLE_MS) {
        lastFlushRef.current = now;
        flushTelemetry();
        setImageRevision((value) => value + 1);
      }
      done();
    };
    context.watch("currentFrame");
  }, [context, flushTelemetry, selectedVehicle]);

  useEffect(() => {
    const canvas = videoCanvasRef.current;
    const src = latestImageRef.current[selectedVehicle];
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.clientWidth || 640;
    const height = canvas.clientHeight || 360;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, width, height);

    if (!src) {
      ctx.fillStyle = "#8b95a7";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Waiting for image stream", width / 2, height / 2);
      return;
    }

    const image = new Image();
    image.onload = () => {
      ctx.clearRect(0, 0, width, height);
      const scale = Math.min(width / image.width, height / image.height);
      const drawW = image.width * scale;
      const drawH = image.height * scale;
      const ox = (width - drawW) / 2;
      const oy = (height - drawH) / 2;
      ctx.drawImage(image, ox, oy, drawW, drawH);

      const boxes = detectionsRef.current[selectedVehicle] ?? [];
      for (const box of boxes) {
        const x = ox + box.x * scale;
        const y = oy + box.y * scale;
        const w = box.w * scale;
        const h = box.h * scale;
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.fillStyle = "rgba(250, 204, 21, 0.92)";
        const label = `${box.label}${box.score > 0 ? ` ${(box.score * 100).toFixed(0)}%` : ""}`;
        const textWidth = ctx.measureText(label).width + 10;
        ctx.fillRect(x, Math.max(0, y - 20), textWidth, 18);
        ctx.fillStyle = "#111827";
        ctx.font = "bold 11px sans-serif";
        ctx.textAlign = "left";
        ctx.fillText(label, x + 5, Math.max(12, y - 7));
      }
    };
    image.src = src;
  }, [selectedVehicle, imageRevision]);

  useEffect(() => {
    const canvas = mapCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const width = canvas.clientWidth || 500;
    const height = canvas.clientHeight || 280;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#101827";
    ctx.fillRect(0, 0, width, height);
    const grid = gridRef.current;
    if (!grid) {
      ctx.fillStyle = "#8b95a7";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Waiting for /map_static or /peer_1/map_relay", width / 2, height / 2);
      return;
    }

    drawOccupancyGrid(ctx, grid, width, height);
    if (showThermalLayer) {
      for (const alert of Object.values(alertsRef.current)) {
        const pos = alert.map_position;
        if (!pos || alert.alert_level <= 0) continue;
        const c = worldToCanvas(pos.x, pos.y, grid, width, height);
        const radius = clamp((alert.max_temp_c - 20) * 0.9, 18, 70);
        const grad = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, radius);
        grad.addColorStop(0, alert.alert_level >= 2 ? "rgba(220,38,38,0.80)" : "rgba(245,158,11,0.75)");
        grad.addColorStop(1, "rgba(245,158,11,0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(c.x, c.y, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }, [alerts, thermal, showThermalLayer, mapRevision]);

  const selectedIds = Array.from(new Set([...vehicles.map((v) => v.id), ...DEFAULT_VEHICLES]));
  const liveCount = vehicles.filter((v) => !v.offline && v.heartbeat != null).length;
  const criticalAlerts = alerts.filter((a) => a.alert_level >= 2).length;

  return (
    <div style={S.root}>
      <header style={S.header}>
        <div>
          <div style={S.title}>AIP Fleet Dashboard</div>
          <div style={S.subtitle}>ROS2 fleet state, AI vision, thermal map</div>
        </div>
        <div style={S.summary}>
          <span style={{ ...S.badge, background: liveCount > 0 ? "#26a269" : "#6b7280" }}>{liveCount} online</span>
          <span style={{ ...S.badge, background: criticalAlerts > 0 ? "#dc2626" : "#334155" }}>{criticalAlerts} high</span>
        </div>
      </header>

      <section style={S.vehicleGrid}>
        {vehicles.map((vehicle) => <VehicleCard key={vehicle.id} vehicle={vehicle} />)}
      </section>

      <section style={S.mainGrid}>
        <div style={S.panel}>
          <div style={S.panelHeader}>
            <strong>AI Vision</strong>
            <select
              value={selectedVehicle}
              onChange={(event) => setSelectedVehicle(event.target.value)}
              style={S.select}
            >
              {selectedIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </div>
          <canvas ref={videoCanvasRef} style={S.videoCanvas} />
        </div>

        <div style={S.panel}>
          <div style={S.panelHeader}>
            <strong>Map / Thermal Layer</strong>
            <label style={S.toggle}>
              <input
                type="checkbox"
                checked={showThermalLayer}
                onChange={(event) => setShowThermalLayer(event.target.checked)}
              />
              Heatmap
            </label>
          </div>
          <canvas ref={mapCanvasRef} style={S.mapCanvas} />
        </div>
      </section>

      <section style={S.panel}>
        <div style={S.panelHeader}>
          <strong>Perception Alerts</strong>
          <span style={S.muted}>Bounding boxes come from /&lt;ns&gt;/detections or /fleet/alerts.</span>
        </div>
        {alerts.length === 0 ? (
          <div style={S.empty}>No active alerts</div>
        ) : (
          <div style={S.alertList}>
            {alerts.map((alert) => (
              <div key={alert.vehicle_id} style={S.alertRow}>
                <span style={{ ...S.badge, background: alert.alert_level >= 2 ? "#dc2626" : "#f59e0b" }}>
                  {alert.alert_level >= 2 ? "HIGH" : "WARN"}
                </span>
                <strong>{alert.vehicle_id}</strong>
                <span>{alert.max_temp_c.toFixed(1)} C</span>
                <span style={S.muted}>conf {((alert.confidence ?? 0) * 100).toFixed(0)}%</span>
                {alert.map_position && (
                  <span style={S.muted}>
                    map ({alert.map_position.x.toFixed(1)}, {alert.map_position.y.toFixed(1)})
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

const S: Record<string, CSSProperties> = {
  root: {
    minHeight: "100%",
    padding: 10,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    background: "#0f172a",
    color: "#e5e7eb",
    fontFamily: "Inter, Segoe UI, sans-serif",
    fontSize: 12,
    overflow: "auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  title: { fontSize: 16, fontWeight: 800, letterSpacing: 0 },
  subtitle: { color: "#94a3b8", marginTop: 2 },
  summary: { display: "flex", gap: 6, flexWrap: "wrap" },
  badge: {
    color: "#fff",
    borderRadius: 4,
    padding: "2px 7px",
    fontSize: 10,
    fontWeight: 800,
    letterSpacing: 0,
  },
  vehicleGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: 8,
  },
  vehicleCard: {
    background: "#111827",
    border: "1px solid",
    borderRadius: 6,
    padding: 8,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    minHeight: 112,
  },
  vehicleHead: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 },
  metricRow: { display: "flex", justifyContent: "space-between", color: "#cbd5e1", fontSize: 11 },
  barShell: { height: 6, background: "#334155", borderRadius: 3, overflow: "hidden" },
  barFill: { height: "100%", borderRadius: 3, transition: "width 120ms linear" },
  tags: { display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center", minHeight: 16 },
  tag: { padding: "1px 5px", borderRadius: 3, background: "#263244", color: "#cbd5e1", fontSize: 10 },
  mainGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(320px, 1.15fr) minmax(300px, 1fr)",
    gap: 10,
  },
  panel: {
    background: "#111827",
    border: "1px solid #253044",
    borderRadius: 6,
    padding: 8,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    minWidth: 0,
  },
  panelHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" },
  select: {
    background: "#172033",
    color: "#e5e7eb",
    border: "1px solid #334155",
    borderRadius: 4,
    padding: "3px 6px",
  },
  toggle: { display: "flex", gap: 5, alignItems: "center", color: "#cbd5e1" },
  videoCanvas: { width: "100%", aspectRatio: "16 / 9", background: "#0b1220", borderRadius: 4 },
  mapCanvas: { width: "100%", aspectRatio: "16 / 9", background: "#0b1220", borderRadius: 4 },
  alertList: { display: "flex", flexDirection: "column", gap: 5 },
  alertRow: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", padding: "4px 0" },
  muted: { color: "#94a3b8", fontSize: 11 },
  empty: { color: "#94a3b8", padding: "5px 0" },
};

export function initFleetDashboard(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<FleetDashboard context={context} />);
  return () => root.unmount();
}
