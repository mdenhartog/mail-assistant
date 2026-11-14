import { useMemo } from "react";

import { FIELD_KEYS } from "@/features/settings/useSettings";
import type { SettingsValues } from "@/features/settings/useSettings";
import { useClock } from "@/pages/clock";

/** What is kept: the five typed values, the version they started from and when they were last typed (D-6). */
interface Draft {
  values: SettingsValues;
  version: number;
  savedAt: number;
}

/** The draft of one tab, removed after twelve hours. */
export interface DraftStore {
  /** The kept draft, or null when there is none, it is older than twelve hours or it is damaged. */
  read: () => Draft | null;
  write: (values: SettingsValues, version: number) => void;
  clear: () => void;
  has: () => boolean;
}

const DRAFT_KEY = "settings-draft";
const MAX_AGE_MS = 12 * 60 * 60 * 1000;

/** The tab's storage, or null where the browser refuses it (private mode, policy). The page works without. */
function area(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function valuesOf(value: unknown): SettingsValues | null {
  if (!isRecord(value) || !FIELD_KEYS.every((key) => typeof value[key] === "string")) {
    return null;
  }
  return {
    timeZone: String(value["timeZone"]),
    quietStart: String(value["quietStart"]),
    quietEnd: String(value["quietEnd"]),
    overviewAt: String(value["overviewAt"]),
    remindAt: String(value["remindAt"]),
  };
}

function parse(raw: string | null): Draft | null {
  try {
    const body: unknown = JSON.parse(raw ?? "null");
    const values = isRecord(body) ? valuesOf(body["values"]) : null;
    if (!isRecord(body) || values === null || typeof body["version"] !== "number" || typeof body["savedAt"] !== "number") {
      return null;
    }
    return { values, version: body["version"], savedAt: body["savedAt"] };
  } catch {
    return null;
  }
}

function attempt(action: (storage: Storage) => void): void {
  try {
    const storage = area();
    if (storage !== null) {
      action(storage);
    }
  } catch {
    // Storage full or refused: the draft is a convenience, so typing and saving go on without it.
  }
}

function rawDraft(): string | null {
  try {
    return area()?.getItem(DRAFT_KEY) ?? null;
  } catch {
    return null;
  }
}

function createStore(now: () => number): DraftStore {
  const clear = (): void => {
    attempt((storage) => {
      storage.removeItem(DRAFT_KEY);
    });
  };
  const read = (): Draft | null => {
    const raw = rawDraft();
    if (raw === null) {
      return null;
    }
    const draft = parse(raw);
    if (draft === null || now() - draft.savedAt >= MAX_AGE_MS) {
      clear();
      return null;
    }
    return draft;
  };
  return {
    read,
    clear,
    has: () => read() !== null,
    write: (values, version) => {
      // Picked field by field: nothing but the five values and the version can end up in storage (AC-8, W-4).
      const kept = valuesOf(values);
      attempt((storage) => {
        storage.setItem(DRAFT_KEY, JSON.stringify({ values: kept, version, savedAt: now() }));
      });
    },
  };
}

/**
 * The typed-values draft that survives a session that ended: kept in `sessionStorage`, so it belongs
 * to this tab only, and never holds a token, an address or anything but the settings fields.
 *
 * @example
 * const draft = useDraft();
 * draft.write(values, settings.version);
 */
export function useDraft(): DraftStore {
  const clock = useClock();
  return useMemo(() => createStore(() => clock.now()), [clock]);
}
