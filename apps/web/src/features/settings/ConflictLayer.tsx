import { useEffect, useRef } from "react";
import type { ReactElement, RefObject } from "react";

import { Button } from "@/components/Button";
import { ConflictBanner } from "@/features/settings/ConflictBanner";
import { useConflict } from "@/features/settings/useConflict";
import type { ConflictMark } from "@/features/settings/useConflict";
import type { ConflictState, FieldKey, SettingsValues } from "@/features/settings/useSettings";

interface ConflictLayerProps {
  conflict: ConflictState | null;
  values: SettingsValues;
  setValue: (field: FieldKey, value: string) => void;
}

interface MarkItemProps {
  mark: ConflictMark;
  onUseMine: () => void;
  onKeepTheirs: () => void;
}

function MarkItem({ mark, onUseMine, onKeepTheirs }: MarkItemProps): ReactElement {
  return (
    <li className="rounded-control border-l-8 border-primary bg-surface-raised px-4 py-3 text-text">
      <p className="font-bold">{mark.label}</p>
      <p>{`You typed ${mark.mine}, Telegram now has ${mark.theirs}`}</p>
      {mark.usingMine ? <p className="text-text-muted">Using your value.</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button aria-label={`Use mine for ${mark.label}`} onClick={onUseMine} variant="secondary">
          Use mine
        </Button>
        <Button aria-label={`Keep Telegram's for ${mark.label}`} onClick={onKeepTheirs} variant="secondary">
          Keep Telegram&apos;s
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
