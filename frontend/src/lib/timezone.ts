/**
 * Shared timezone utility. All timestamp displays must use these functions.
 * The display timezone is fetched from /api/settings on app load.
 */

let displayTimezone = "America/New_York";
const listeners = new Set<() => void>();

export function setDisplayTimezone(tz: string) {
  displayTimezone = tz;
  listeners.forEach((l) => l());
}

export function getDisplayTimezone(): string {
  return displayTimezone;
}

export function onTimezoneChange(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Format a UTC ISO string or epoch seconds to time only (e.g., "2:30:45 PM") */
export function formatTime(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  return date.toLocaleTimeString("en-US", { timeZone: displayTimezone });
}

/** Format a UTC ISO string or epoch seconds to date + time (e.g., "Apr 2, 2:30 PM") */
export function formatDateTime(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  return date.toLocaleString("en-US", {
    timeZone: displayTimezone,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Format a UTC ISO string or epoch seconds to date only (e.g., "Apr 2") */
export function formatDate(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  return date.toLocaleDateString("en-US", {
    timeZone: displayTimezone,
    month: "short",
    day: "numeric",
  });
}

/** Get timezone offset in seconds for shifting chart epoch timestamps.
 *  Lightweight-charts renders epoch seconds as UTC — we shift by the
 *  configured timezone's offset so the chart displays the correct local time. */
export function getTimezoneOffsetSec(): number {
  // Create a date and compare UTC vs timezone-local representation
  const now = new Date();
  const utcStr = now.toLocaleString("en-US", { timeZone: "UTC" });
  const tzStr = now.toLocaleString("en-US", { timeZone: displayTimezone });
  const utcDate = new Date(utcStr);
  const tzDate = new Date(tzStr);
  return (tzDate.getTime() - utcDate.getTime()) / 1000;
}
