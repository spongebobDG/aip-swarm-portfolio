import { ExtensionContext } from "@foxglove/extension";

import { initEStopPanel } from "../EStopPanel/src/EStopPanel";
import { initFleetDashboard } from "../FleetDashboard/src/FleetDashboard";
import { initOverridePanel } from "../OverridePanel/src/OverridePanel";
import { initPatrolPlannerPanel } from "../PatrolPlannerPanel/src/PatrolPlannerPanel";

export function activate(ctx: ExtensionContext): void {
  ctx.registerPanel({ name: "AIP E-Stop", initPanel: initEStopPanel });
  ctx.registerPanel({ name: "AIP Override", initPanel: initOverridePanel });
  ctx.registerPanel({ name: "AIP Fleet Dashboard", initPanel: initFleetDashboard });
  ctx.registerPanel({ name: "AIP Patrol Planner", initPanel: initPatrolPlannerPanel });
}
