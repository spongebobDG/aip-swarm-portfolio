import { PanelExtensionContext } from "@foxglove/extension";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

// ── 타입 정의 ─────────────────────────────────────────────────────────────────

interface MapInfo {
  width: number;
  height: number;
  resolution: number;
  originX: number;
  originY: number;
}

interface Waypoint {
  x: number;
  y: number;
  yawDeg: number;
}

type EditMode = "waypoints" | "coverage_box";

// ── 상수 ─────────────────────────────────────────────────────────────────────

const VEHICLES = ["peer_1", "peer_2", "peer_3"];

const VIZ_COLORS: Record<string, string> = {
  peer_1: "#4ade80",
  peer_2: "#60a5fa",
  peer_3: "#fb923c",
};

const emptyWps = (): Record<string, Waypoint[]> =>
  Object.fromEntries(VEHICLES.map((v) => [v, []]));

// ── 좌표 변환 헬퍼 ─────────────────────────────────────────────────────────────

function canvasToWorld(
  cx: number,
  cy: number,
  cw: number,
  ch: number,
  info: MapInfo,
): { x: number; y: number } {
  const px = (cx / cw) * info.width;
  const py = ((ch - cy) / ch) * info.height; // Y축 반전
  return {
    x: info.originX + px * info.resolution,
    y: info.originY + py * info.resolution,
  };
}

function worldToCanvas(
  wx: number,
  wy: number,
  cw: number,
  ch: number,
  info: MapInfo,
): { x: number; y: number } {
  const px = (wx - info.originX) / info.resolution;
  const py = (wy - info.originY) / info.resolution;
  return {
    x: (px / info.width) * cw,
    y: ch - (py / info.height) * ch, // Y축 반전
  };
}

// ── 메인 컴포넌트 ───────────────────────────────────────────────────────────────

function PatrolPlannerPanel({ context }: { context: PanelExtensionContext }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapDataRef = useRef<number[] | null>(null);
  const dragRef = useRef<{
    active: boolean;
    startWorld: { x: number; y: number } | null;
    endWorld: { x: number; y: number } | null;
  }>({ active: false, startWorld: null, endWorld: null });

  const [mapInfo, setMapInfo] = useState<MapInfo | null>(null);
  const [waypoints, setWaypoints] = useState<Record<string, Waypoint[]>>(emptyWps);
  const [activeVehicle, setActiveVehicle] = useState("peer_1");
  const [editMode, setEditMode] = useState<EditMode>("waypoints");
  const [rowSpacing, setRowSpacing] = useState(2.0);
  const [sweepHeading, setSweepHeading] = useState(0);
  const [boxPreview, setBoxPreview] = useState<{
    x1: number; y1: number; x2: number; y2: number;
  } | null>(null);
  const [redraw, setRedraw] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");

  // ── 토픽 구독 및 렌더 콜백 ──────────────────────────────────────────────────

  useLayoutEffect(() => {
    context.subscribe([
      { topic: "/map_static" },
      { topic: "/patrol_planner/plan_state" },
    ]);

    context.advertise?.("/patrol_planner/cmd", "std_msgs/msg/String");

    context.onRender = (renderState, done) => {
      for (const { topic, message } of renderState.currentFrame ?? []) {
        const msg = message as Record<string, unknown>;

        if (topic === "/map_static") {
          // OccupancyGrid
          const info = msg["info"] as {
            width: number; height: number; resolution: number;
            origin: { position: { x: number; y: number } };
          };
          setMapInfo({
            width: info.width,
            height: info.height,
            resolution: info.resolution,
            originX: info.origin.position.x,
            originY: info.origin.position.y,
          });
          mapDataRef.current = msg["data"] as number[];
          setRedraw((n) => n + 1);
        } else if (topic === "/patrol_planner/plan_state") {
          try {
            const state = JSON.parse(String(msg["data"] ?? "{}")) as {
              vehicles: Record<string, [number, number, number][]>;
              active?: string;
            };
            if (state.vehicles) {
              const updated: Record<string, Waypoint[]> = {};
              for (const [vid, wps] of Object.entries(state.vehicles)) {
                updated[vid] = wps.map(([x, y, yawDeg]) => ({ x, y, yawDeg }));
              }
              setWaypoints((prev) => ({ ...prev, ...updated }));
              if (state.active) setActiveVehicle(state.active);
              setRedraw((n) => n + 1);
            }
          } catch {
            // JSON 파싱 실패 무시
          }
        }
      }
      done();
    };

    return () => {
      context.unadvertise?.("/patrol_planner/cmd");
    };
  }, [context]);

  // ── 캔버스 리사이즈 ────────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const observer = new ResizeObserver(() => {
      const W = canvas.clientWidth;
      const H = canvas.clientHeight;
      if (W > 0 && H > 0) {
        canvas.width = W;
        canvas.height = H;
        setRedraw((n) => n + 1);
      }
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  // ── 캔버스 렌더링 ─────────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    if (W === 0 || H === 0) return;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#111827";
    ctx.fillRect(0, 0, W, H);

    const data = mapDataRef.current;
    if (!data || !mapInfo) {
      ctx.fillStyle = "#6b7280";
      ctx.font = "13px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("/map_static 수신 대기 중…", W / 2, H / 2);
      return;
    }

    // ── OccupancyGrid 렌더링 ─────────────────────────────────────────────────
    const offscreen = document.createElement("canvas");
    offscreen.width = mapInfo.width;
    offscreen.height = mapInfo.height;
    const oCtx = offscreen.getContext("2d");
    if (oCtx) {
      const imgData = oCtx.createImageData(mapInfo.width, mapInfo.height);
      for (let i = 0; i < data.length; i++) {
        const v = data[i]!;
        const p = i * 4;
        if (v < 0) {
          // Unknown
          imgData.data[p] = 180; imgData.data[p + 1] = 185;
          imgData.data[p + 2] = 190; imgData.data[p + 3] = 180;
        } else if (v === 0) {
          // Free
          imgData.data[p] = 240; imgData.data[p + 1] = 245;
          imgData.data[p + 2] = 250; imgData.data[p + 3] = 255;
        } else {
          // Occupied
          const d = Math.max(15, 90 - v);
          imgData.data[p] = d; imgData.data[p + 1] = d;
          imgData.data[p + 2] = d; imgData.data[p + 3] = 255;
        }
      }
      oCtx.putImageData(imgData, 0, 0);
      ctx.save();
      ctx.translate(0, H);
      ctx.scale(W / mapInfo.width, -H / mapInfo.height);
      ctx.drawImage(offscreen, 0, 0);
      ctx.restore();
    }

    // ── 각 차량 순찰 경로 렌더링 ────────────────────────────────────────────
    for (const vid of VEHICLES) {
      const wps = waypoints[vid] ?? [];
      const color = VIZ_COLORS[vid] ?? "#ccc";
      const isActive = vid === activeVehicle;
      ctx.globalAlpha = isActive ? 1.0 : 0.30;

      if (wps.length >= 2) {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = isActive ? 2.5 : 1.5;
        ctx.setLineDash([]);
        wps.forEach((wp, i) => {
          const c = worldToCanvas(wp.x, wp.y, W, H, mapInfo);
          i === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y);
        });
        // 루프 닫기
        const c0 = worldToCanvas(wps[0]!.x, wps[0]!.y, W, H, mapInfo);
        ctx.lineTo(c0.x, c0.y);
        ctx.stroke();
      }

      wps.forEach((wp, i) => {
        const c = worldToCanvas(wp.x, wp.y, W, H, mapInfo);
        const r = isActive ? 7 : 4;
        ctx.beginPath();
        ctx.arc(c.x, c.y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        if (isActive) {
          ctx.fillStyle = "#000";
          ctx.font = "bold 9px sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(String(i + 1), c.x, c.y + 3.5);
        }
      });
    }
    ctx.globalAlpha = 1.0;

    // ── 커버리지 박스 미리보기 ───────────────────────────────────────────────
    if (boxPreview) {
      const p1 = worldToCanvas(boxPreview.x1, boxPreview.y1, W, H, mapInfo);
      const p2 = worldToCanvas(boxPreview.x2, boxPreview.y2, W, H, mapInfo);
      const rx = Math.min(p1.x, p2.x);
      const ry = Math.min(p1.y, p2.y);
      const rw = Math.abs(p2.x - p1.x);
      const rh = Math.abs(p2.y - p1.y);
      ctx.globalAlpha = 0.25;
      ctx.fillStyle = "#facc15";
      ctx.fillRect(rx, ry, rw, rh);
      ctx.globalAlpha = 0.85;
      ctx.strokeStyle = "#facc15";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(rx, ry, rw, rh);
      ctx.setLineDash([]);
      ctx.globalAlpha = 1.0;
    }
  }, [redraw, mapInfo, waypoints, activeVehicle, boxPreview]);

  // ── 명령 발행 ─────────────────────────────────────────────────────────────

  const sendCmd = useCallback(
    (cmd: string) => {
      context.publish?.("/patrol_planner/cmd", { data: cmd });
    },
    [context],
  );

  // ── 마우스 이벤트 헬퍼 ─────────────────────────────────────────────────────

  const getWorldCoords = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas || !mapInfo) return null;
      const rect = canvas.getBoundingClientRect();
      return canvasToWorld(
        e.clientX - rect.left,
        e.clientY - rect.top,
        canvas.width,
        canvas.height,
        mapInfo,
      );
    },
    [mapInfo],
  );

  // ── 캔버스 이벤트 핸들러 ──────────────────────────────────────────────────

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (editMode !== "waypoints") return;
      const w = getWorldCoords(e);
      if (!w) return;

      const prevWps = waypoints[activeVehicle] ?? [];
      const newWp: Waypoint = {
        x: w.x,
        y: w.y,
        // yaw: 이전 포인트 방향 자동 계산
        yawDeg:
          prevWps.length > 0
            ? Math.round(
                (Math.atan2(
                  w.y - prevWps[prevWps.length - 1]!.y,
                  w.x - prevWps[prevWps.length - 1]!.x,
                ) *
                  180) /
                  Math.PI,
              )
            : 0,
      };
      const updated = [...prevWps, newWp];
      setWaypoints((prev) => ({ ...prev, [activeVehicle]: updated }));

      // yaw를 앞 포인트 방향으로 소급 보정 후 전송
      const wpStr = updated
        .map((wp, i) => {
          const next = updated[i + 1];
          const yaw = next
            ? Math.round(
                (Math.atan2(next.y - wp.y, next.x - wp.x) * 180) / Math.PI,
              )
            : wp.yawDeg;
          return `${wp.x.toFixed(3)},${wp.y.toFixed(3)},${yaw}`;
        })
        .join(";");
      sendCmd(`set_wp_list:${activeVehicle}:${wpStr}`);
      setRedraw((n) => n + 1);
      setStatusMsg(`[${activeVehicle}] 웨이포인트 ${updated.length}개`);
    },
    [editMode, activeVehicle, waypoints, getWorldCoords, sendCmd],
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (editMode !== "coverage_box") return;
      e.preventDefault();
      const w = getWorldCoords(e);
      if (!w) return;
      dragRef.current = { active: true, startWorld: w, endWorld: w };
      setBoxPreview({ x1: w.x, y1: w.y, x2: w.x, y2: w.y });
    },
    [editMode, getWorldCoords],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!dragRef.current.active || !dragRef.current.startWorld) return;
      const w = getWorldCoords(e);
      if (!w) return;
      dragRef.current.endWorld = w;
      const s = dragRef.current.startWorld;
      setBoxPreview({ x1: s.x, y1: s.y, x2: w.x, y2: w.y });
    },
    [getWorldCoords],
  );

  const handleMouseUp = useCallback(
    (_e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!dragRef.current.active) return;
      dragRef.current.active = false;
      const s = dragRef.current.startWorld;
      const end = dragRef.current.endWorld;
      setBoxPreview(null);
      if (!s || !end) return;
      const dw = Math.abs(end.x - s.x);
      const dh = Math.abs(end.y - s.y);
      if (dw < 0.5 || dh < 0.5) {
        setStatusMsg("박스가 너무 작습니다 (최소 0.5m)");
        return;
      }
      sendCmd(
        `coverage_box:${activeVehicle}:${s.x.toFixed(3)},${s.y.toFixed(3)}:${end.x.toFixed(3)},${end.y.toFixed(3)}:${rowSpacing.toFixed(2)}:${sweepHeading}`,
      );
      setEditMode("waypoints");
      setStatusMsg(`[${activeVehicle}] 커버리지 박스 → 간격=${rowSpacing}m, 방향=${sweepHeading}°`);
    },
    [activeVehicle, rowSpacing, sweepHeading, sendCmd],
  );

  // ── 버튼 핸들러 ────────────────────────────────────────────────────────────

  const handleVehicleChange = useCallback(
    (vid: string) => {
      setActiveVehicle(vid);
      sendCmd(`switch:${vid}`);
    },
    [sendCmd],
  );

  const handleUndo = useCallback(() => {
    const wps = waypoints[activeVehicle] ?? [];
    if (wps.length === 0) return;
    const updated = wps.slice(0, -1);
    setWaypoints((prev) => ({ ...prev, [activeVehicle]: updated }));
    sendCmd("undo");
    setRedraw((n) => n + 1);
  }, [activeVehicle, waypoints, sendCmd]);

  const handleClear = useCallback(() => {
    setWaypoints((prev) => ({ ...prev, [activeVehicle]: [] }));
    sendCmd("clear");
    setRedraw((n) => n + 1);
    setStatusMsg(`[${activeVehicle}] 초기화 완료`);
  }, [activeVehicle, sendCmd]);

  const handleSave = useCallback(() => {
    sendCmd("save");
    setStatusMsg("YAML 저장 요청 완료");
  }, [sendCmd]);

  // ── 스타일 헬퍼 ────────────────────────────────────────────────────────────

  const activeWps = waypoints[activeVehicle] ?? [];
  const cursor = editMode === "coverage_box" ? "crosshair" : "cell";

  const btnBase: React.CSSProperties = {
    flex: 1, padding: "4px 6px", border: "none", borderRadius: 4,
    cursor: "pointer", fontWeight: 600, fontSize: 11,
  };

  const tabBtn = (active: boolean): React.CSSProperties => ({
    padding: "3px 8px",
    border: `1px solid ${active ? "#6b7280" : "#374151"}`,
    borderRadius: 4,
    background: active ? "#374151" : "transparent",
    color: "#e5e7eb",
    fontSize: 11,
    cursor: "pointer",
  });

  // ── JSX ───────────────────────────────────────────────────────────────────

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", height: "100%",
        background: "#111827", color: "#e5e7eb", fontFamily: "sans-serif",
        fontSize: 12, padding: 6, boxSizing: "border-box", gap: 4,
        userSelect: "none",
      }}
    >
      {/* ── 차량 선택 ── */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: "#6b7280", marginRight: 2 }}>차량:</span>
        {VEHICLES.map((v) => (
          <button
            key={v}
            onClick={() => handleVehicleChange(v)}
            style={{
              padding: "2px 8px",
              border: `2px solid ${VIZ_COLORS[v]}`,
              borderRadius: 4,
              background: activeVehicle === v ? VIZ_COLORS[v] : "transparent",
              color: activeVehicle === v ? "#000" : VIZ_COLORS[v]!,
              fontWeight: 700, fontSize: 11, cursor: "pointer",
            }}
          >
            {v}
          </button>
        ))}
      </div>

      {/* ── 편집 모드 ── */}
      <div style={{ display: "flex", gap: 4, alignItems: "center", flexShrink: 0, flexWrap: "wrap" }}>
        <button onClick={() => setEditMode("waypoints")} style={tabBtn(editMode === "waypoints")}>
          클릭-웨이포인트
        </button>
        <button onClick={() => setEditMode("coverage_box")} style={{ ...tabBtn(editMode === "coverage_box"), color: "#facc15" }}>
          드래그-커버리지
        </button>
        {editMode === "coverage_box" && (
          <>
            <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11 }}>
              간격
              <input
                type="number" min={0.5} max={20} step={0.5} value={rowSpacing}
                onChange={(e) => setRowSpacing(parseFloat(e.target.value))}
                style={{ width: 44, background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", padding: "1px 3px", borderRadius: 3, fontSize: 11 }}
              />
              m
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 11 }}>
              방향
              <input
                type="number" min={-180} max={180} step={15} value={sweepHeading}
                onChange={(e) => setSweepHeading(parseInt(e.target.value, 10))}
                style={{ width: 40, background: "#1f2937", color: "#e5e7eb", border: "1px solid #374151", padding: "1px 3px", borderRadius: 3, fontSize: 11 }}
              />
              °
            </label>
          </>
        )}
      </div>

      {/* ── 힌트 ── */}
      <div style={{ fontSize: 10, color: "#6b7280", flexShrink: 0 }}>
        {editMode === "waypoints"
          ? "지도를 클릭하여 웨이포인트 추가 (순서대로)"
          : "드래그하여 커버리지 박스 지정 → 자동 생성"}
      </div>

      {/* ── 지도 캔버스 ── */}
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height: "100%", display: "block", cursor }}
          onClick={handleClick}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        />
      </div>

      {/* ── 웨이포인트 목록 ── */}
      <div
        style={{
          maxHeight: 52, overflowY: "auto", flexShrink: 0,
          fontSize: 10, color: "#9ca3af", lineHeight: 1.5,
        }}
      >
        {activeWps.length === 0
          ? "웨이포인트 없음"
          : activeWps.map((wp, i) => (
              <span
                key={i}
                style={{ display: "inline-block", margin: "1px 3px", background: "#1f2937", padding: "1px 5px", borderRadius: 3 }}
              >
                {i + 1}.({wp.x.toFixed(1)},{wp.y.toFixed(1)},{wp.yawDeg}°)
              </span>
            ))}
      </div>

      {/* ── 액션 버튼 ── */}
      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
        <button
          onClick={handleUndo}
          disabled={activeWps.length === 0}
          style={{ ...btnBase, background: "#374151", color: activeWps.length === 0 ? "#6b7280" : "#e5e7eb" }}
        >
          ↩ 되돌리기
        </button>
        <button onClick={handleClear} style={{ ...btnBase, background: "#4b5563", color: "#e5e7eb" }}>
          초기화
        </button>
        <button onClick={handleSave} style={{ ...btnBase, flex: 2, background: "#1d4ed8", color: "#fff" }}>
          💾 YAML 저장
        </button>
      </div>

      {/* ── 상태 요약 / 메시지 ── */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#6b7280", flexShrink: 0 }}>
        <span>
          {VEHICLES.map((v) => (
            <span key={v} style={{ marginRight: 8 }}>
              <span style={{ color: VIZ_COLORS[v] }}>{v}</span>:{" "}
              {waypoints[v]?.length ?? 0}pts
            </span>
          ))}
        </span>
        <span style={{ color: "#9ca3af" }}>{statusMsg}</span>
      </div>
    </div>
  );
}

export function initPatrolPlannerPanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<PatrolPlannerPanel context={context} />);
  return () => {
    root.unmount();
  };
}
