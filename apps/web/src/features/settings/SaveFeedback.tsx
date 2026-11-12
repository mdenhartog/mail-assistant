import type { FunctionComponent, ReactElement } from "react";

import { Banner } from "@/components/Banner";
import { LastChangeLine } from "@/features/settings/LastChangeLine";
import { cityOf, clockIn } from "@/features/settings/liveTime";
import type { Settings, SettingsValues } from "@/features/settings/useSettings";
import { ZonePreview } from "@/features/settings/ZonePreview";
import { minutesPhrase } from "@/features/settings/zoneMath";
import { useSession } from "@/session/useSession";

interface SaveFeedbackProps {
  /** The stored copy. */
  settings: Settings;
  /** The form. */
  values: SettingsValues;
  /** The answer of the last successful save. */
  saved: Settings | null;
  /** The clock for the zone preview. Defaults to the system clock. */
  now?: () => Date;
}

function systemNow(): Date {
  return new Date();
}

/** The success banner. It asks for the session only now, to name the agent's run interval. */
function SavedBanner({ saved }: { saved: Settings }): ReactElement {
  const { data: session, isPending } = useSession();
  const zone = saved.values.timeZone;
  const at = saved.updatedAt === null ? null : clockIn(zone, new Date(saved.updatedAt));
  const notice = session ? `within ${minutesPhrase(session.noticeIntervalMinutes)}.` : "shortly.";
  return (
    <Banner kind="success" title={at === null ? "Saved." : `Saved at ${at}.`}>
      {`Quiet hours are ${saved.values.quietStart} to ${saved.values.quietEnd} (${cityOf(zone)} time).`}
      {isPending ? "" : ` A message with an Undo button follows on Telegram ${notice}`}
    </Banner>
  );
}

/**
 * Everything under the fields that tells what is true: the permanent zone sentence, the preview of a
 * zone change, the last-change line and, after a save, the success banner (the only live announcement).
 *
 * @example
 * <SaveFeedback saved={null} settings={settings} values={draft} />
 */
export const SaveFeedback: FunctionComponent<SaveFeedbackProps> = ({ settings, values, saved, now = systemNow }) => (
  <div className="flex flex-col gap-2">
    <p className="text-sm text-text-muted">Quiet hours, the overview and reminders follow this time zone.</p>
    <ZonePreview now={now} savedZone={settings.values.timeZone} values={values} />
    <LastChangeLine settings={settings} />
    {saved ? <SavedBanner saved={saved} /> : null}
  </div>
);
