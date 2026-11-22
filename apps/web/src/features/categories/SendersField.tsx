import { useId } from "react";
import type { ReactElement } from "react";

import { HELP, SKIPPED_NOTE, skippedText } from "@/features/categories/copy";
import { MAX_SENDERS, entryKey, parseSenders } from "@/features/categories/senders";
import type { SenderError } from "@/features/categories/senders";

export interface SendersFieldProps {
  value: string;
  errors: readonly SenderError[];
  /** The stored entries Gmail could not confirm, with how often (see `Row.skipped`). */
  skipped: ReadonlyMap<string, number>;
  onChange: (value: string) => void;
}

interface SkippedEntry {
  entry: string;
  count: number;
}

/** The entries now written in the text that have a stored count above 0; an edited or added entry has none. */
function skippedEntries(text: string, skipped: ReadonlyMap<string, number>): SkippedEntry[] {
  return parseSenders(text).entries.flatMap(({ entry }) => {
    const count = skipped.get(entryKey(entry)) ?? 0;
    return count > 0 ? [{ entry, count }] : [];
  });
}

/** Plain text per entry, then one note; part of the field's description. Nothing renders when no entry has a count. */
function SkippedList({ id, items }: { id: string; items: readonly SkippedEntry[] }): ReactElement | null {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-1 text-sm text-text-muted" id={id}>
      <ul className="flex flex-col gap-1">
        {items.map(({ entry, count }) => (
          <li className="flex flex-col wrap-anywhere" key={entryKey(entry)}>
            <span className="font-mono text-text">{entry}</span>
            <span>{skippedText(count)}</span>
          </li>
        ))}
      </ul>
      <p>{SKIPPED_NOTE}</p>
    </div>
  );
}

/**
 * The sender entries of a category as one entry per line, with the help, a live count and the errors per line.
 * The textarea is described by the help, the count and the errors, so a screen reader hears all of them.
 */
export function SendersField({ value, errors, skipped, onChange }: SendersFieldProps): ReactElement {
  const id = useId();
  const ids = { help: `${id}-help`, format: `${id}-format`, count: `${id}-count`, errors: `${id}-errors`, skipped: `${id}-skipped` };
  const invalid = errors.length > 0;
  const notApplied = skippedEntries(value, skipped);
  const describedBy = [ids.help, ids.format, ids.count, notApplied.length > 0 ? ids.skipped : null, invalid ? ids.errors : null].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1">
      <label className="font-semibold text-text" htmlFor={id}>
        Senders
      </label>
      <p className="text-sm text-text-muted" id={ids.help}>
        {HELP.senders}
      </p>
      <p className="text-sm text-text-muted" id={ids.format}>
        {HELP.sendersFormat}
      </p>
      <textarea
        aria-describedby={describedBy}
        aria-invalid={invalid ? true : undefined}
        autoCapitalize="off"
        autoCorrect="off"
        className="field-sizing-content mt-1 min-h-24 w-full min-w-0 max-w-full rounded-control border border-border bg-surface-raised px-3 py-2 font-mono text-text aria-invalid:border-2 aria-invalid:border-danger"
        data-field="senders"
        id={id}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        rows={6}
        spellCheck={false}
        value={value}
      />
      <p className="text-sm text-text-muted" id={ids.count}>
        {`${String(parseSenders(value).entries.length)} of ${String(MAX_SENDERS)}`}
      </p>
      <SkippedList id={ids.skipped} items={notApplied} />
      {invalid ? (
        <div id={ids.errors} role="alert">
          <ul className="flex flex-col gap-1">
            {errors.map((error) => (
              <li className="flex items-start gap-2 text-danger" key={`${String(error.line)}:${error.text}`}>
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-grid size-5 flex-none place-items-center rounded-full bg-danger text-sm font-bold text-surface-raised"
                >
                  !
                </span>
                <span className="wrap-anywhere">{error.line === null ? error.text : `Line ${String(error.line)}: ${error.text}`}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
