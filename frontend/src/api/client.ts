/**
 * api/client.ts
 * HTTP and WebSocket client for communicating with the Sentinel-SRE backend.
 */

import axios from "axios";
import type {
  ForecastResponse,
  WebSocketMessage,
  ShortageData,
  PreemptionPlanData,
  AlertLogData,
} from "../types/index";

const API_BASE_URL = "http://localhost:8000";
const WS_BASE_URL = "ws://localhost:8000";

/**
 * Fetch the next-hour GPU demand forecast
 */
export async function fetchForecast(): Promise<ForecastResponse> {
  const response = await axios.get<ForecastResponse>(
    `${API_BASE_URL}/api/forecast`
  );
  return response.data;
}

/**
 * Connect to the WebSocket triage endpoint and listen for messages
 * @param predictedDemand The GPU demand to send to the triage workflow
 * @param onMessage Callback function invoked for each WebSocket message
 * @param onError Callback for connection errors
 * @returns A function to close the WebSocket connection
 */
export function connectToTriage(
  predictedDemand: number,
  onMessage: (message: WebSocketMessage) => void,
  onError: (error: string) => void
): () => void {
  const ws = new WebSocket(`${WS_BASE_URL}/ws/triage`);

  ws.onopen = () => {
    console.log("WebSocket connected to /ws/triage");
    // Send the predicted demand to start the triage workflow
    ws.send(JSON.stringify({ predicted_demand: predictedDemand }));
  };

  ws.onmessage = (event) => {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      onMessage(message);
    } catch (error) {
      onError(`Failed to parse WebSocket message: ${error}`);
    }
  };

  ws.onerror = (event) => {
    onError(`WebSocket error: ${event}`);
  };

  ws.onclose = () => {
    console.log("WebSocket disconnected from /ws/triage");
  };

  // Return a function to close the connection
  return () => ws.close();
}
