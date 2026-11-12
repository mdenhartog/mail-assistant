import type { ReactElement } from "react";

import type { Settings } from "@/features/settings/useSettings";

/** Skeleton. */
export function LastChangeLine({ settings }: { settings: Settings }): ReactElement | null {
  return settings.version < 0 ? <p /> : null;
}
