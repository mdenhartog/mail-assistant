import { useId } from "react";
import type { ReactElement } from "react";

import type { CategoryItem } from "@/api/categories/categories.types";
import { HELP } from "@/features/categories/copy";

export interface KindFieldProps {
  value: CategoryItem["kind"];
  onChange: (kind: CategoryItem["kind"]) => void;
}

const OPTIONS = [
  { kind: "topic", label: "Topic", help: HELP.topic },
  { kind: "extra", label: "Extra label", help: HELP.extra },
] as const;

/** Topic or extra label as two radio buttons, each with its help text. */
export function KindField({ value, onChange }: KindFieldProps): ReactElement {
  const id = useId();
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="font-semibold text-text">Kind</legend>
      {OPTIONS.map((option) => (
        <div className="flex items-start gap-3" key={option.kind}>
          <input
            aria-describedby={`${id}-${option.kind}`}
            checked={value === option.kind}
            className="mt-2.5 size-6 flex-none cursor-pointer"
            id={`${id}-radio-${option.kind}`}
            name={`${id}-kind`}
            onChange={() => {
              onChange(option.kind);
            }}
            type="radio"
          />
          <div className="flex min-w-0 flex-col">
            <label className="flex min-h-11 cursor-pointer items-center font-semibold text-text" htmlFor={`${id}-radio-${option.kind}`}>
              {option.label}
            </label>
            <p className="text-sm text-text-muted" id={`${id}-${option.kind}`}>
              {option.help}
            </p>
          </div>
        </div>
      ))}
    </fieldset>
  );
}
