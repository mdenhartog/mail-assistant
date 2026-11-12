/* eslint-disable @typescript-eslint/no-unused-vars -- skeleton, replaced by the implementation commit */
import type { FieldKey, Problem, SettingsValues } from "@/features/settings/useSettings";

export type FieldErrors = Partial<Record<FieldKey, string>>;

export function problemText(_problem: Problem): string {
  return "";
}

export function fieldErrors(_problems: Problem[]): FieldErrors {
  return {};
}

export function emptyFieldErrors(_values: SettingsValues): FieldErrors {
  return {};
}
