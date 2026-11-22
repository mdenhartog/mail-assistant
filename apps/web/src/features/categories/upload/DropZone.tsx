import { useId, useState } from "react";
import type { ReactElement } from "react";

/**
 * The upload control: the native file input is the keyboard and screen-reader way in, the box around it takes
 * a dropped file. Both hand the file on; nothing is read here.
 */
export function DropZone({ disabled, onFile }: { disabled: boolean; onFile: (file: File) => void }): ReactElement {
  const id = useId();
  const [over, setOver] = useState(false);
  return (
    <div
      className={`flex flex-col gap-2 rounded-card border-2 border-dashed p-4 ${over ? "border-primary bg-surface-raised" : "border-border"}`}
      onDragLeave={() => {
        setOver(false);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setOver(true);
        }
      }}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const file = event.dataTransfer.files[0];
        if (!disabled && file !== undefined) {
          onFile(file);
        }
      }}
    >
      <label className="font-semibold text-text" htmlFor={id}>
        Choose a YAML file
      </label>
      <input
        accept=".yaml,.yml,application/yaml,text/yaml"
        className="min-h-11 w-full min-w-0 cursor-pointer text-text file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-pill file:border-2 file:border-border file:bg-surface-raised file:px-5 file:font-semibold file:text-text"
        disabled={disabled}
        id={id}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file !== undefined) {
            onFile(file);
          }
        }}
        type="file"
      />
      <p className="text-text-muted">{over ? "Drop the file now." : "Or drop the file on this box. Nothing changes until you have seen a preview."}</p>
    </div>
  );
}
