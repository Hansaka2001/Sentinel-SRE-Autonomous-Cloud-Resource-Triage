/**
 * components/AgentTerminal.tsx
 * Black terminal-like window that streams LangGraph agent reasoning logs in real-time.
 */

import React, { useEffect, useRef, useState } from "react";
import { Terminal, AlertCircle } from "lucide-react";
import { connectToTriage } from "../api/client";
import type { AgentLogEntry } from "../types/index";

interface AgentTerminalProps {
  predictedDemand: number;
  onTriageComplete?: (data: {
    shortage: number;
    preemptionPlan: string;
    alertLog: string;
  }) => void;
}

export const AgentTerminal: React.FC<AgentTerminalProps> = ({
  predictedDemand,
  onTriageComplete,
}) => {
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const logIdRef = useRef(0);

  useEffect(() => {
    let closeConnection: (() => void) | null = null;
    let triageData: {
      shortage: number;
      preemptionPlan: string;
      alertLog: string;
    } = {
      shortage: 0,
      preemptionPlan: "",
      alertLog: "",
    };

    // Connect to the WebSocket
    try {
      closeConnection = connectToTriage(
        predictedDemand,
        (message) => {
          const newLog: AgentLogEntry = {
            id: `log-${logIdRef.current++}`,
            timestamp: new Date().toLocaleTimeString("en-US", {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            type: message.event as any,
            message: "",
          };

          // Parse message based on event type
          switch (message.event) {
            case "shortage":
              const shortage = (message.data as any).shortage;
              triageData.shortage = shortage;
              newLog.message =
                shortage > 0
                  ? `⚠️ GPU Shortage Detected: ${shortage} units`
                  : `✓ No shortage detected`;
              break;

            case "no_shortage":
              newLog.message = (message.data as any).message;
              break;

            case "preemption_plan":
              const plan = (message.data as any).preemption_plan;
              triageData.preemptionPlan = plan;
              newLog.message = `🔧 Preemption Plan Generated:\n${plan}`;
              break;

            case "alert_log":
              const alertLog = (message.data as any).alert_log;
              triageData.alertLog = alertLog;
              newLog.message = `📋 Alert Log:\n${alertLog}`;
              break;

            case "done":
              newLog.message = "✅ Triage workflow complete";
              // Invoke callback when done
              if (onTriageComplete) {
                onTriageComplete(triageData);
              }
              break;

            case "error":
              newLog.message = `❌ Error: ${(message.data as any).message}`;
              setError((message.data as any).message);
              break;

            default:
              newLog.message = JSON.stringify(message.data);
          }

          setLogs((prev) => [...prev, newLog]);
          setIsConnected(true);
          setError(null);
        },
        (err) => {
          setError(err);
          setIsConnected(false);
          const errorLog: AgentLogEntry = {
            id: `log-${logIdRef.current++}`,
            timestamp: new Date().toLocaleTimeString("en-US", {
              hour12: false,
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            type: "error",
            message: `Connection Error: ${err}`,
          };
          setLogs((prev) => [...prev, errorLog]);
        },
      );
    } catch (err) {
      setError(`Failed to connect: ${err}`);
    }

    return () => {
      if (closeConnection) {
        closeConnection();
      }
    };
  }, [predictedDemand, onTriageComplete]);

  // Auto-scroll to the bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 rounded-lg p-6 shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-slate-200 flex items-center">
          <Terminal className="w-5 h-5 mr-2 text-green-400" />
          Agent Triage Workflow
        </h2>
        <div className="flex items-center gap-2">
          {isConnected && (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
              Live
            </span>
          )}
          {error && (
            <span className="flex items-center gap-1 text-xs text-red-400">
              <AlertCircle className="w-4 h-4" />
              Error
            </span>
          )}
        </div>
      </div>

      {/* Terminal window */}
      <div className="bg-slate-950 border border-slate-700 rounded font-mono text-sm h-96 overflow-y-auto p-4 space-y-2">
        {/* Initial connection message */}
        {logs.length === 0 && !error && (
          <div className="text-slate-500 text-xs">
            <span className="text-cyan-600">sentinel-sre@localhost:~$ </span>
            <span className="animate-pulse">
              Connecting to triage workflow...
            </span>
          </div>
        )}

        {/* Log entries */}
        {logs.map((log) => (
          <div
            key={log.id}
            className={`text-xs leading-relaxed ${
              log.type === "error"
                ? "text-red-400"
                : log.type === "complete"
                  ? "text-green-400"
                  : log.type === "shortage"
                    ? "text-orange-400"
                    : log.type === "preemption_plan"
                      ? "text-cyan-400"
                      : log.type === "alert_log"
                        ? "text-purple-400"
                        : "text-slate-300"
            }`}
          >
            <span className="text-slate-600">[{log.timestamp}]</span>{" "}
            <span className="whitespace-pre-wrap break-words">
              {log.message}
            </span>
          </div>
        ))}

        {/* Scroll anchor */}
        <div ref={logsEndRef} />
      </div>

      {/* Error message if any */}
      {error && (
        <div className="mt-4 bg-red-900 border border-red-700 rounded p-3 text-red-200 text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Log count info */}
      <div className="mt-4 text-xs text-slate-500">
        {logs.length} events received
        {logs.some((l) => l.type === "done") && (
          <span className="text-green-400 ml-2">✓ Workflow complete</span>
        )}
      </div>
    </div>
  );
};
