import { useState } from "react";

import { FIELD_KEYS } from "@/features/settings/useSettings";
import type { ConflictState, FieldKey, Settings, SettingsValues } from "@/features/settings/useSettings";

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

const LABELS: Record<FieldKey, string> = {
  timeZone: "Time zone",
  quietStart: "Quiet hours from",
  quietEnd: "Quiet hours until",
  overviewAt: "Daily overview",
  remindAt: "Remind-me-later default",
};

/** "Europe/Amsterdam" becomes "Amsterdam"; anything else is shown as it is. */
function placeName(zone: string): string {
  return (zone.split("/").pop() ?? zone).replaceAll("_", " ");
}

/** The wall-clock time of the other change in the zone it is stored in, or null when it cannot be told. */
function clockTime(current: Settings): string | null {
  if (current.updatedAt === null) {
    return null;
  }
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: current.values.timeZone,
    }).format(new Date(current.updatedAt));
  } catch {
    return null;
  }
}

function titleOf(current: Settings): string {
  const source = current.updatedVia === "web" ? "from the web" : "in Telegram";
  const time = clockTime(current);
  return time === null
    ? `Settings changed ${source}.`
    : `Settings changed ${source} at ${time} (${placeName(current.values.timeZone)} time).`;
}

/** Fields the user edited and that now differ from what is stored; typing what Telegram has is no conflict. */
function conflictingFields(conflict: ConflictState): FieldKey[] {
  return FIELD_KEYS.filter(
    (field) => conflict.mine[field] !== conflict.base[field] && conflict.mine[field] !== conflict.current.values[field],
  );
}

/** The user dismissed a mark by keeping Telegram's value; dismissals belong to one conflict only. */
function useDismissed(conflict: ConflictState | null): [FieldKey[], (field: FieldKey) => void] {
  const [seen, setSeen] = useState(conflict);
  const [dismissed, setDismissed] = useState<FieldKey[]>([]);
  if (seen !== conflict) {
    setSeen(conflict);
    setDismissed([]);
  }
  return [
    dismissed,
    (field) => {
      setDismissed((list) => [...list, field]);
    },
  ];
}

function markOf(field: FieldKey, conflict: ConflictState, values: SettingsValues): ConflictMark | null {
  const mine = conflict.mine[field];
  const theirs = conflict.current.values[field];
  const shown = values[field];
  // A third value typed afterwards settles the question by itself.
  if (shown !== mine && shown !== theirs) {
    return null;
  }
  return { field, label: LABELS[field], mine, theirs, usingMine: shown === mine };
}

/**
 * What the conflict layer shows after a 409: the banner title, a mark per edited field that
 * Telegram (or another tab) changed meanwhile, and the two ways to settle each mark.
 * Nothing here saves; the choices only change the draft.
 */
export function useConflict(
  conflict: ConflictState | null,
  values: SettingsValues,
  setValue: (field: FieldKey, value: string) => void,
): ConflictView | null {
  const [dismissed, dismiss] = useDismissed(conflict);
  if (conflict === null) {
    return null;
  }
  const marks = conflictingFields(conflict)
    .filter((field) => !dismissed.includes(field))
    .map((field) => markOf(field, conflict, values))
    .filter((mark): mark is ConflictMark => mark !== null);
  return {
    title: titleOf(conflict.current),
    marks,
    useMine: (field) => {
      setValue(field, conflict.mine[field]);
    },
    keepTheirs: (field) => {
      setValue(field, conflict.current.values[field]);
      dismiss(field);
    },
  };
}
