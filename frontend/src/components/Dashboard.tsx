/**
 * components/Dashboard.tsx
 * Main dashboard layout integrating all components.
 */

import React, { useEffect, useState } from "react";
import { AlertTriangle, Loader } from "lucide-react";
import { fetchForecast } from "../api/client";
import { MetricsRow } from "./MetricsRow";
import { DemandChart } from "./DemandChart";
import { AgentTerminal } from "./AgentTerminal";
import type { TriageState } from "../types/index";

export const Dashboard: React.FC = () => {
  const [triageState, setTriageState] = useState<TriageState>({
    predictedDemand: 0,
    clusterCapacity: 0,
    shortage: 0,
    preemptionPlan: "",
    alertLog: "",
    isLoading: true,
    hasShortage: false,
  });

  const [forecastError, setForecastError] = useState<string | null>(null);

  // Fetch the forecast on component mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        setForecastError(null);
        const forecast = await fetchForecast();

        const shortage = Math.max(
          0,
          forecast.predicted_demand - forecast.cluster_capacity,
        );

        setTriageState((prev) => ({
          ...prev,
          predictedDemand: forecast.predicted_demand,
          clusterCapacity: forecast.cluster_capacity,
          shortage,
          hasShortage: shortage > 0,
          isLoading: false,
        }));
      } catch (error: any) {
        setForecastError(
          error.message ||
            "Failed to fetch forecast. Ensure the backend is running on http://localhost:8000",
        );
        setTriageState((prev) => ({
          ...prev,
          isLoading: false,
        }));
      }
    };

    fetchData();
  }, []);

  const handleTriageComplete = (data: {
    shortage: number;
    preemptionPlan: string;
    alertLog: string;
  }) => {
    setTriageState((prev) => ({
      ...prev,
      shortage: data.shortage,
      preemptionPlan: data.preemptionPlan,
      alertLog: data.alertLog,
    }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100 p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <div className="mb-8 border-b border-slate-700 pb-6">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-3xl sm:text-4xl font-bold bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
            Sentinel-SRE
          </h1>
          <div className="text-xs sm:text-sm text-slate-400">
            GPU Cluster Management Dashboard
          </div>
        </div>
        <p className="text-slate-400 text-sm">
          Autonomous demand forecasting & Kubernetes preemption scheduler
        </p>
      </div>

      {/* Loading State */}
      {triageState.isLoading && (
        <div className="flex flex-col items-center justify-center py-12">
          <Loader className="w-8 h-8 text-cyan-400 animate-spin mb-3" />
          <p className="text-slate-300">Loading forecast data...</p>
          <p className="text-xs text-slate-500 mt-2">
            Ensure the backend is running: python backend/main.py
          </p>
        </div>
      )}

      {/* Error State */}
      {forecastError && !triageState.isLoading && (
        <div className="bg-red-900 border border-red-700 rounded-lg p-6 mb-6 flex items-start gap-3">
          <AlertTriangle className="w-6 h-6 text-red-400 flex-shrink-0 mt-1" />
          <div>
            <h3 className="font-bold text-red-200 mb-1">Connection Error</h3>
            <p className="text-red-100 text-sm">{forecastError}</p>
            <p className="text-red-200 text-xs mt-2">
              Backend URL: http://localhost:8000
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      {!triageState.isLoading && (
        <>
          {/* Metrics Row */}
          <MetricsRow
            clusterCapacity={triageState.clusterCapacity}
            predictedDemand={triageState.predictedDemand}
            shortage={triageState.shortage}
          />

          {/* Demand Chart */}
          {triageState.clusterCapacity > 0 && (
            <DemandChart
              clusterCapacity={triageState.clusterCapacity}
              predictedDemand={triageState.predictedDemand}
            />
          )}

          {/* Alert Banner if Shortage */}
          {triageState.hasShortage && (
            <div className="bg-gradient-to-r from-orange-900 to-red-900 border border-red-700 rounded-lg p-4 mb-6 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-orange-400 flex-shrink-0 mt-1" />
              <div>
                <h3 className="font-bold text-orange-200">
                  GPU Shortage Detected
                </h3>
                <p className="text-orange-100 text-sm mt-1">
                  Predicted demand exceeds cluster capacity. AI triage workflow
                  is running to generate preemption strategy.
                </p>
              </div>
            </div>
          )}

          {/* Agent Terminal */}
          <AgentTerminal
            predictedDemand={triageState.predictedDemand}
            onTriageComplete={handleTriageComplete}
          />

          {/* Results Summary (shown after triage completes) */}
          {triageState.alertLog && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
              {/* Preemption Plan */}
              {triageState.preemptionPlan && (
                <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg">
                  <h3 className="text-lg font-bold text-cyan-400 mb-3">
                    🔧 Preemption Plan
                  </h3>
                  <p className="text-slate-300 text-sm leading-relaxed">
                    {triageState.preemptionPlan}
                  </p>
                </div>
              )}

              {/* Alert Log */}
              <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg">
                <h3 className="text-lg font-bold text-purple-400 mb-3">
                  📋 Alert Log
                </h3>
                <pre className="text-slate-300 text-xs leading-relaxed overflow-x-auto bg-slate-950 p-3 rounded border border-slate-700 max-h-64 overflow-y-auto">
                  {triageState.alertLog}
                </pre>
              </div>
            </div>
          )}
        </>
      )}

      {/* Footer */}
      <div className="mt-12 pt-6 border-t border-slate-700 text-center text-xs text-slate-500">
        <p>Sentinel-SRE v1.0.0 • GPU Cluster Triage System</p>
        <p className="mt-1">
          Backend: http://localhost:8000 • WebSocket: ws://localhost:8000
        </p>
      </div>
    </div>
  );
};
