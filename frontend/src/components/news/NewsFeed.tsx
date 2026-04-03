"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";
import type { NewsEvent, ImpactRating, Sentiment } from "@/lib/types";

const impactColors: Record<ImpactRating, string> = {
  LOW: "bg-gray-700 text-gray-400",
  MEDIUM: "bg-yellow-900 text-yellow-400",
  HIGH: "bg-orange-900 text-orange-400",
  CRITICAL: "bg-red-900 text-red-400",
};

const sentimentColors: Record<Sentiment, string> = {
  BULLISH: "text-green-400",
  BEARISH: "text-red-400",
  NEUTRAL: "text-gray-400",
};

export default function NewsFeed() {
  const [news, setNews] = useState<NewsEvent[]>([]);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsub = subscribe("news", (data) => {
      const item = data as NewsEvent;
      setNews((prev) => [item, ...prev].slice(0, 50));
    });
    return unsub;
  }, [subscribe]);

  return (
    <div className="p-3 h-full">
      <div className="text-sm font-bold text-gray-300 mb-2">News Feed</div>
      {news.length === 0 ? (
        <div className="text-xs text-gray-600">Waiting for news...</div>
      ) : (
        <div className="space-y-2">
          {news.map((item) => (
            <div key={item.id} className="text-xs border-b border-gray-800 pb-1.5">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-gray-500">
                  {formatTime(item.timestamp)}
                </span>
                <span
                  className={`px-1 py-0.5 rounded text-xs ${impactColors[item.impact_rating]}`}
                >
                  {item.impact_rating}
                </span>
                <span className={`text-xs ${sentimentColors[item.sentiment]}`}>
                  {item.sentiment}
                </span>
                {item.is_significant && (
                  <span className="text-xs text-yellow-400">★</span>
                )}
              </div>
              <div className="text-gray-300">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-blue-400 hover:underline"
                  >
                    {item.headline}
                  </a>
                ) : (
                  item.headline
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-gray-600">{item.source}</span>
                {item.analysis && (
                  <span className="text-gray-500">
                    — {(item.analysis as Record<string, string>).reasoning?.slice(0, 100)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
