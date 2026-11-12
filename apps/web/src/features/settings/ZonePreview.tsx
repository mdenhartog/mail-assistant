import type { ReactElement } from "react";

import type { SettingsValues } from "@/features/settings/useSettings";

/** Skeleton. */
export function ZonePreview({
  savedZone,
  values,
}: {
  savedZone: string;
  values: SettingsValues;
  now: () => Date;
}): ReactElement | null {
  return savedZone === values.timeZone && savedZone === "" ? <p /> : null;
}
