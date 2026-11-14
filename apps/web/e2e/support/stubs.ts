import type { Page, Route } from "@playwright/test";

/**
 * A stubbed API for the `ui-states` project: every request the app makes is answered with
 * `route.fulfill`, so no backend runs. A handler answers one endpoint; `n` counts its calls from 0.
 */
interface StubState {
  /** True once a code was accepted (or from the start for the settings states). */
  signedIn: boolean;
}

interface StubCall {
  n: number;
  state: StubState;
}

export type Handler = (route: Route, call: StubCall) => Promise<void> | void;

export interface Handlers {
  signedIn?: boolean;
  session?: Handler;
  requestCode?: Handler;
  verifyCode?: Handler;
  getSettings?: Handler;
  putSettings?: Handler;
  resetSettings?: Handler;
  logout?: Handler;
  places?: Handler;
}

export interface Stub {
  /** How many times each endpoint was called. */
  calls: Record<keyof Omit<Handlers, "signedIn">, number>;
}

export const MASKED = "m***@example.com";

export const STORED = {
  updatedAt: "2026-11-10T13:02:00Z",
  updatedVia: "telegram",
  version: 3,
  values: { timeZone: "Europe/Amsterdam", quietStart: "23:00", quietEnd: "07:00", overviewAt: "18:00", remindAt: "09:00" },
} as const;

const PLACES = {
  places: [
    { zone: "Asia/Bangkok", label: "Bangkok, Thailand", utcOffsetMinutes: 420 },
    { zone: "Asia/Dhaka", label: "Dhaka, Bangladesh", utcOffsetMinutes: 360 },
    { zone: "Europe/Amsterdam", label: "Amsterdam, Netherlands", utcOffsetMinutes: 60 },
  ],
  suggestion: null,
};

/** Answers with a status, an optional JSON body and optional headers. */
export function reply(status: number, body?: unknown, headers: Record<string, string> = {}): Handler {
  return async (route) => {
    await route.fulfill({
      status,
      headers,
      ...(body === undefined ? {} : { contentType: "application/json", body: JSON.stringify(body) }),
    });
  };
}

/** Uses the handlers in order, one per call; the last one answers every later call. */
export function sequence(...handlers: Handler[]): Handler {
  return async (route, call) => {
    const handler = handlers[Math.min(call.n, handlers.length - 1)];
    await handler?.(route, call);
  };
}

/** Holds a request until `release()` is called, then lets `inner` answer it. */
export function held(inner: Handler): { handler: Handler; release: () => void } {
  let release = (): void => undefined;
  const open = new Promise<void>((resolve) => {
    release = resolve;
  });
  return {
    release: () => {
      release();
    },
    handler: async (route, call) => {
      await open;
      await inner(route, call);
    },
  };
}

const requestCodeOk: Handler = reply(200, {
  maskedAddress: MASKED,
  expiresAt: "2026-11-12T12:10:00Z",
  resendAfterSeconds: 60,
});

const sessionByState: Handler = async (route, { state }) => {
  if (!state.signedIn) {
    await reply(401, { detail: "No session" })(route, { n: 0, state });
    return;
  }
  await reply(200, {
    maskedAddress: MASKED,
    csrfToken: "stub-csrf-token",
    noticeIntervalMinutes: 5,
    absoluteExpiresAt: "2026-11-13T12:00:00Z",
    idleExpiresAt: "2026-11-12T20:00:00Z",
  })(route, { n: 0, state });
};

const verifyOk: Handler = async (route, { state }) => {
  state.signedIn = true;
  await route.fulfill({ status: 204 });
};

const putEcho: Handler = async (route, { state }) => {
  const sent = (route.request().postDataJSON() ?? {}) as { values?: unknown; version?: number };
  await reply(200, {
    updatedAt: "2026-11-12T20:42:00Z",
    updatedVia: "web",
    version: (sent.version ?? STORED.version) + 1,
    values: sent.values ?? STORED.values,
  })(route, { n: 0, state });
};

/** The reset answers with the defaults on the next version, like the API does. */
const resetToDefaults: Handler = async (route, { state }) => {
  const sent = (route.request().postDataJSON() ?? {}) as { version?: number };
  await reply(200, {
    updatedAt: "2026-11-12T20:42:00Z",
    updatedVia: "web",
    version: (sent.version ?? STORED.version) + 1,
    values: STORED.values,
  })(route, { n: 0, state });
};

type Endpoint = keyof Stub["calls"];

function tableOf(handlers: Handlers): [Endpoint, string, string, Handler][] {
  return [
    ["session", "/api/session", "GET", handlers.session ?? sessionByState],
    ["requestCode", "/auth/request-code", "POST", handlers.requestCode ?? requestCodeOk],
    ["verifyCode", "/auth/verify-code", "POST", handlers.verifyCode ?? verifyOk],
    ["getSettings", "/api/settings", "GET", handlers.getSettings ?? reply(200, STORED)],
    ["putSettings", "/api/settings", "PUT", handlers.putSettings ?? putEcho],
    ["resetSettings", "/api/settings/reset", "POST", handlers.resetSettings ?? resetToDefaults],
    ["logout", "/auth/logout", "POST", handlers.logout ?? reply(204)],
    ["places", "/api/places", "GET", handlers.places ?? reply(200, PLACES)],
  ];
}

/** Installs the stubs on the page. A request under /api or /auth without a stub is answered 599 and shows up as a failure. */
export async function stubApi(page: Page, handlers: Handlers = {}): Promise<Stub> {
  const state: StubState = { signedIn: handlers.signedIn ?? false };
  const calls: Stub["calls"] = { session: 0, requestCode: 0, verifyCode: 0, getSettings: 0, putSettings: 0, resetSettings: 0, logout: 0, places: 0 };
  const table = tableOf(handlers);
  await page.route(
    (url) => url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/"),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      const method = route.request().method();
      const hit = table.find(([, path, verb]) => path === pathname && verb === method);
      if (!hit) {
        await route.fulfill({ status: 599, body: `No stub for ${method} ${pathname}` });
        return;
      }
      const [endpoint, , , handler] = hit;
      const n = calls[endpoint];
      calls[endpoint] += 1;
      await handler(route, { n, state });
    },
  );
  return { calls };
}
