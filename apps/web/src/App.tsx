import type { ReactElement } from "react";

/**
 * Application shell. Replaced feature by feature through the SDLC; kept minimal on purpose.
 *
 * @example
 * <App />
 */
export function App(): ReactElement {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center gap-4 px-6 py-12 md:px-10">
      <h1 className="font-display text-4xl text-text md:text-5xl">{"Mail Assistant"}</h1>
      <p className="text-lg text-text-muted">Built with the claude-sdlc-kit. Start with /sdlc:feature.</p>
    </main>
  );
}
