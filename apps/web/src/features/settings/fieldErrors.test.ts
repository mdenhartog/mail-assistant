import { describe, expect, it } from "vitest";

import { emptyFieldErrors, fieldErrors, problemText } from "@/features/settings/fieldErrors";
import type { Problem, SettingsValues } from "@/features/settings/useSettings";

const VALUES: SettingsValues = {
  timeZone: "Europe/Amsterdam",
  quietStart: "23:00",
  quietEnd: "07:00",
  overviewAt: "18:00",
  remindAt: "09:00",
};

function problem(field: string, rule: string, value: string, example: string): Problem {
  return { field, rule, value, example };
}

describe("problemText: one sentence per rule id, in the words of Telegram", () => {
  it.each([
    ["overview_in_quiet_hours", "23:30", "Try 07:00", "The daily overview at 23:30 would fall inside quiet hours. Try 07:00."],
    ["remind_in_quiet_hours", "23:15", "Try 07:00", "The remind-me-later default at 23:15 would fall inside quiet hours. Try 07:00."],
    ["quiet_window_empty", "07:00 to 07:00", "Try 07:00 to 19:00", "Quiet hours must start and end at different times. 07:00 to 07:00 is empty. Try 07:00 to 19:00."],
    ["quiet_window_length", "20:00 to 12:00", "Try 20:00 to 08:00", "Quiet hours can be 1 to 12 hours. 20:00 to 12:00 is 16 hours. Try 20:00 to 08:00."],
    ["quiet_window_length", "07:00 to 07:30", "Try 07:00 to 08:00", "Quiet hours can be 1 to 12 hours. 07:00 to 07:30 is 30 minutes. Try 07:00 to 08:00."],
    ["zone_unknown", "Mars/Olympus", "Try Europe/Amsterdam", 'I could not find a time zone for "Mars/Olympus". Try Europe/Amsterdam.'],
    ["time_not_whole_minute", "09:00:30", "Try 09:00", "That is not a time in whole minutes, such as 09:00. Try 09:00."],
    ["time_has_zone", "09:00", "Try 09:00", "That is not a time in whole minutes, such as 09:00. Try 09:00."],
    ["a_rule_from_the_future", "x", "Try y", "That is not allowed. Try y."],
  ])("given the rule %s, when worded, then the sentence reads right", (rule, value, example, expected) => {
    expect(problemText(problem("x", rule, value, example))).toBe(expected);
  });
});

describe("fieldErrors", () => {
  it("given problems for two fields, when mapped, then each field has its text", () => {
    const result = fieldErrors([
      problem("overviewAt", "overview_in_quiet_hours", "23:30", "Try 07:00"),
      problem("remindAt", "remind_in_quiet_hours", "23:15", "Try 07:00"),
    ]);

    expect(Object.keys(result).sort()).toEqual(["overviewAt", "remindAt"]);
    expect(result.overviewAt).toContain("daily overview");
  });

  it("given two problems for one field, when mapped, then the first one wins", () => {
    const result = fieldErrors([
      problem("quietStart", "quiet_window_empty", "a", "Try b"),
      problem("quietStart", "quiet_window_length", "c", "Try d"),
    ]);

    expect(result.quietStart).toContain("different times");
  });

  it("given a field name the form does not have, when mapped, then it is dropped", () => {
    expect(fieldErrors([problem("somethingElse", "zone_unknown", "x", "Try y")])).toEqual({});
  });
});

describe("emptyFieldErrors: nothing is sent when a value is missing", () => {
  it("given all values, when checked, then there is no error", () => {
    expect(emptyFieldErrors(VALUES)).toEqual({});
  });

  it("given an empty time and an empty zone, when checked, then each field asks for a value", () => {
    const result = emptyFieldErrors({ ...VALUES, overviewAt: "", timeZone: " " });

    expect(result.overviewAt).toBe("Pick a time, for example 18:00.");
    expect(result.timeZone).toBe("Type a city or a country, for example Paris or Japan.");
    expect(Object.keys(result)).toHaveLength(2);
  });

  it("given an empty quiet start, when checked, then the quiet hours say which time is missing", () => {
    expect(emptyFieldErrors({ ...VALUES, quietStart: "" }).quietStart).toBe("Pick a time, for example 23:00.");
  });
});
