"use client";

import AccountBar from "@/components/layout/AccountBar";
import EngineStatus from "@/components/layout/EngineStatus";
import DualChartLayout from "@/components/layout/DualChartLayout";
import PositionsAndOrders from "@/components/trading/PositionsAndOrders";
import OrderEntry from "@/components/trading/OrderEntry";
import ActivityLog from "@/components/trading/ActivityLog";
import SignalFeed from "@/components/signals/SignalFeed";
import NewsFeed from "@/components/news/NewsFeed";

export default function TradingTerminal() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AccountBar />
      <EngineStatus />

      {/* Charts */}
      <div className="p-2 shrink-0">
        <DualChartLayout />
      </div>

      {/* Positions & Orders (grouped) */}
      <PositionsAndOrders />

      {/* Bottom panel: Order Entry | Signal Feed | News Feed — fills remaining height */}
      <div className="grid grid-cols-3 border-t border-gray-800 flex-1 min-h-0">
        <div className="border-r border-gray-800 flex flex-col min-h-0">
          <div className="shrink-0">
            <OrderEntry />
          </div>
          <div className="border-t border-gray-800 flex-1 overflow-y-auto min-h-0">
            <NewsFeed />
          </div>
        </div>
        <div className="border-r border-gray-800 overflow-y-auto">
          <SignalFeed />
        </div>
        <div className="overflow-y-auto">
          <ActivityLog />
        </div>
      </div>
    </div>
  );
}
