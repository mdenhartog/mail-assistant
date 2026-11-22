import { useId } from "react";
import type { ReactElement } from "react";

import { HELP } from "@/features/categories/copy";

export interface NotifyFieldProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

/** The Always notify tick with its help and the note about the hourly limit. */
export function NotifyField({ checked, onChange }: NotifyFieldProps): ReactElement {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <input
        aria-describedby={`${id}-help ${id}-cap`}
        checked={checked}
        className="mt-2.5 size-6 flex-none cursor-pointer"
        id={id}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        type="checkbox"
      />
      <div className="flex min-w-0 flex-col">
        <label className="flex min-h-11 cursor-pointer items-center font-semibold text-text" htmlFor={id}>
          Always notify
        </label>
        <p className="text-sm text-text-muted" id={`${id}-help`}>
          {HELP.notify}
        </p>
        <p className="text-sm text-text-muted" id={`${id}-cap`}>
          {HELP.notifyCap}
        </p>
      </div>
    </div>
  );
}
