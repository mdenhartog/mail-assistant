import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { ApiError, apiFetch } from "@/api/client";
import type { components } from "@/api/schema";

export type Settings = components["schemas"]["Settings"];
export type SettingsValues = components["schemas"]["SettingsValues"];
export type Problem = components["schemas"]["ProblemItem"];
export type FieldKey = keyof SettingsValues;

/** The 409 answer: the settings as they are now, what the user had typed and what that was based on. */
export interface ConflictState {
  current: Settings;
  mine: SettingsValues;
  /** The stored values the typed ones started from; a field differs from these only if the user edited it. */
  base: SettingsValues;
}

/** What a failed save means for the page. */
export type SaveOutcome =
  | { kind: "invalid"; problems: Problem[] }
  | { kind: "conflict"; current: Settings }
  | { kind: "refused" }
  | { kind: "failed" };

interface SaveVariables {
  values: SettingsValues;
  version: number;
}

const settingsKey = ["settings"] as const;
/** The five values in the order of the form. */
export const FIELD_KEYS: readonly FieldKey[] = ["timeZone", "quietStart", "quietEnd", "overviewAt", "remindAt"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isValues(value: unknown): value is SettingsValues {
  return isRecord(value) && FIELD_KEYS.every((key) => typeof value[key] === "string");
}

function isSettings(value: unknown): value is Settings {
  return isRecord(value) && isValues(value["values"]) && typeof value["version"] === "number";
}

function isProblem(value: unknown): value is Problem {
  return isRecord(value) && ["field", "rule", "value", "example"].every((key) => typeof value[key] === "string");
}

function problemsOf(body: unknown): Problem[] {
  const list = isRecord(body) ? body["problems"] : undefined;
  return Array.isArray(list) ? (list as unknown[]).filter(isProblem) : [];
}

async function readSettings(response: Response): Promise<Settings> {
  const body: unknown = await response.json();
  if (!isSettings(body)) {
    throw new Error("Unexpected settings answer");
  }
  return body;
}

/** Tells a 422 with problems, a 409 with the current settings and any other failure apart. */
export function classifySaveError(error: unknown): SaveOutcome {
  if (!(error instanceof ApiError)) {
    return { kind: "failed" };
  }
  const body = error.body;
  if (error.status === 409 && isRecord(body) && isSettings(body["current"])) {
    return { kind: "conflict", current: body["current"] };
  }
  if (error.status === 422) {
    const list = problemsOf(body);
    return list.length > 0 ? { kind: "invalid", problems: list } : { kind: "refused" };
  }
  return { kind: "failed" };
}

/**
 * The stored settings. Kept until a save changes them: a refetch while the user types would
 * replace the form under their hands.
 *
 * @example
 * const { data } = useSettings();
 */
export function useSettings(): UseQueryResult<Settings> {
  return useQuery({
    queryKey: settingsKey,
    queryFn: async () => readSettings(await apiFetch("/api/settings")),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** What both writes do with an answer: the stored row, or the 409's current one, becomes the stored copy. */
function useStoredCopy(): { onSuccess: (saved: Settings) => void; onError: (error: Error) => void } {
  const queryClient = useQueryClient();
  return {
    onSuccess: (saved) => {
      queryClient.setQueryData(settingsKey, saved);
    },
    onError: (error) => {
      const outcome = classifySaveError(error);
      if (outcome.kind === "conflict") {
        queryClient.setQueryData(settingsKey, outcome.current);
      }
    },
  };
}

/** Saves the whole row on the version it was based on; the answer, or the 409's current, becomes the stored copy. */
export function useSaveSettings(): UseMutationResult<Settings, Error, SaveVariables> {
  return useMutation({
    mutationFn: async (variables: SaveVariables) =>
      readSettings(await apiFetch("/api/settings", { method: "PUT", body: JSON.stringify(variables) })),
    ...useStoredCopy(),
  });
}

/** Replaces the stored values, the time zone included, with the defaults on the version the page shows (R2). */
export function useResetSettings(): UseMutationResult<Settings, Error, number> {
  return useMutation({
    mutationFn: async (version: number) =>
      readSettings(await apiFetch("/api/settings/reset", { method: "POST", body: JSON.stringify({ version }) })),
    ...useStoredCopy(),
  });
}
