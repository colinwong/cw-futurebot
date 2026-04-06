/**
 * Convert any event data object into a human-readable string.
 * Handles known fields gracefully, falls back to key=value pairs for unknown data.
 * Never shows raw JSON braces/brackets.
 */
export function formatEventData(d: Record<string, unknown>): string {
  // Order fill event (from fill callback)
  if (d.action === "filled" && d.ib_order_id) {
    const price = d.fill_price ? ` @ ${(d.fill_price as number).toFixed(2)}` : "";
    return `${d.side || ""} ${d.symbol || ""} filled${price} x${d.quantity || ""}`.trim();
  }
  // Close order submitted
  if (d.action === "close_submitted") {
    return `Close order submitted for ${d.symbol || ""}`;
  }
  // Order with status
  if (d.status && d.ib_order_id) {
    const price = d.fill_price ? ` @ ${(d.fill_price as number).toFixed(2)}` : "";
    return `Order #${d.ib_order_id} ${d.status}${price}${d.quantity ? ` x${d.quantity}` : ""}`;
  }
  // New bracket order
  if (d.action === "new_bracket") {
    return "New bracket order placed";
  }
  // Position update
  if (d.action === "updated" || d.action === "new") {
    return `Position ${d.action}${d.position_id ? ` #${d.position_id}` : ""}`;
  }
  // Position with direction
  if (d.direction && d.symbol) {
    const price = d.entry_price ? ` @ ${(d.entry_price as number).toFixed(2)}` : "";
    return `${d.direction} ${d.symbol} x${d.quantity || 1}${price}`;
  }
  // System event type
  if (d.event_type) {
    return `${d.event_type}${d.details ? `: ${summarizeValue(d.details)}` : ""}`;
  }
  // Named event
  if (d.event) {
    return String(d.event).replace(/_/g, " ");
  }
  // Message field
  if (d.message) {
    return String(d.message);
  }

  // Generic fallback — readable key: value pairs
  const parts: string[] = [];
  for (const [k, v] of Object.entries(d)) {
    if (v === null || v === undefined || k === "type") continue;
    parts.push(`${k}: ${summarizeValue(v)}`);
    if (parts.length >= 3) break;
  }
  return parts.join(" · ") || "—";
}

/**
 * Clean any string that looks like JSON into readable text.
 * Call this on any message before displaying — catches anything
 * that slipped through formatEventData.
 */
export function cleanJsonString(s: string): string {
  // If it doesn't look like JSON, return as-is
  if (!s.includes("{") && !s.includes("[")) return s;

  // Try to parse and re-format
  try {
    const parsed = JSON.parse(s);
    if (typeof parsed === "object" && parsed !== null) {
      return formatEventData(parsed as Record<string, unknown>);
    }
  } catch {
    // Not valid JSON — clean up common patterns
  }

  // Remove JSON syntax characters for partial JSON strings
  return s
    .replace(/[{}[\]"]/g, "")
    .replace(/,\s*/g, ", ")
    .replace(/:\s*/g, ": ")
    .replace(/\s+/g, " ")
    .trim();
}

function summarizeValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v.length > 40 ? v.slice(0, 40) + "…" : v;
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return `[${v.length} items]`;
  if (typeof v === "object") {
    const keys = Object.keys(v as Record<string, unknown>);
    return keys.length <= 3 ? keys.join(", ") : `{${keys.length} fields}`;
  }
  return String(v);
}
