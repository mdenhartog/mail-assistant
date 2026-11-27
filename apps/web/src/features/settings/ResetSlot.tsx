import { useState } from "react";
import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { valueText } from "@/features/settings/cleanupText";
import type { Ranges } from "@/features/settings/useSettings";

interface ResetSlotProps {
  /** A save or a reset is running: the button stays where it is but does nothing. */
  busy: boolean;
  /** Marco confirmed: replace the stored values with the defaults. */
  onReset: () => void;
  /** The defaults of the label cleanup numbers, as the api sent them. */
  ranges: Ranges;
}

const LABEL = "Reset to defaults";

// ASSUMPTION: the schedule defaults named in the dialog are the DEFAULT_POLICY values of the schedule policy
// (Europe/Amsterdam, quiet 23:00 to 07:00, overview 18:00, reminders 09:00); the API stores the real ones.
// The label cleanup defaults come from the ranges the API sent.
const SCHEDULE_DEFAULTS = "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00";

function defaultsText(ranges: Ranges): string {
  const cleanup = [
    `label cleanup waiting time ${valueText("waitingMinutes", ranges.waitingMinutes.default)}`,
    `protection ${valueText("protectionDays", ranges.protectionDays.default)}`,
    `retention ${valueText("retentionDays", ranges.retentionDays.default)}`,
  ];
  return `${SCHEDULE_DEFAULTS}, ${cleanup.join(", ")}`;
}

/**
 * "Reset to defaults" and the question that comes before it. Nothing is sent until the destructive
 * button of the dialog is pressed; the safe button, Escape and a closed dialog send nothing.
 *
 * @example
 * <ResetSlot busy={flow.saving} onReset={flow.reset} ranges={settings.ranges} />
 */
export function ResetSlot({ busy, onReset, ranges }: ResetSlotProps): ReactElement {
  const [asking, setAsking] = useState(false);
  const close = (): void => {
    setAsking(false);
  };
  return (
    <>
      <Button
        loading={busy}
        loadingLabel={LABEL}
        onClick={() => {
          setAsking(true);
        }}
        variant="secondary"
      >
        {LABEL}
      </Button>
      <ConfirmDialog
        cancelLabel="Keep my settings"
        confirmLabel="Replace my settings with defaults"
        onCancel={close}
        onConfirm={() => {
          close();
          onReset();
        }}
        open={asking}
        title={`${LABEL}?`}
        tone="danger"
      >
        <p>
          {`This replaces your saved settings with: ${defaultsText(ranges)}. The time zone is reset too. It takes effect at once for new alerts.`}
        </p>
      </ConfirmDialog>
    </>
  );
}
