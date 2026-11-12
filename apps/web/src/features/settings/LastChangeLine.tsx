import type { ReactElement } from "react";

import { clockIn } from "@/features/settings/liveTime";
import type { Settings } from "@/features/settings/useSettings";

/**
 * "Last changed from Telegram at 14:02" (time in the stored zone) or, before any change, the default notice.
 *
 * @example
 * <LastChangeLine settings={settings} />
 */
export function LastChangeLine({ settings }: { settings: Settings }): ReactElement {
  const { updatedAt, updatedVia, version, values } = settings;
  const clock = updatedAt === null ? null : clockIn(values.timeZone, new Date(updatedAt));
  if (version === 0 || updatedAt === null || updatedVia === null || clock === null) {
    return <p className="text-sm text-text-muted">Using the default settings.</p>;
  }
  return (
    <p className="text-sm text-text-muted">
      {`Last changed from ${updatedVia === "telegram" ? "Telegram" : "the web"} at `}
      <time dateTime={updatedAt}>{clock}</time>
    </p>
  );
}
