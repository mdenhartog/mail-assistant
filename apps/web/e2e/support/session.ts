// Where the `setup` project saves the signed-in browser state and the projects after it read it from (U-web-settings-42).
// The folder is git-ignored; the file holds a live session cookie of the throwaway prod-like stack only.
import { fileURLToPath } from "node:url";

export const STORAGE_STATE = fileURLToPath(new URL("../../playwright/.auth/user.json", import.meta.url));
export const USERNAME = process.env.E2E_USERNAME ?? "e2e-owner";
