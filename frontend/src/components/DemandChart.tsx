/**
 * components/DemandChart.tsx
 * Recharts visualization showing historical GPU demand trend and predicted demand.
 */

import React, { useMemo } from "react";
import {
  LineChart,
  Line,
  ReferenceLine,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

interface DemandChartProps {
  clusterCapacity: number;
  predictedDemand: number;
}

interface DataPoint {
  hour: number;
  demand: number;
  capacity: number;
}

export const DemandChart: React.FC<DemandChartProps> = ({
  clusterCapacity,
  predictedDemand,
}) => {
  // Generate 25 hours of historical data (last 24h + predicted next hour)
  const chartData: DataPoint[] = useMemo(() => {
    const data: DataPoint[] = [];

    // Generate historical data (last 24 hours)
    // Simulate a realistic GPU demand pattern with some variation
    for (let i = 0; i < 24; i++) {
      const baseDemand = clusterCapacity * 0.65;
      const variation =
        Math.sin((i / 24) * Math.PI * 2) * clusterCapacity * 0.15;
      const randomNoise = (Math.random() - 0.5) * clusterCapacity * 0.08;
      const demand = Math.max(0, baseDemand + variation + randomNoise);

      data.push({
        hour: i,
        demand: Math.round(demand),
        capacity: clusterCapacity,
      });
    }

    // Add predicted demand for next hour (hour 24)
    data.push({
      hour: 24,
      demand: predictedDemand,
      capacity: clusterCapacity,
    });

    return data;
  }, [clusterCapacity, predictedDemand]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-900 border border-slate-700 rounded px-3 py-2 shadow-lg">
          <p className="text-xs text-slate-300">
            Hour {payload[0].payload.hour}
          </p>
          <p className="text-sm font-semibold text-cyan-400">
            Demand: {payload[0].value.toLocaleString()} GPU
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg mb-6">
      <h2 className="text-lg font-bold text-slate-200 mb-4 flex items-center">
        <div className="w-2 h-2 rounded-full bg-cyan-400 mr-3"></div>
        GPU Demand Forecast (24h + Prediction)
      </h2>

      <ResponsiveContainer width="100%" height={350}>
        <AreaChart
          data={chartData}
          margin={{ top: 5, right: 20, bottom: 5, left: 0 }}
        >
          <defs>
            <linearGradient id="colorDemand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ paddingTop: "20px" }}
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #475569",
              borderRadius: "8px",
            }}
            textStyle={{ color: "#cbd5e1" }}
          />

          {/* Capacity reference line */}
          <ReferenceLine
            y={clusterCapacity}
            stroke="#f97316"
            strokeWidth={2}
            strokeDasharray="5 5"
            name="Capacity Limit"
            label={{
              value: "Cluster Capacity",
              position: "right",
              fill: "#f97316",
              fontSize: 12,
            }}
          />

          {/* Predicted demand reference line */}
          <ReferenceLine
            x={24}
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="5 5"
            label={{
              value: "Predicted Hour",
              position: "top",
              fill: "#ef4444",
              fontSize: 12,
              offset: 10,
            }}
          />

          {/* Area and line for demand */}
          <Area
            type="monotone"
            dataKey="demand"
            stroke="#06b6d4"
            strokeWidth={3}
            fill="url(#colorDemand)"
            name="GPU Demand"
            isAnimationActive={true}
            animationDuration={1000}
          />
        </AreaChart>
      </ResponsiveContainer>

      <div className="mt-4 flex gap-8 text-sm">
        <div>
          <span className="text-slate-500">Peak Demand: </span>
          <span className="text-cyan-400 font-semibold">
            {Math.max(...chartData.map((d) => d.demand)).toLocaleString()} GPU
          </span>
        </div>
        <div>
          <span className="text-slate-500">Next Hour Prediction: </span>
          <span
            className={`font-semibold ${
              predictedDemand > clusterCapacity
                ? "text-orange-400"
                : "text-emerald-400"
            }`}
          >
            {predictedDemand.toLocaleString()} GPU
          </span>
        </div>
      </div>
    </div>
  );
};
