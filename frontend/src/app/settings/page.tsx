"use client";

import { useState, useEffect } from "react";
import { getSettings, updateSettings, getSettingsAudit } from "@/lib/api";
import { setDisplayTimezone } from "@/lib/timezone";
import { formatDateTime } from "@/lib/timezone";
import Tooltip from "@/components/ui/Tooltip";

const TIMEZONE_OPTIONS = [
  { value: "America/New_York", label: "Eastern (ET)" },
  { value: "America/Chicago", label: "Central (CT)" },
  { value: "America/Denver", label: "Mountain (MT)" },
  { value: "America/Los_Angeles", label: "Pacific (PT)" },
  { value: "UTC", label: "UTC" },
];

const MODEL_OPTIONS = [
  { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6 (fast/cheap)" },
  { value: "claude-opus-4-6", label: "Claude Opus 4.6 (accurate/costly)" },
  { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5 (fastest/cheapest)" },
];

interface SettingMeta {
  value: string;
  default: string;
  type: string;
  label: string;
  tooltip: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, SettingMeta>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [audits, setAudits] = useState<Array<{
    id: number; timestamp: string; key: string; label: string;
    old_value: string | null; new_value: string; changed_by: string;
  }>>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ success: boolean; message: string } | null>(null);

  useEffect(() => {
    Promise.all([
      getSettings().then((res) => {
        setSettings(res.settings);
        const vals: Record<string, string> = {};
        for (const [key, meta] of Object.entries(res.settings)) {
          vals[key] = meta.value;
        }
        setValues(vals);
      }),
      getSettingsAudit(20).then((res) => setAudits(res.audits)),
    ]).finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveResult(null);
    try {
      const changed: Record<string, string> = {};
      for (const [key, val] of Object.entries(values)) {
        if (settings[key] && val !== settings[key].value) {
          changed[key] = val;
        }
      }

      if (Object.keys(changed).length === 0) {
        setSaveResult({ success: true, message: "No changes to save" });
        setSaving(false);
        return;
      }

      const res = await updateSettings(changed);

      // Update timezone if it changed
      if (changed.display_timezone) {
        setDisplayTimezone(changed.display_timezone);
      }

      // Refresh settings and audit
      const [settingsRes, auditRes] = await Promise.all([
        getSettings(),
        getSettingsAudit(20),
      ]);
      setSettings(settingsRes.settings);
      const newVals: Record<string, string> = {};
      for (const [key, meta] of Object.entries(settingsRes.settings)) {
        newVals[key] = meta.value;
      }
      setValues(newVals);
      setAudits(auditRes.audits);

      setSaveResult({ success: true, message: `Updated ${res.updated.length} setting(s)` });
    } catch (e) {
      setSaveResult({ success: false, message: e instanceof Error ? e.message : "Save failed" });
    } finally {
      setSaving(false);
    }
  };

  const updateValue = (key: string, val: string) => {
    setValues((prev) => ({ ...prev, [key]: val }));
    setSaveResult(null);
  };

  if (loading) return <div className="p-4 text-gray-500">Loading settings...</div>;

  const renderInput = (key: string) => {
    const meta = settings[key];
    if (!meta) return null;

    // Special rendering for dropdowns
    if (key === "display_timezone") {
      return (
        <select
          value={values[key]}
          onChange={(e) => updateValue(key, e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
        >
          {TIMEZONE_OPTIONS.map((tz) => (
            <option key={tz.value} value={tz.value}>{tz.label}</option>
          ))}
        </select>
      );
    }

    if (key === "news_analysis_model") {
      return (
        <select
          value={values[key]}
          onChange={(e) => updateValue(key, e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
        >
          {MODEL_OPTIONS.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      );
    }

    // Number inputs
    const inputType = meta.type === "float" ? "number" : meta.type === "int" ? "number" : "text";
    const step = meta.type === "float" ? "0.01" : "1";

    return (
      <input
        type={inputType}
        step={step}
        value={values[key]}
        onChange={(e) => updateValue(key, e.target.value)}
        className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
      />
    );
  };

  const renderSettingRow = (key: string) => {
    const meta = settings[key];
    if (!meta) return null;
    const isChanged = values[key] !== meta.value;

    return (
      <div key={key} className="flex items-center py-1.5 gap-2">
        <div className="flex items-center gap-1 text-xs text-gray-400 shrink-0 w-56">
          {meta.label}
          <Tooltip text={meta.tooltip} />
        </div>
        <div className="w-48 shrink-0">
          {renderInput(key)}
        </div>
        <span className={`text-yellow-400 text-xs w-3 ${isChanged ? "" : "invisible"}`}>*</span>
      </div>
    );
  };

  return (
    <div className="p-4 max-w-3xl">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold">Settings</h1>
        <div className="flex items-center gap-3">
          {saveResult && (
            <span className={`text-xs ${saveResult.success ? "text-green-400" : "text-red-400"}`}>
              {saveResult.message}
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving || Object.entries(values).every(([key, val]) => settings[key]?.value === val)}
            className="px-4 py-1.5 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>

      {/* Display */}
      <div className="bg-gray-900 rounded p-4 mb-4">
        <h2 className="text-sm font-bold mb-3">Display</h2>
        {renderSettingRow("display_timezone")}
      </div>

      {/* Trading Parameters */}
      <div className="bg-gray-900 rounded p-4 mb-4">
        <h2 className="text-sm font-bold mb-3">Trading Parameters</h2>
        {renderSettingRow("max_position_size")}
        {renderSettingRow("daily_loss_limit")}
        {renderSettingRow("default_stop_ticks")}
        {renderSettingRow("default_target_ticks")}
      </div>

      {/* Engine Parameters */}
      <div className="bg-gray-900 rounded p-4 mb-4">
        <h2 className="text-sm font-bold mb-3">Engine Parameters</h2>
        {renderSettingRow("strategy_eval_interval")}
        {renderSettingRow("reconciliation_interval")}
        {renderSettingRow("news_analysis_model")}
      </div>

      {/* Settings Audit Trail */}
      <div className="bg-gray-900 rounded p-4">
        <h2 className="text-sm font-bold mb-3">Change History</h2>
        {audits.length === 0 ? (
          <div className="text-xs text-gray-600">No changes recorded yet</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1">Time</th>
                <th className="text-left">Setting</th>
                <th className="text-left">Old</th>
                <th className="text-left">New</th>
              </tr>
            </thead>
            <tbody>
              {audits.map((a) => (
                <tr key={a.id} className="border-b border-gray-800">
                  <td className="py-1 text-gray-500">{formatDateTime(a.timestamp)}</td>
                  <td>{a.label}</td>
                  <td className="text-red-400">{a.old_value ?? "—"}</td>
                  <td className="text-green-400">{a.new_value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
