/* eslint-disable @typescript-eslint/no-unused-vars -- skeleton, replaced by the implementation commit */
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import type { components } from "@/api/schema";

export type Settings = components["schemas"]["Settings"];
export type SettingsValues = components["schemas"]["SettingsValues"];
export type Problem = components["schemas"]["ProblemItem"];
export type FieldKey = keyof SettingsValues;

/** The 409 answer: the settings as they are now, and what the user had typed. */
export interface ConflictState {
  current: Settings;
  mine: SettingsValues;
}

export type SaveOutcome =
  | { kind: "invalid"; problems: Problem[] }
  | { kind: "conflict"; current: Settings }
  | { kind: "refused" }
  | { kind: "failed" };

interface SaveVariables {
  values: SettingsValues;
  version: number;
}

export function classifySaveError(_error: unknown): SaveOutcome {
  return { kind: "failed" };
}

export function useSettings(): UseQueryResult<Settings> {
  throw new Error("not built");
}

export function useSaveSettings(): UseMutationResult<Settings, Error, SaveVariables> {
  throw new Error("not built");
}
