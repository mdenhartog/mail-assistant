import { useEffect, useRef, useState } from "react";

import { emptyFieldErrors, fieldErrors } from "@/features/settings/fieldErrors";
import type { FieldErrors } from "@/features/settings/fieldErrors";
import { useDraft } from "@/features/settings/useDraft";
import type { DraftStore } from "@/features/settings/useDraft";
import { FIELD_KEYS, classifySaveError, useResetSettings, useSaveSettings } from "@/features/settings/useSettings";
import type { ConflictState, FieldKey, SaveOutcome, Settings, SettingsValues } from "@/features/settings/useSettings";

/** A save or reset that did not store anything and has no field to blame. */
export type SaveFailure = "failed" | "refused" | "reset-failed";

/** What the last save left behind; at most one of the three is set. */
interface SaveResult {
  failure: SaveFailure | null;
  conflict: ConflictState | null;
  saved: Settings | null;
  /** The last write was a reset and it went through. */
  defaultsRestored: boolean;
}

const NO_RESULT: SaveResult = { failure: null, conflict: null, saved: null, defaultsRestored: false };

export interface SettingsFlow extends SaveResult {
  draft: SettingsValues;
  /** The typed values of a session that ended were put back and are not saved yet. */
  restored: boolean;
  dirty: boolean;
  saving: boolean;
  errors: FieldErrors;
  /** Changes on every submit that shows errors, so focus moves once per submit and not while typing. */
  errorStamp: number;
  setField: (field: FieldKey, value: string) => void;
  submit: () => void;
  /** Replaces the stored values with the defaults (the page asked and Marco confirmed). */
  reset: () => void;
}

/** What a write (save or reset) tells the flow when it ends. */
interface WriteCallbacks {
  onSuccess: (stored: Settings) => void;
  onError: (error: Error) => void;
  onSettled: () => void;
}

/** How the page starts: the stored values, or the values typed before the last session ended. */
interface Start {
  values: SettingsValues;
  result: SaveResult;
  restored: boolean;
  /** A kept draft that says nothing new (it equals what is stored); it is removed. */
  obsolete: boolean;
}

const isDirty = (values: SettingsValues, settings: Settings): boolean =>
  FIELD_KEYS.some((key) => values[key] !== settings.values[key]);

/**
 * A kept draft on the same version comes back as typed; on another version the stored values stay and
 * the draft is handed to the conflict flow as "mine", so nothing replaces a change made meanwhile.
 */
function startOf(store: DraftStore, settings: Settings): Start {
  const kept = store.read();
  const plain: Start = { values: settings.values, result: NO_RESULT, restored: false, obsolete: false };
  if (kept === null) {
    return plain;
  }
  if (!isDirty(kept.values, settings)) {
    return { ...plain, obsolete: true };
  }
  if (kept.version === settings.version) {
    return { ...plain, values: kept.values, restored: true };
  }
  const conflict = { current: settings, mine: kept.values, base: settings.values };
  return { ...plain, result: { ...NO_RESULT, conflict } };
}

/** What a save that stored nothing leaves on the page: the conflict, or the failure without a field to blame. */
function resultOf(outcome: SaveOutcome, mine: SettingsValues, settings: Settings, whenFailed: SaveFailure): SaveResult {
  if (outcome.kind === "conflict") {
    return { ...NO_RESULT, conflict: { current: outcome.current, mine, base: settings.values } };
  }
  return { ...NO_RESULT, failure: outcome.kind === "failed" ? whenFailed : "refused" };
}

/** The draft of this tab: where the page starts, and the two ways to keep it in step with the form. */
function useKeptDraft(settings: Settings): { start: Start; keep: (values: SettingsValues) => void; forget: () => void } {
  const store = useDraft();
  const [start] = useState(() => startOf(store, settings));
  useEffect(() => {
    if (start.obsolete) {
      store.clear();
    }
  }, [start, store]);
  return {
    start,
    forget: store.clear,
    keep: (values) => {
      if (isDirty(values, settings)) {
        store.write(values, settings.version);
      } else {
        store.clear();
      }
    },
  };
}

/** Quiet hours are one group with one message: editing either time clears it. */
function clearedFor(errors: FieldErrors, field: FieldKey): FieldErrors {
  const group: FieldKey[] = field === "quietStart" || field === "quietEnd" ? ["quietStart", "quietEnd"] : [field];
  return Object.fromEntries(Object.entries(errors).filter(([key]) => !group.some((member) => member === key)));
}

/** The field errors and the stamp that tells the form when to move focus to the first of them. */
function useFieldErrors(): {
  errors: FieldErrors;
  errorStamp: number;
  show: (next: FieldErrors) => void;
  clearFor: (field: FieldKey) => void;
  clearAll: () => void;
} {
  const [errors, setErrors] = useState<FieldErrors>({});
  const [errorStamp, setErrorStamp] = useState(0);
  return {
    errors,
    errorStamp,
    show: (next) => {
      setErrors(next);
      setErrorStamp((stamp) => stamp + 1);
    },
    clearFor: (field) => {
      setErrors((current) => clearedFor(current, field));
    },
    clearAll: () => {
      setErrors({});
    },
  };
}

interface WritesInput {
  settings: Settings;
  draft: SettingsValues;
  setResult: (result: SaveResult) => void;
  forget: () => void;
  show: (errors: FieldErrors) => void;
  clearAll: () => void;
}

/** What a write that stored nothing shows: the errors of the fields it names, or the failure, or the conflict. */
function showOutcome(input: WritesInput, outcome: SaveOutcome, whenFailed: SaveFailure): void {
  const mapped = outcome.kind === "invalid" ? fieldErrors(outcome.problems) : {};
  if (Object.keys(mapped).length > 0) {
    input.show(mapped);
  } else {
    input.setResult(resultOf(outcome, input.draft, input.settings, whenFailed));
  }
}

/** The two ways to write the row, a save of the draft and a reset to the defaults; one runs at a time. */
function useWrites(input: WritesInput): {
  submit: () => void;
  reset: () => void;
  saving: boolean;
} {
  const { settings, draft, setResult, forget, clearAll, show } = input;
  const save = useSaveSettings();
  const resetting = useResetSettings();
  const inFlight = useRef(false);

  const write = (send: (callbacks: WriteCallbacks) => void, done: (stored: Settings) => SaveResult, whenFailed: SaveFailure): void => {
    inFlight.current = true;
    clearAll();
    setResult(NO_RESULT);
    send({
      onSuccess: (stored) => {
        forget();
        setResult(done(stored));
      },
      onError: (error) => {
        showOutcome(input, classifySaveError(error), whenFailed);
      },
      onSettled: () => {
        inFlight.current = false;
      },
    });
  };

  const submit = (): void => {
    const missing = emptyFieldErrors(draft);
    if (inFlight.current) {
      return;
    }
    if (Object.keys(missing).length > 0) {
      show(missing);
    } else {
      write(
        (callbacks) => {
          save.mutate({ values: draft, version: settings.version }, callbacks);
        },
        (stored) => ({ ...NO_RESULT, saved: stored }),
        "failed",
      );
    }
  };

  const reset = (): void => {
    if (!inFlight.current) {
      write(
        (callbacks) => {
          resetting.mutate(settings.version, callbacks);
        },
        () => ({ ...NO_RESULT, defaultsRestored: true }),
        "reset-failed",
      );
    }
  };

  return { submit, reset, saving: save.isPending || resetting.isPending };
}

/**
 * The state of the form between load and save: the draft, the errors, the outcome of the last save.
 * The draft starts from the stored copy and starts over whenever the stored version changes
 * (after a save, or after a 409 handed back the current settings).
 */
export function useSettingsFlow(settings: Settings): SettingsFlow {
  const { start, keep, forget } = useKeptDraft(settings);
  const [draft, setDraft] = useState(start.values);
  const [baseVersion, setBaseVersion] = useState(settings.version);
  const [result, setResult] = useState(start.result);
  const { errors, errorStamp, show, clearFor, clearAll } = useFieldErrors();
  const { submit, reset, saving } = useWrites({ settings, draft, setResult, forget, show, clearAll });

  if (baseVersion !== settings.version) {
    setBaseVersion(settings.version);
    setDraft(settings.values);
    clearAll();
  }

  const setField = (field: FieldKey, value: string): void => {
    const next = { ...draft, [field]: value };
    setDraft(next);
    clearFor(field);
    keep(next);
  };

  const dirty = isDirty(draft, settings);
  return { ...result, draft, restored: start.restored && dirty, dirty, saving, errors, errorStamp, setField, submit, reset };
}
