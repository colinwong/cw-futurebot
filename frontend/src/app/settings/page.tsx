"use client";

export default function SettingsPage() {
  return (
    <div className="p-4">
      <h1 className="text-lg font-bold mb-4">Settings</h1>

      <div className="grid grid-cols-2 gap-6 max-w-4xl">
        {/* Trading Parameters */}
        <div className="bg-gray-900 rounded p-4">
          <h2 className="text-sm font-bold mb-3">Trading Parameters</h2>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Max Position Size</span>
              <span>5 contracts</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Daily Loss Limit</span>
              <span>$2,000</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Default Stop (ticks)</span>
              <span>20</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Default Target (ticks)</span>
              <span>40</span>
            </div>
          </div>
        </div>

        {/* Strategy Control */}
        <div className="bg-gray-900 rounded p-4">
          <h2 className="text-sm font-bold mb-3">Strategies</h2>
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span>EMA Crossover</span>
              <span className="text-green-400">Active</span>
            </div>
          </div>
          <p className="text-gray-600 text-xs mt-4">
            Strategy configuration will be available in a future update.
          </p>
        </div>

        {/* Connection Info */}
        <div className="bg-gray-900 rounded p-4">
          <h2 className="text-sm font-bold mb-3">Connections</h2>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">IB Gateway</span>
              <span>localhost:4002</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Backend API</span>
              <span>localhost:8002</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">News Provider</span>
              <span>Finnhub</span>
            </div>
          </div>
        </div>

        {/* Engine Status */}
        <div className="bg-gray-900 rounded p-4">
          <h2 className="text-sm font-bold mb-3">Engine</h2>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-500">Eval Interval</span>
              <span>30s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Reconciliation Interval</span>
              <span>300s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">News Analysis Model</span>
              <span>claude-sonnet-4-6</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
