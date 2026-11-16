import type { ReactElement } from "react";

export interface ProgressProps {
  /** Names the bar for a screen reader, for example "Mails sorted". */
  label: string;
  value: number;
  max: number;
}

/**
 * Determinate progress bar. The numbers are read out as "340 of 2000"; the fill is only a picture.
 *
 * @example
 * <Progress label="Mails sorted" max={2000} value={340} />
 */
export function Progress({ label, value, max }: ProgressProps): ReactElement {
  const total = Math.max(0, max);
  const done = Math.min(Math.max(0, value), total);
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div
      aria-label={label}
      aria-valuemax={total}
      aria-valuemin={0}
      aria-valuenow={done}
      aria-valuetext={`${String(done)} of ${String(total)}`}
      className="h-3 w-full overflow-hidden rounded-pill border border-border bg-surface-raised"
      role="progressbar"
    >
      <div className="h-full bg-primary motion-safe:transition-all motion-safe:duration-200" style={{ width: `${String(percent)}%` }} />
    </div>
  );
}
