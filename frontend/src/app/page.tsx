"use client";

import AccountBar from "@/components/layout/AccountBar";
import DualChartLayout from "@/components/layout/DualChartLayout";
import PositionStrip from "@/components/trading/PositionStrip";
import OrderBook from "@/components/trading/OrderBook";
import OrderEntry from "@/components/trading/OrderEntry";
import SignalFeed from "@/components/signals/SignalFeed";
import NewsFeed from "@/components/news/NewsFeed";

export default function TradingTerminal() {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AccountBar />

      {/* Charts */}
      <div className="p-2 shrink-0">
        <DualChartLayout />
      </div>

      {/* Positions & Orders */}
      <PositionStrip />
      <OrderBook />

      {/* Bottom panel: Order Entry | Signal Feed | News Feed — fills remaining height */}
      <div className="grid grid-cols-3 border-t border-gray-800 flex-1 min-h-0">
        <div className="border-r border-gray-800 overflow-y-auto">
          <OrderEntry />
        </div>
        <div className="border-r border-gray-800 overflow-y-auto">
          <SignalFeed />
        </div>
        <div className="overflow-y-auto">
          <NewsFeed />
        </div>
      </div>
    </div>
  );
}
