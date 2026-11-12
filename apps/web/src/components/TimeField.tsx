import { useState } from "react";
import type { ChangeEvent, ReactElement } from "react";

export interface TimeFieldProps {
  id: string;
  /** 24-hour "HH:MM", shown exactly as stored. */
  value: string;
  onChange: (value: string) => void;
  readOnly?: boolean;
  "aria-describedby"?: string | undefined;
  "aria-invalid"?: true | undefined;
  /** Forces the native or the select control; by default the browser is asked. */
  native?: boolean;
}

const CONTROL =
  "min-h-11 min-w-0 max-w-full rounded-control border border-border bg-surface-raised px-3 text-text tabular-nums " +
  "aria-invalid:border-2 aria-invalid:border-danger read-only:opacity-80";

const GRID: string[] = Array.from({ length: 96 }, (_, i) => {
  const hours = String(Math.floor(i / 4)).padStart(2, "0");
  const minutes = String((i % 4) * 15).padStart(2, "0");
  return `${hours}:${minutes}`;
});

function supportsTimeInput(): boolean {
  const probe = document.createElement("input");
  probe.type = "time";
  return probe.type === "time";
}

/** The 15-minute grid plus the stored value when it is not on the grid, so it is never rounded. */
function optionsFor(value: string): string[] {
  return value === "" || GRID.includes(value) ? GRID : [...GRID, value].sort();
}

/**
 * Time of day as a native `input type=time` (step 60), or a stepped select where the browser has
 * none. The stored value is echoed in 24-hour text because a phone may display 12-hour time.
 *
 * @example
 * <Field label="From">{(control) => <TimeField {...control} onChange={set} value="22:10" />}</Field>
 */
export function TimeField({ value, onChange, readOnly = false, native, ...aria }: TimeFieldProps): ReactElement {
  const [detected] = useState(supportsTimeInput);
  const useNative = native ?? detected;
  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>): void => {
    if (!readOnly) {
      onChange(event.target.value);
    }
  };
  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-x-3 gap-y-1">
      {useNative ? (
        <input
          {...aria}
          className={CONTROL}
          onChange={handleChange}
          readOnly={readOnly}
          step={60}
          type="time"
          value={value}
        />
      ) : (
        <select {...aria} aria-readonly={readOnly || undefined} className={CONTROL} onChange={handleChange} value={value}>
          {optionsFor(value).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      )}
      <span className="text-sm text-text-muted tabular-nums">= {value}</span>
    </div>
  );
}
