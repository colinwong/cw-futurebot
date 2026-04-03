/**
 * Shared timezone utility. All timestamp displays must use these functions.
 * The display timezone is fetched from /api/settings on app load.
 * ALL format functions include the timezone abbreviation (e.g., "ET", "PT").
 */

let displayTimezone = "America/New_York";
const listeners = new Set<() => void>();

const TZ_SHORT_NAMES: Record<string, string> = {
  "America/New_York": "ET",
  "America/Chicago": "CT",
  "America/Denver": "MT",
  "America/Los_Angeles": "PT",
  "UTC": "UTC",
};

export function setDisplayTimezone(tz: string) {
  displayTimezone = tz;
  listeners.forEach((l) => l());
}

export function getDisplayTimezone(): string {
  return displayTimezone;
}

/** Short timezone label (e.g., "ET", "PT") */
export function tzLabel(): string {
  return TZ_SHORT_NAMES[displayTimezone] || displayTimezone;
}

export function onTimezoneChange(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Format to time only with timezone (e.g., "2:30:45 PM ET") */
export function formatTime(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  const time = date.toLocaleTimeString("en-US", { timeZone: displayTimezone });
  return `${time} ${tzLabel()}`;
}

/** Format to date + time with timezone (e.g., "Apr 2, 2:30:45 PM ET") */
export function formatDateTime(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  const dt = date.toLocaleString("en-US", {
    timeZone: displayTimezone,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
  return `${dt} ${tzLabel()}`;
}

/** Format to date only (e.g., "Apr 2") — no timezone needed for dates */
export function formatDate(timestamp: string | number): string {
  const date = typeof timestamp === "number" ? new Date(timestamp * 1000) : new Date(timestamp);
  return date.toLocaleDateString("en-US", {
    timeZone: displayTimezone,
    month: "short",
    day: "numeric",
  });
}

/** Get timezone offset in seconds for shifting chart epoch timestamps. */
export function getTimezoneOffsetSec(): number {
  const now = new Date();
  const utcStr = now.toLocaleString("en-US", { timeZone: "UTC" });
  const tzStr = now.toLocaleString("en-US", { timeZone: displayTimezone });
  const utcDate = new Date(utcStr);
  const tzDate = new Date(tzStr);
  return (tzDate.getTime() - utcDate.getTime()) / 1000;
}
