/**
 * App.tsx
 * Main React application entry point for Sentinel-SRE GPU Cluster Dashboard.
 */

import React from "react";
import { Dashboard } from "./components/Dashboard";
import "./index.css";

function App() {
  return (
    <main className="w-full">
      <Dashboard />
    </main>
  );
}

export default App;
