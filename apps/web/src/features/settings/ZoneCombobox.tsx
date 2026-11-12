import { useId } from "react";
import type { ReactElement } from "react";

import { cityOf, clockIn } from "@/features/settings/liveTime";
import { useZoneCombobox } from "@/features/settings/useZoneCombobox";
import { ZoneHints } from "@/features/settings/ZoneHints";
import { ZoneStatus } from "@/features/settings/ZoneStatus";
import { ZoneOptions } from "@/features/settings/ZoneOptions";

/** What the Field gives its control so it is labelled, described and flagged. */
interface ZoneControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface ZoneComboboxProps {
  control: ZoneControlProps;
  /** The zone now in the form. */
  value: string;
  onChange: (zone: string) => void;
  readOnly: boolean;
  /** The zone as stored; the second Escape puts it back. */
  savedValue: string;
  /** The clock for every local time shown. */
  now: () => Date;
}

const CONTROL =
  "min-h-11 w-full min-w-0 rounded-control border border-border bg-surface-raised px-3 text-text " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

const INPUT_ATTRIBUTES = {
  autoCapitalize: "none",
  autoComplete: "off",
  maxLength: 64,
  spellCheck: false,
  type: "text",
} as const;

function liveSentence(zone: string, at: Date): string {
  const clock = clockIn(zone, at);
  return clock === null ? "" : `In ${cityOf(zone)} it is ${clock} right now.`;
}

function countWords(count: number): string {
  return `${String(count)} ${count === 1 ? "place" : "places"} found`;
}

/**
 * An ARIA 1.2 combobox with list autocomplete for the time zone. Typing looks places up after a
 * pause; each option shows the local time there. Focus never leaves the input: the active option is
 * named by `aria-activedescendant`.
 *
 * @example
 * <ZoneCombobox control={control} now={() => new Date()} onChange={set} readOnly={false} savedValue="Europe/Amsterdam" value="Europe/Amsterdam" />
 */
export function ZoneCombobox(props: ZoneComboboxProps): ReactElement {
  const { control, value, readOnly, savedValue, now } = props;
  const listId = useId();
  const hintId = useId();
  const model = useZoneCombobox(props);
  const { state, view } = model;
  const at = now();
  const describedBy = [control["aria-describedby"], view.noMatch || view.lookupFailed ? hintId : undefined].filter(Boolean).join(" ");

  return (
    <div className="flex flex-col gap-2">
      <div className="relative">
        <input
          {...control}
          {...INPUT_ATTRIBUTES}
          aria-activedescendant={view.activeIndex >= 0 ? `${listId}-option-${String(view.activeIndex)}` : undefined}
          aria-autocomplete="list"
          aria-controls={listId}
          aria-describedby={describedBy || undefined}
          aria-expanded={view.expanded}
          className={CONTROL}
          onBlur={model.settle}
          onChange={(event) => {
            model.type(event.target.value);
          }}
          onFocus={(event) => {
            event.currentTarget.select();
          }}
          onKeyDown={model.keyDown}
          readOnly={readOnly}
          role="combobox"
          value={state.draft ?? value}
        />
        <ZoneOptions
          activeIndex={view.activeIndex}
          at={at}
          expanded={view.expanded}
          id={listId}
          onChoose={model.choose}
          places={view.places}
          reference={value}
        />
      </div>
      <ZoneHints
        id={hintId}
        lookupFailed={view.lookupFailed}
        noMatch={view.noMatch}
        onSuggest={(text) => {
          model.suggest(text, control.id);
        }}
        suggestion={view.suggestion}
        typed={view.typed}
      />
      <ZoneStatus
        announcement={view.expanded ? countWords(view.places.length) : ""}
        live={liveSentence(state.preview ?? value, at)}
        savedValue={savedValue}
      />
    </div>
  );
}
