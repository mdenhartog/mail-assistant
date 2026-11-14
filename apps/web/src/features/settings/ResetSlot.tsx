import { useState } from "react";
import type { ReactElement } from "react";

import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";

interface ResetSlotProps {
  /** A save or a reset is running: the button stays where it is but does nothing. */
  busy: boolean;
  /** Marco confirmed: replace the stored values with the defaults. */
  onReset: () => void;
}

const LABEL = "Reset to defaults";

// ASSUMPTION: the defaults named in the dialog are the DEFAULT_POLICY values of the schedule policy
// (Europe/Amsterdam, quiet 23:00 to 07:00, overview 18:00, reminders 09:00); the API stores the real ones.
const DEFAULTS = "Time zone Europe/Amsterdam, quiet hours 23:00 to 07:00, daily overview 18:00, reminders 09:00";

/**
 * "Reset to defaults" and the question that comes before it. Nothing is sent until the destructive
 * button of the dialog is pressed; the safe button, Escape and a closed dialog send nothing.
 *
 * @example
 * <ResetSlot busy={flow.saving} onReset={flow.reset} />
 */
export function ResetSlot({ busy, onReset }: ResetSlotProps): ReactElement {
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
      >
        <p>
          {`This replaces your saved settings with: ${DEFAULTS}. The time zone is reset too. It takes effect at once for new alerts.`}
        </p>
      </ConfirmDialog>
    </>
  );
}
