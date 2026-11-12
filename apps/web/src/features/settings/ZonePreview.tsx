import type { ReactElement } from "react";

import { cityOf } from "@/features/settings/liveTime";
import type { SettingsValues } from "@/features/settings/useSettings";
import { convertClock } from "@/features/settings/zoneMath";

interface ZonePreviewProps {
  /** The stored zone. */
  savedZone: string;
  values: SettingsValues;
  now: () => Date;
}

/**
 * Shown while the chosen zone differs from the stored one: the quiet hours in the new zone and
 * the same moments in the stored zone. The clock times in the form do not change.
 *
 * @example
 * <ZonePreview now={() => new Date()} savedZone="Europe/Amsterdam" values={values} />
 */
export function ZonePreview({ savedZone, values, now }: ZonePreviewProps): ReactElement | null {
  if (values.timeZone === savedZone) {
    return null;
  }
  const at = now();
  const start = convertClock(values.quietStart, values.timeZone, savedZone, at);
  const end = convertClock(values.quietEnd, values.timeZone, savedZone, at);
  if (!start || !end) {
    return null;
  }
  return (
    <p className="text-sm text-text">
      {`Quiet hours will now be ${values.quietStart} to ${values.quietEnd} ${cityOf(values.timeZone)} time ` +
        `(${start.clock}${start.dayNote} to ${end.clock}${end.dayNote} ${cityOf(savedZone)} time).`}
    </p>
  );
}
