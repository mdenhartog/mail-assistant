import { useEffect, useRef } from "react";
import type { ReactElement, RefObject } from "react";

import { Button } from "@/components/Button";
import { ConflictBanner } from "@/features/settings/ConflictBanner";
import { useConflict } from "@/features/settings/useConflict";
import type { ConflictMark, ConflictSource } from "@/features/settings/useConflict";
import type { ConflictState, FieldKey, SettingsValues } from "@/features/settings/useSettings";

interface ConflictLayerProps {
  conflict: ConflictState | null;
  values: SettingsValues;
  setValue: (field: FieldKey, value: string) => void;
}

interface MarkItemProps {
  mark: ConflictMark;
  source: ConflictSource;
  onUseMine: () => void;
  onKeepTheirs: () => void;
}

/** The words for the other side of a mark: "Telegram now has", and the button that keeps its value. */
const WORDING: Record<ConflictSource, { has: string; keep: string }> = {
  telegram: { has: "Telegram", keep: "Keep Telegram's" },
  web: { has: "the web", keep: "Keep the stored value" },
};

function MarkItem({ mark, source, onUseMine, onKeepTheirs }: MarkItemProps): ReactElement {
  const words = WORDING[source];
  return (
    <li className="rounded-control border-l-8 border-primary bg-surface-raised px-4 py-3 text-text">
      <p className="font-bold">{mark.label}</p>
      <p>{`You typed ${mark.mine}, ${words.has} now has ${mark.theirs}`}</p>
      {mark.usingMine ? <p className="text-text-muted">Using your value.</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button aria-label={`Use mine for ${mark.label}`} onClick={onUseMine} variant="secondary">
          Use mine
        </Button>
        <Button aria-label={`${words.keep} for ${mark.label}`} onClick={onKeepTheirs} variant="secondary">
          {words.keep}
        </Button>
      </div>
    </li>
  );
}

/** When a mark is settled its buttons are gone: focus moves to the next mark, or to the layer itself. */
function useKeepFocus(root: RefObject<HTMLDivElement | null>, count: number): void {
  const previous = useRef(count);
  useEffect(() => {
    if (count < previous.current && !root.current?.contains(document.activeElement)) {
      const next = root.current?.querySelector<HTMLElement>("li button");
      (next ?? root.current)?.focus();
    }
    previous.current = count;
  }, [count, root]);
}

/**
 * Above the fields after a 409: the banner and, for every field the user had edited that the other
 * change moved too, the two values and the choice between them. Nothing is saved from here.
 *
 * @example
 * <ConflictLayer conflict={flow.conflict} setValue={flow.setField} values={flow.draft} />
 */
export function ConflictLayer({ conflict, values, setValue }: ConflictLayerProps): ReactElement | null {
  const view = useConflict(conflict, values, setValue);
  const root = useRef<HTMLDivElement>(null);
  useKeepFocus(root, view?.marks.length ?? 0);
  if (view === null) {
    return null;
  }
  return (
    <div className="flex flex-col gap-3 outline-none" ref={root} tabIndex={-1}>
      <ConflictBanner title={view.title} />
      {view.marks.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {view.marks.map((mark) => (
            <MarkItem
              key={mark.field}
              mark={mark}
              source={view.source}
              onKeepTheirs={() => {
                view.keepTheirs(mark.field);
              }}
              onUseMine={() => {
                view.useMine(mark.field);
              }}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
