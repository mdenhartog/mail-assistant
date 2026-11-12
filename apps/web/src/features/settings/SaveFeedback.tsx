import type { FunctionComponent } from "react";

import type { Settings, SettingsValues } from "@/features/settings/useSettings";

interface SaveFeedbackProps {
  settings: Settings;
  values: SettingsValues;
  saved: Settings | null;
}

/**
 * Slot of U-web-settings-34 (last-change line, saved banner, zone preview). Empty in this unit.
 * `settings` is the stored copy, `values` the form, `saved` the answer of the last successful save.
 */
export const SaveFeedback: FunctionComponent<SaveFeedbackProps> = () => null;
