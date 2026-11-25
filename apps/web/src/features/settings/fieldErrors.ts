import { durationText, rangeMessage } from "@/features/settings/cleanupText";
import { FIELD_KEYS, NUMBER_KEYS, isNumberKey } from "@/features/settings/useSettings";
import type { FieldKey, Problem, Ranges, SettingsValues } from "@/features/settings/useSettings";

/** Message per form field; a field that is not in the object is fine. */
export type FieldErrors = Partial<Record<FieldKey, string>>;

const MINUTES_PER_DAY = 1440;
const WINDOW = /^(\d{2}):(\d{2}) to (\d{2}):(\d{2})$/;

function isFieldKey(name: string): name is FieldKey {
  return FIELD_KEYS.some((key) => key === name);
}

/** "16 hours", "30 minutes", "12 hours 1 minute" for a shown window such as "20:00 to 12:00". */
function windowLength(shown: string): string | null {
  const match = WINDOW.exec(shown);
  if (!match) {
    return null;
  }
  const [startH, startM, endH, endM] = match.slice(1).map(Number) as [number, number, number, number];
  return durationText((endH * 60 + endM - (startH * 60 + startM) + MINUTES_PER_DAY) % MINUTES_PER_DAY);
}

function windowLengthText({ value, example }: Problem): string {
  const length = windowLength(value);
  return `Quiet hours can be 1 to 12 hours. ${value}${length ? ` is ${length}` : ""}. ${example}.`;
}

const TEXT: Record<string, (problem: Problem) => string> = {
  overview_in_quiet_hours: ({ value, example }) => `The daily overview at ${value} would fall inside quiet hours. ${example}.`,
  remind_in_quiet_hours: ({ value, example }) =>
    `The remind-me-later default at ${value} would fall inside quiet hours. ${example}.`,
  quiet_window_empty: ({ value, example }) =>
    `Quiet hours must start and end at different times. ${value} is empty. ${example}.`,
  quiet_window_length: windowLengthText,
  zone_unknown: ({ value, example }) => `I could not find a time zone for "${value}". ${example}.`,
  time_not_whole_minute: ({ example }) => `That is not a time in whole minutes, such as 09:00. ${example}.`,
  time_has_zone: ({ example }) => `That is not a time in whole minutes, such as 09:00. ${example}.`,
};

/**
 * One refused rule in plain words, the wording of the Telegram dialogue. The rule id picks the
 * sentence; the value and the example come from the server. A rule this page does not know gets a
 * generic sentence, so a new rule on the server is never shown as a bare code.
 */
export function problemText(problem: Problem): string {
  return (TEXT[problem.rule] ?? (({ example }: Problem) => `That is not allowed. ${example}.`))(problem);
}

/**
 * Maps the problems of a 422 to the fields they name; the first problem of a field wins. A number outside its
 * range is worded from the ranges the api sent, the same words as the check before sending.
 */
export function fieldErrors(problems: Problem[], ranges: Ranges): FieldErrors {
  const result: FieldErrors = {};
  for (const problem of problems) {
    if (isFieldKey(problem.field) && result[problem.field] === undefined) {
      result[problem.field] = isNumberKey(problem.field) ? rangeMessage(problem.field, ranges) : problemText(problem);
    }
  }
  return result;
}

const MISSING_TIME: Record<"quietStart" | "quietEnd" | "overviewAt" | "remindAt", string> = {
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};

/** Values that are missing: nothing is sent for them, the field asks instead. A number outside its range is refused the same way. */
export function emptyFieldErrors(values: SettingsValues, ranges: Ranges): FieldErrors {
  const result: FieldErrors = {};
  if (values.timeZone.trim() === "") {
    result.timeZone = "Type a city or a country, for example Paris or Japan.";
  }
  for (const [key, example] of Object.entries(MISSING_TIME) as [keyof typeof MISSING_TIME, string][]) {
    if (values[key] === "") {
      result[key] = `Pick a time, for example ${example}.`;
    }
  }
  for (const key of NUMBER_KEYS) {
    if (values[key] < ranges[key].min || values[key] > ranges[key].max) {
      result[key] = rangeMessage(key, ranges);
    }
  }
  return result;
}
