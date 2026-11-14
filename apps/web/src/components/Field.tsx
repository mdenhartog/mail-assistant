import { useId } from "react";
import type { ReactElement, ReactNode } from "react";

/** What a control inside a Field must receive to be labelled, described and flagged. */
interface FieldControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface FieldProps {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  children: (control: FieldControlProps) => ReactNode;
}

/**
 * Label, hint, control and error. The control comes from the render prop so it gets the ids;
 * `aria-invalid` is set only when there is an error, and the error is announced as an alert.
 *
 * @example
 * <Field label="Time zone" hint="Type a city.">{(control) => <input {...control} />}</Field>
 */
export function Field({ label, hint, error, children }: FieldProps): ReactElement {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1">
      <label className="font-semibold text-text" htmlFor={id}>
        {label}
      </label>
      {hint ? (
        <p className="text-sm text-text-muted" id={hintId}>
          {hint}
        </p>
      ) : null}
      <div className="mt-1">
        {children({
          id,
          "aria-describedby": describedBy || undefined,
          "aria-invalid": error ? true : undefined,
        })}
      </div>
      {error ? (
        <p className="mt-1 flex items-start gap-2 text-danger" id={errorId} role="alert">
          <span
            aria-hidden="true"
            className="mt-0.5 inline-grid size-5 flex-none place-items-center rounded-full bg-danger text-sm font-bold text-surface-raised"
          >
            !
          </span>
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}
