import type { ReactElement } from "react";

import { clockIn, dayNote, offsetLabel, placeName } from "@/features/settings/liveTime";
import type { Place } from "@/features/settings/useZoneSearch";

interface ZoneOptionsProps {
  id: string;
  places: Place[];
  activeIndex: number;
  expanded: boolean;
  /** The zone the day words (tomorrow, yesterday) are measured against. */
  reference: string;
  at: Date;
  onChoose: (place: Place) => void;
}

const LIST =
  "absolute inset-x-0 top-full z-10 mt-1 max-h-72 overflow-auto rounded-control border border-border " +
  "bg-surface-raised py-1 shadow-soft";
const OPTION =
  "flex min-h-11 cursor-pointer flex-wrap items-center justify-between gap-x-3 px-3 py-1 text-text " +
  "aria-selected:bg-primary aria-selected:text-primary-contrast";

function optionText(place: Place, reference: string, at: Date): { name: string; detail: string } {
  const clock = clockIn(place.zone, at);
  const time = clock === null ? "" : `, ${clock} now${dayNote(place.zone, reference, at)}`;
  return { name: placeName(place.label), detail: `${offsetLabel(place.utcOffsetMinutes)}${time}` };
}

/** The listbox. Labels come from the API and are rendered as text only. A press chooses and keeps focus in the input. */
export function ZoneOptions({ id, places, activeIndex, expanded, reference, at, onChoose }: ZoneOptionsProps): ReactElement {
  return (
    <ul aria-label="Matching places" className={LIST} hidden={!expanded} id={id} role="listbox">
      {places.map((place, index) => {
        const text = optionText(place, reference, at);
        return (
          <li
            aria-label={`${text.name}, ${text.detail}`}
            aria-selected={index === activeIndex}
            className={OPTION}
            id={`${id}-option-${String(index)}`}
            key={`${place.zone}|${place.label}`}
            onMouseDown={(event) => {
              event.preventDefault();
              onChoose(place);
            }}
            role="option"
          >
            <span>{text.name}</span>
            <span className="text-sm tabular-nums">{text.detail}</span>
          </li>
        );
      })}
    </ul>
  );
}
