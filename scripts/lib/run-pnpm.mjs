// Runs pnpm without `shell: true` (no argument concatenation by a shell):
// - started via `pnpm run`: use pnpm's own entry (a JS file or, since pnpm 11+, a native executable);
// - Windows otherwise: pnpm is a .cmd shim, so go through cmd.exe with quoted, fixed arguments;
// - elsewhere: call pnpm directly.
import { execFileSync } from "node:child_process";

export function runPnpm(args, options = {}) {
  const entry = process.env.npm_execpath;
  if (entry && /pnpm/i.test(entry)) {
    return /\.[cm]?js$/i.test(entry)
      ? execFileSync(process.execPath, [entry, ...args], options)
      : execFileSync(entry, args, options);
  }
  if (process.platform === "win32") {
    const quoted = args.map((a) => (/^[\w@./:=-]+$/.test(a) ? a : `"${a.replace(/"/g, '\\"')}"`));
    return execFileSync("cmd.exe", ["/d", "/s", "/c", ["pnpm", ...quoted].join(" ")], options);
  }
  return execFileSync("pnpm", args, options);
}
