import type { ReactElement } from "react";

import { usePageTitle } from "@/pages/usePageTitle";

/** Placeholder until the settings form arrives (U-web-settings-32). */
export function SettingsPage(): ReactElement {
  usePageTitle("Settings");
  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-text">Settings</h1>
    </main>
  );
}
