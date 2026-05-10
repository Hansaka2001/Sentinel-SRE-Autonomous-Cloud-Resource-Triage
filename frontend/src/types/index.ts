/**
 * types/index.ts
 * TypeScript interfaces for the Sentinel-SRE GPU Cluster Dashboard.
 */

/**
 * Response from GET /api/forecast
 * Contains the LSTM-predicted GPU demand and current cluster capacity.
 */
export interface ForecastResponse {
  predicted_demand: number;
  cluster_capacity: number;
}

/**
 * Base structure for WebSocket messages from /ws/triage
 */
export interface WebSocketMessage<T = Record<string, unknown>> {
  event:
    | "shortage"
    | "no_shortage"
    | "preemption_plan"
    | "alert_log"
    | "done"
    | "error";
  data: T;
}

/**
 * Shortage message payload
 */
export interface ShortageData {
  shortage: number;
}

/**
 * Preemption plan payload
 */
export interface PreemptionPlanData {
  preemption_plan: string;
}

/**
 * Alert log payload
 */
export interface AlertLogData {
  alert_log: string;
}

/**
 * No shortage payload
 */
export interface NoShortageData {
  message: string;
}

/**
 * Error payload
 */
export interface ErrorData {
  message: string;
}

/**
 * Agent log entry for display in the terminal
 */
export interface AgentLogEntry {
  id: string;
  timestamp: string;
  type: "shortage" | "preemption_plan" | "alert_log" | "info" | "error" | "complete" | "done";
  message: string;
}

/**
 * Triage workflow state
 */
export interface TriageState {
  predictedDemand: number;
  clusterCapacity: number;
  shortage: number;
  preemptionPlan: string;
  alertLog: string;
  isLoading: boolean;
  hasShortage: boolean;
}
