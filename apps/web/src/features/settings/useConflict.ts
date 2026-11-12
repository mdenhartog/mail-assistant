import type { FieldKey } from "@/features/settings/useSettings";

/** One edited field whose stored value moved on while the user typed. */
export interface ConflictMark {
  field: FieldKey;
  label: string;
  mine: string;
  theirs: string;
  usingMine: boolean;
}

export interface ConflictView {
  /** Source and time of the other change, ready for the banner title. */
  title: string;
  marks: ConflictMark[];
  useMine: (field: FieldKey) => void;
  keepTheirs: (field: FieldKey) => void;
}

/** Skeleton of U-web-settings-35. */
export function useConflict(): ConflictView | null {
  return null;
}
