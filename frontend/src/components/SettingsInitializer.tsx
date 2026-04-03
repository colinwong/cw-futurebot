"use client";

import { useEffect } from "react";
import { getSettings } from "@/lib/api";
import { setDisplayTimezone } from "@/lib/timezone";

export default function SettingsInitializer() {
  useEffect(() => {
    getSettings()
      .then((res) => {
        const tz = res.settings.display_timezone?.value;
        if (tz) setDisplayTimezone(tz);
      })
      .catch(() => {});
  }, []);

  return null;
}
