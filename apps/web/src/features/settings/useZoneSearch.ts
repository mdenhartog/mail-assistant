import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiFetch } from "@/api/client";
import type { components } from "@/api/schema";

export type Place = components["schemas"]["Place"];
type PlaceResults = components["schemas"]["PlaceResults"];

/** How long the typing must pause before a request goes out. */
const PAUSE_MS = 250;

export type ZoneSearch =
  | { state: "idle" | "pending" | "failed" }
  | { state: "done"; places: Place[]; suggestion: string | null };

function isPlace(value: unknown): value is Place {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>)["zone"] === "string" &&
    typeof (value as Record<string, unknown>)["label"] === "string" &&
    typeof (value as Record<string, unknown>)["utcOffsetMinutes"] === "number"
  );
}

function isResults(value: unknown): value is PlaceResults {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as Record<string, unknown>)["places"]) &&
    ((value as { places: unknown[] }).places).every(isPlace)
  );
}

async function searchPlaces(query: string, signal: AbortSignal): Promise<PlaceResults> {
  const response = await apiFetch(`/api/places?q=${encodeURIComponent(query)}`, { signal });
  const body: unknown = await response.json();
  if (!isResults(body)) {
    throw new Error("Unexpected places answer");
  }
  return body;
}

function useAfterPause(text: string): string {
  const [paused, setPaused] = useState(text);
  useEffect(() => {
    const timer = setTimeout(() => {
      setPaused(text);
    }, PAUSE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [text]);
  return paused;
}

/**
 * Looks places up for the typed text once the typing pauses. Only the answer for the text as it is
 * now is returned, so a late answer for older text is never shown. The text goes nowhere but the
 * request: it is not logged, stored or put in the page address.
 *
 * @example
 * const search = useZoneSearch("bang", true);
 */
export function useZoneSearch(text: string, enabled: boolean): ZoneSearch {
  const trimmed = text.trim();
  const paused = useAfterPause(trimmed);
  const query = useQuery({
    queryKey: ["places", paused],
    queryFn: ({ signal }) => searchPlaces(paused, signal),
    enabled: enabled && paused !== "",
    staleTime: 60_000,
    gcTime: 60_000,
    retry: false,
  });
  if (!enabled || trimmed === "") {
    return { state: "idle" };
  }
  if (paused !== trimmed || query.isPending) {
    return { state: "pending" };
  }
  if (query.isError) {
    return { state: "failed" };
  }
  return { state: "done", places: query.data.places, suggestion: query.data.suggestion ?? null };
}
