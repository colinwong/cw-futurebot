"use client";

import { useState } from "react";

interface TooltipProps {
  text: string;
}

export default function Tooltip({ text }: TooltipProps) {
  const [show, setShow] = useState(false);

  return (
    <span className="relative inline-block">
      <span
        className="cursor-help text-gray-500 hover:text-gray-300 ml-1"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
      >
        ?
      </span>
      {show && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1 w-64 px-3 py-2 text-xs text-gray-200 bg-gray-800 border border-gray-700 rounded shadow-lg">
          {text}
        </div>
      )}
    </span>
  );
}
