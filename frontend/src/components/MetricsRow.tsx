/**
 * components/MetricsRow.tsx
 * Three metric cards: Total Capacity, Predicted Demand, and Shortage.
 */

import React from "react";
import { TrendingUp, Gauge, AlertTriangle } from "lucide-react";

interface MetricsRowProps {
  clusterCapacity: number;
  predictedDemand: number;
  shortage: number;
}

export const MetricsRow: React.FC<MetricsRowProps> = ({
  clusterCapacity,
  predictedDemand,
  shortage,
}) => {
  const utilizationPercent = Math.round(
    (predictedDemand / clusterCapacity) * 100,
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      {/* Cluster Capacity Card */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg hover:shadow-xl transition-shadow">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium uppercase tracking-wide">
              Cluster Capacity
            </p>
            <p className="text-4xl font-bold text-cyan-400 mt-2">
              {clusterCapacity.toLocaleString()}
            </p>
            <p className="text-xs text-slate-500 mt-1">GPU Units</p>
          </div>
          <Gauge className="w-12 h-12 text-cyan-500 opacity-20" />
        </div>
      </div>

      {/* Predicted Demand Card */}
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg hover:shadow-xl transition-shadow">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium uppercase tracking-wide">
              Predicted Demand
            </p>
            <p className="text-4xl font-bold text-green-400 mt-2">
              {predictedDemand.toLocaleString()}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Utilization: {utilizationPercent}%
            </p>
          </div>
          <TrendingUp className="w-12 h-12 text-green-500 opacity-20" />
        </div>
      </div>

      {/* Shortage Card */}
      <div
        className={`bg-gradient-to-br ${
          shortage > 0
            ? "from-orange-900 to-red-900 border-red-700"
            : "from-slate-800 to-slate-900 border-slate-700"
        } border rounded-lg p-6 shadow-lg hover:shadow-xl transition-shadow`}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm font-medium uppercase tracking-wide">
              GPU Shortage
            </p>
            <p
              className={`text-4xl font-bold mt-2 ${
                shortage > 0 ? "text-orange-300" : "text-emerald-400"
              }`}
            >
              {shortage.toLocaleString()}
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {shortage > 0 ? "Action Required" : "No Shortage Detected"}
            </p>
          </div>
          <AlertTriangle
            className={`w-12 h-12 opacity-20 ${
              shortage > 0 ? "text-orange-500" : "text-emerald-500"
            }`}
          />
        </div>
      </div>
    </div>
  );
};
