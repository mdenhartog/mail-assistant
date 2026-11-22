import { useId } from "react";
import type { ReactElement } from "react";

import { HELP } from "@/features/categories/copy";
import { MAX_SENDERS, parseSenders } from "@/features/categories/senders";
import type { SenderError } from "@/features/categories/senders";

export interface SendersFieldProps {
  value: string;
  errors: readonly SenderError[];
  onChange: (value: string) => void;
}

/**
 * The sender entries of a category as one entry per line, with the help, a live count and the errors per line.
 * The textarea is described by the help, the count and the errors, so a screen reader hears all of them.
 */
export function SendersField({ value, errors, onChange }: SendersFieldProps): ReactElement {
  const id = useId();
  const ids = { help: `${id}-help`, format: `${id}-format`, count: `${id}-count`, errors: `${id}-errors` };
  const invalid = errors.length > 0;
  const describedBy = [ids.help, ids.format, ids.count, invalid ? ids.errors : null].filter(Boolean).join(" ");
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
