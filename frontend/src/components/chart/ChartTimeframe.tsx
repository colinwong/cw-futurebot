"use client";

const TIMEFRAMES = [
  { label: "1m", barSize: "1 min", duration: "1 D" },
  { label: "5m", barSize: "5 mins", duration: "2 D" },
  { label: "15m", barSize: "15 mins", duration: "5 D" },
  { label: "1h", barSize: "1 hour", duration: "1 W" },
  { label: "4h", barSize: "4 hours", duration: "1 M" },
  { label: "1D", barSize: "1 day", duration: "6 M" },
];

interface ChartTimeframeProps {
  selected: string;
  onSelect: (barSize: string, duration: string) => void;
}

export default function ChartTimeframe({ selected, onSelect }: ChartTimeframeProps) {
  return (
    <div className="flex gap-1">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.label}
          onClick={() => onSelect(tf.barSize, tf.duration)}
          className={`px-2 py-0.5 text-xs rounded ${
            selected === tf.barSize
              ? "bg-blue-600 text-white"
              : "bg-gray-800 text-gray-400 hover:bg-gray-700"
          }`}
        >
          {tf.label}
        </button>
      ))}
    </div>
  );
}
