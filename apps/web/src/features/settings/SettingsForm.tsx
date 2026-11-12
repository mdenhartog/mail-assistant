import { useEffect, useRef } from "react";
import type { ReactElement, RefObject, SyntheticEvent } from "react";

import { Banner } from "@/components/Banner";
import { Button } from "@/components/Button";
import { ConflictLayer } from "@/features/settings/ConflictLayer";
import { SaveFeedback } from "@/features/settings/SaveFeedback";
import { SettingsFields } from "@/features/settings/SettingsFields";
import type { Settings } from "@/features/settings/useSettings";
import { useSettingsFlow } from "@/features/settings/useSettingsFlow";
import type { SaveFailure } from "@/features/settings/useSettingsFlow";

/** Moves focus to the first invalid control in DOM order each time `stamp` changes to a non-zero value. */
function useFocusFirstInvalid(form: RefObject<HTMLFormElement | null>, stamp: number): void {
  useEffect(() => {
    if (stamp > 0) {
      form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [form, stamp]);
}

function FailureBanner({ failure, onRetry }: { failure: SaveFailure; onRetry: () => void }): ReactElement {
  if (failure === "refused") {
    return (
      <Banner kind="danger" title="Some values were not accepted.">
        Check the times and the time zone, then try again.
      </Banner>
    );
  }
  return (
    <Banner action={{ label: "Try again", onClick: onRetry }} kind="danger" title="Could not save. Nothing was changed.">
      Check your connection and try again.
    </Banner>
  );
}

/**
 * The loaded settings as a form: load happened in the page, this validates (the server's 422 per
 * field) and saves. The three slot files fill the gaps for later units: `ZoneField` (inside the
 * fields), `ConflictLayer` above them and `SaveFeedback` below them.
 */
export function SettingsForm({ settings }: { settings: Settings }): ReactElement {
  const flow = useSettingsFlow(settings);
  const form = useRef<HTMLFormElement>(null);
  useFocusFirstInvalid(form, flow.errorStamp);
  const handleSubmit = (event: SyntheticEvent): void => {
    event.preventDefault();
    flow.submit();
  };
  return (
    <form className="mt-6 flex flex-col gap-6" noValidate onSubmit={handleSubmit} ref={form}>
      <ConflictLayer conflict={flow.conflict} setValue={flow.setField} values={flow.draft} />
      <SettingsFields errors={flow.errors} readOnly={flow.saving} setField={flow.setField} values={flow.draft} />
      <SaveFeedback saved={flow.saved} settings={settings} values={flow.draft} />
      {flow.failure ? <FailureBanner failure={flow.failure} onRetry={flow.submit} /> : null}
      <div>
        <Button disabled={!flow.dirty} loading={flow.saving} type="submit" variant="primary">
          Save changes
        </Button>
      </div>
      <p className="sr-only" role="status">
        {flow.saving ? "Saving your settings." : ""}
      </p>
    </form>
  );
}
