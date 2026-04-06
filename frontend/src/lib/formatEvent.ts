/**
 * Convert any event data object into a human-readable string.
 * Handles known fields gracefully, falls back to key=value pairs for unknown data.
 * Never shows raw JSON braces/brackets.
 */
export function formatEventData(d: Record<string, unknown>): string {
  // Known patterns
  if (d.status && d.ib_order_id) {
    const price = d.fill_price ? ` @ ${(d.fill_price as number).toFixed(2)}` : "";
    return `Order #${d.ib_order_id} ${d.status}${price}${d.quantity ? ` x${d.quantity}` : ""}`;
  }
  if (d.action === "updated" || d.action === "new") {
    return `Position ${d.action}${d.position_id ? ` #${d.position_id}` : ""}`;
  }
  if (d.direction && d.symbol) {
    const price = d.entry_price ? ` @ ${(d.entry_price as number).toFixed(2)}` : "";
    return `${d.direction} ${d.symbol} x${d.quantity || 1}${price}`;
  }
  if (d.event_type) {
    return `${d.event_type}${d.details ? `: ${summarizeValue(d.details)}` : ""}`;
  }
  if (d.event) {
    return String(d.event).replace(/_/g, " ");
  }
  if (d.message) {
    return String(d.message);
  }

  // Generic: convert to key=value pairs, skip nulls and internal fields
  const parts: string[] = [];
  for (const [k, v] of Object.entries(d)) {
    if (v === null || v === undefined || k === "type") continue;
    parts.push(`${k}=${summarizeValue(v)}`);
    if (parts.length >= 4) break;
  }
  return parts.join(", ") || "—";
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
