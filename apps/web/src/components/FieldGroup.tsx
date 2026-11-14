import { useId } from "react";
import type { ReactElement, ReactNode } from "react";

/** What every control in the group must receive to be described and flagged by the group. */
interface GroupControlProps {
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

export interface FieldGroupProps {
  legend: string;
  hint?: string | undefined;
  error?: string | undefined;
  children: (control: GroupControlProps) => ReactNode;
}

/**
 * A fieldset with a legend, one hint and one error for several controls (for example From and
 * Until). Each control is given the description and the invalid flag; each keeps its own label.
 *
 * @example
 * <FieldGroup legend="Quiet hours" hint="Alerts wait until it ends.">{(control) => <input {...control} />}</FieldGroup>
 */
export function FieldGroup({ legend, hint, error, children }: FieldGroupProps): ReactElement {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  return (
    <fieldset className="flex min-w-0 flex-col gap-1">
      <legend className="font-semibold text-text">{legend}</legend>
      {hint ? (
        <p className="text-sm text-text-muted" id={hintId}>
          {hint}
        </p>
      ) : null}
      <div className="mt-1">
        {children({ "aria-describedby": describedBy || undefined, "aria-invalid": error ? true : undefined })}
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
    </fieldset>
  );
}
