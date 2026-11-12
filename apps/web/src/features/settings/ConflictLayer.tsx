import type { FunctionComponent } from "react";

import type { ConflictState, FieldKey, SettingsValues } from "@/features/settings/useSettings";

interface ConflictLayerProps {
  conflict: ConflictState | null;
  values: SettingsValues;
  setValue: (field: FieldKey, value: string) => void;
}

/**
 * Slot of U-web-settings-35 (conflict banner, Use mine, Keep Telegram's). Empty in this unit.
 * On a 409 the form already holds `conflict.current.values`; `conflict.mine` is what the user had typed.
 */
export const ConflictLayer: FunctionComponent<ConflictLayerProps> = () => null;
