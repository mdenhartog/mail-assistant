/** What the combobox remembers between renders. `draft` is null while the field shows the form's zone. */
export interface ComboState {
  draft: string | null;
  open: boolean;
  active: number;
  preview: string | null;
}

export type ComboAction =
  | { type: "type"; text: string }
  | { type: "activate"; index: number }
  | { type: "close" }
  | { type: "settle" }
  | { type: "preview"; zone: string };

export const INITIAL_STATE: ComboState = { draft: null, open: false, active: -1, preview: null };

export function comboReducer(state: ComboState, action: ComboAction): ComboState {
  switch (action.type) {
    case "type":
      return { ...state, draft: action.text, open: true, active: -1 };
    case "activate":
      return { ...state, open: true, active: action.index };
    case "close":
      return { ...state, open: false, active: -1 };
    case "settle":
      return INITIAL_STATE;
    case "preview":
      return { ...state, preview: action.zone };
  }
}
