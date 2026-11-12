import { useEffect, useReducer } from "react";
import type { Dispatch, KeyboardEvent } from "react";

import { INITIAL_STATE, comboReducer } from "@/features/settings/zoneComboboxState";
import type { ComboAction, ComboState } from "@/features/settings/zoneComboboxState";
import { useZoneSearch } from "@/features/settings/useZoneSearch";
import type { Place, ZoneSearch } from "@/features/settings/useZoneSearch";

/** How long the active option must rest before the live paragraph speaks. */
const LIVE_PAUSE_MS = 300;

interface ComboView {
  places: Place[];
  expanded: boolean;
  activeIndex: number;
  typed: string;
  noMatch: boolean;
  lookupFailed: boolean;
  suggestion: string | null;
  previewZone: string | null;
}

function lookupFlags(state: ComboState, search: ZoneSearch, empty: boolean): Pick<ComboView, "noMatch" | "lookupFailed"> {
  const typing = state.draft !== null;
  return {
    noMatch: typing && search.state === "done" && empty,
    lookupFailed: typing && search.state === "failed",
  };
}

function placesOf(search: ZoneSearch): Place[] {
  return search.state === "done" ? search.places : [];
}

function suggestionOf(search: ZoneSearch): string | null {
  return search.state === "done" ? search.suggestion : null;
}

function describe(state: ComboState, search: ZoneSearch): ComboView {
  const places = placesOf(search);
  const expanded = state.open && state.draft !== null && places.length > 0;
  return {
    ...lookupFlags(state, search, places.length === 0),
    places,
    expanded,
    activeIndex: expanded ? state.active : -1,
    typed: (state.draft ?? "").trim(),
    suggestion: suggestionOf(search),
    previewZone: expanded ? (places[Math.max(state.active, 0)]?.zone ?? null) : null,
  };
}

function usePreview(zone: string | null, dispatch: Dispatch<ComboAction>): void {
  useEffect(() => {
    if (zone === null) {
      return undefined;
    }
    const timer = setTimeout(() => {
      dispatch({ type: "preview", zone });
    }, LIVE_PAUSE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [zone, dispatch]);
}

export interface ZoneComboboxModel {
  state: ComboState;
  view: ComboView;
  type: (text: string) => void;
  suggest: (text: string, inputId: string) => void;
  settle: () => void;
  choose: (place: Place) => void;
  keyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
}

interface ModelInput {
  value: string;
  savedValue: string;
  readOnly: boolean;
  onChange: (zone: string) => void;
}

/** The state, the derived view and the key model of the zone combobox. */
export function useZoneCombobox({ value, savedValue, readOnly, onChange }: ModelInput): ZoneComboboxModel {
  const [state, dispatch] = useReducer(comboReducer, INITIAL_STATE);
  const view = describe(state, useZoneSearch(state.draft ?? "", state.draft !== null));
  usePreview(view.previewZone, dispatch);

  const choose = (place: Place): void => {
    dispatch({ type: "settle" });
    onChange(place.zone);
  };
  const move = (step: 1 | -1): void => {
    const last = view.places.length - 1;
    if (state.draft === null || last < 0) {
      return;
    }
    const first = step === 1 ? 0 : last;
    const next = view.expanded ? state.active + step : first;
    dispatch({ type: "activate", index: next > last || next < 0 ? first : next });
  };
  const escape = (): void => {
    if (view.expanded) {
      dispatch({ type: "close" });
      return;
    }
    dispatch({ type: "settle" });
    if (value !== savedValue) {
      onChange(savedValue);
    }
  };
  const enter = (): boolean => {
    const chosen = view.places[state.active] ?? (view.places.length === 1 ? view.places[0] : undefined);
    if (view.expanded && chosen) {
      choose(chosen);
    }
    return view.expanded;
  };
  const keyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    const dirty = view.expanded || state.draft !== null || value !== savedValue;
    const handled = readOnly ? false : runKey(event.key, { move, escape, enter, dirty });
    if (handled) {
      event.preventDefault();
    }
  };

  return {
    state,
    view,
    choose,
    keyDown,
    settle: () => {
      dispatch({ type: "settle" });
    },
    type: (text) => {
      dispatch({ type: "type", text });
    },
    suggest: (text, inputId) => {
      dispatch({ type: "type", text });
      document.getElementById(inputId)?.focus();
    },
  };
}

interface KeyActions {
  move: (step: 1 | -1) => void;
  escape: () => void;
  enter: () => boolean;
  dirty: boolean;
}

function runKey(key: string, actions: KeyActions): boolean {
  if (key === "ArrowDown" || key === "ArrowUp") {
    actions.move(key === "ArrowDown" ? 1 : -1);
    return true;
  }
  if (key === "Enter") {
    return actions.enter();
  }
  if (key === "Escape" && actions.dirty) {
    actions.escape();
    return true;
  }
  return false;
}
