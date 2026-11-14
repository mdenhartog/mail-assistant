import { useRef, useState } from "react";

import { emptyFieldErrors, fieldErrors } from "@/features/settings/fieldErrors";
import type { FieldErrors } from "@/features/settings/fieldErrors";
import { FIELD_KEYS, classifySaveError, useSaveSettings } from "@/features/settings/useSettings";
import type { ConflictState, FieldKey, SaveOutcome, Settings, SettingsValues } from "@/features/settings/useSettings";

/** A save that did not store anything and has no field to blame. */
export type SaveFailure = "failed" | "refused";

/** What the last save left behind; at most one of the three is set. */
interface SaveResult {
  failure: SaveFailure | null;
  conflict: ConflictState | null;
  saved: Settings | null;
}

const NO_RESULT: SaveResult = { failure: null, conflict: null, saved: null };

export interface SettingsFlow extends SaveResult {
  draft: SettingsValues;
  dirty: boolean;
  saving: boolean;
  errors: FieldErrors;
  /** Changes on every submit that shows errors, so focus moves once per submit and not while typing. */
  errorStamp: number;
  setField: (field: FieldKey, value: string) => void;
  submit: () => void;
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

/**
 * The state of the form between load and save: the draft, the errors, the outcome of the last save.
 * The draft starts from the stored copy and starts over whenever the stored version changes
 * (after a save, or after a 409 handed back the current settings).
 */
export function useSettingsFlow(settings: Settings): SettingsFlow {
  const save = useSaveSettings();
  const [draft, setDraft] = useState(settings.values);
  const [baseVersion, setBaseVersion] = useState(settings.version);
  const [result, setResult] = useState(NO_RESULT);
  const { errors, errorStamp, show, clearFor, clearAll } = useFieldErrors();
  const inFlight = useRef(false);

  if (baseVersion !== settings.version) {
    setBaseVersion(settings.version);
    setDraft(settings.values);
    clearAll();
  }

  const handleOutcome = (outcome: SaveOutcome): void => {
    const mapped = outcome.kind === "invalid" ? fieldErrors(outcome.problems) : {};
    if (Object.keys(mapped).length > 0) {
      show(mapped);
    } else if (outcome.kind === "conflict") {
      setResult({ ...NO_RESULT, conflict: { current: outcome.current, mine: draft, base: settings.values } });
    } else {
      setResult({ ...NO_RESULT, failure: outcome.kind === "failed" ? "failed" : "refused" });
    }
  };

  const submit = (): void => {
    const missing = emptyFieldErrors(draft);
    if (inFlight.current) {
      return;
    }
    if (Object.keys(missing).length > 0) {
      show(missing);
      return;
    }
    inFlight.current = true;
    clearAll();
    setResult(NO_RESULT);
    save.mutate(
      { values: draft, version: settings.version },
      {
        onSuccess: (stored) => {
          setResult({ ...NO_RESULT, saved: stored });
        },
        onError: (error) => {
          handleOutcome(classifySaveError(error));
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  };

  const setField = (field: FieldKey, value: string): void => {
    setDraft((current) => ({ ...current, [field]: value }));
    clearFor(field);
  };

  const dirty = FIELD_KEYS.some((key) => draft[key] !== settings.values[key]);
  return { ...result, draft, dirty, saving: save.isPending, errors, errorStamp, setField, submit };
}
