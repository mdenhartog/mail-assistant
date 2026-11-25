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
  getCategories?: Handler;
  putCategories?: Handler;
  uploadFile?: Handler;
  confirmUpload?: Handler;
  restorePrevious?: Handler;
  exportList?: Handler;
  getPlan?: Handler;
  getLatestResort?: Handler;
  postResort?: Handler;
  getPlanItems?: Handler;
  postDecision?: Handler;
  postApprove?: Handler;
  postMoveBack?: Handler;
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
  values: { timeZone: "Europe/Amsterdam", quietStart: "23:00", quietEnd: "07:00", overviewAt: "18:00", remindAt: "09:00", waitingMinutes: 720, protectionDays: 7, retentionDays: 30 },
  ranges: {
    waitingMinutes: { min: 5, max: 720, default: 720 },
    protectionDays: { min: 1, max: 30, default: 7 },
    retentionDays: { min: 7, max: 90, default: 30 },
  },
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

export const CATEGORIES = {
  version: 5,
  ready: true,
  generalInstructions: "Keep receipts for the tax year.",
  archiveLabel: "Archive",
  otherLabel: "Other",
  categories: [
    { id: "00000000-0000-4000-8000-000000000001", name: "Invoices", description: "Invoices, receipts and payment confirmations.", mailCount: 120, kind: "extra", notify: true, senders: [{ entry: "billing@example.com", subdomains: false, skippedCount: 0 }] },
    { id: "00000000-0000-4000-8000-000000000002", name: "Newsletters", description: "Weekly digests and product news I read on Sunday.", mailCount: 1, kind: "topic", notify: false, senders: [] },
    { id: "00000000-0000-4000-8000-000000000003", name: "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW", description: "https://example.com/a/very/long/address/that/has/no/spaces/at/all/and/keeps/going/and/going", mailCount: 0, kind: "topic", notify: false, senders: [] },
  ],
  other: { mailCount: 42 },
} as const;

/** What an upload of a valid file returns: 3 added, 5 changed and 2 removed, one of them with a very long name. */
export const UPLOAD_PREVIEW = {
  previewId: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa",
  fileHash: "a".repeat(64),
  baseVersion: 5,
  expiresAt: "2026-11-22T12:10:00Z",
  added: 3,
  adopted: 2,
  changed: 5,
  removed: 2,
  removedCategories: ["Travel/Trains", "W".repeat(60)],
  instructionsChanged: true,
  archiveLabelChanged: true,
} as const;

const putCategoriesEcho: Handler = async (route, { state }) => {
  const sent = (route.request().postDataJSON() ?? {}) as { version?: number };
  await reply(200, { ...CATEGORIES, version: (sent.version ?? CATEGORIES.version) + 1 })(route, { n: 0, state });
};

export const PLAN = {
  id: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa",
  state: "ready",
  progress: { checked: 900, cap: 5000, unclear: 2, estimate: 2000, notLookedAt: 0 },
  groups: [
    { from: "00000000-0000-0000-0000-000000000000", to: "00000000-0000-4000-8000-000000000001", count: 20, approved: 0, rejected: 0, example: { senderName: "Acme Billing", senderAddress: "billing@acme.example", subject: "Your invoice" } },
    { from: "00000000-0000-4000-8000-000000000002", to: "00000000-0000-4000-8000-000000000001", count: 12, approved: 0, rejected: 0, example: { senderName: "Acme Billing", senderAddress: "billing@acme.example", subject: "Your invoice" } },
    { from: "00000000-0000-4000-8000-0000000000ff", to: "00000000-0000-4000-8000-000000000003", count: 1, approved: 0, rejected: 0, example: { senderName: "Acme Billing", senderAddress: "billing@acme.example", subject: "Your invoice" } },
  ],
  counts: { items: 33, pending: 33, approved: 0, rejected: 0 },
  applyAfter: null,
  applyThreshold: 50,
  applyDelayMinutes: 30,
  lastPlan: null,
  threshold: 80,
  auto: { moved: 5, scheduled: 12, skipped: 1 },
} as const;

/** `GET /api/plan` while no plan is open. */
export const NO_PLAN = { ...PLAN, id: null, state: null, groups: [], counts: { items: 0, pending: 0, approved: 0, rejected: 0 } } as const;

/** Untrusted model text: markup and a link inside it must stay text. */
const TIP = 'Add billing@acme.example (4 mails) as a sender of Invoices. <a href="https://evil.example">not a link</a> https://evil.example/' + "x".repeat(60);

export function planItems(first: number, size: number, hasMore: boolean, page = 1): unknown {
  return {
    page,
    hasMore,
    items: Array.from({ length: size }, (_, index) => ({
      id: first + index,
      senderName: index % 5 === 0 ? `‮PayPal Support ${String(first + index)}‬` : `Sender ${String(first + index)} with a rather long display name`,
      senderAddress: `someone.with.a.long.address.${String(first + index)}@example.com`,
      subject: index % 7 === 0 ? "W".repeat(80) : `Your invoice ${String(first + index)} for the month is ready to download`,
      from: "00000000-0000-0000-0000-000000000000",
      to: "00000000-0000-4000-8000-000000000001",
      decision: "pending",
      state: "pending",
      reason: null,
      oldTopic: index % 3 === 0 ? null : "Household/Energy and utilities/Yearly statements",
      oldExtra: index % 2 === 0 ? null : "Household/Energy and utilities/Yearly statements/Acme",
      newTopic: "Finance/Invoices",
      newExtra: index % 4 === 0 ? "Finance/Invoices/Acme" : null,
      confidencePct: index % 6 === 0 ? null : 40 + index,
      tip: TIP,
    })),
  };
}

type Endpoint = keyof Stub["calls"];

function tableOf(given: Handlers): [Endpoint, string, string, Handler][] {
  const own: Required<Omit<Handlers, "signedIn">> = {
    session: sessionByState,
    requestCode: requestCodeOk,
    verifyCode: verifyOk,
    getSettings: reply(200, STORED),
    putSettings: putEcho,
    resetSettings: resetToDefaults,
    logout: reply(204),
    places: reply(200, PLACES),
    getCategories: reply(200, CATEGORIES),
    putCategories: putCategoriesEcho,
    uploadFile: reply(200, UPLOAD_PREVIEW),
    confirmUpload: reply(200, { ...CATEGORIES, version: 6 }),
    restorePrevious: reply(200, { ...CATEGORIES, version: 7 }),
    exportList: async (route) => {
      await route.fulfill({ status: 200, contentType: "application/yaml", body: "schema: 1\n" });
    },
    getPlan: reply(200, PLAN),
    getLatestResort: reply(200, { threshold: 50 }),
    postResort: reply(201, { requestId: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00bb", threshold: 50 }),
    getPlanItems: async (route, call) => {
      const page = Number(new URL(route.request().url()).searchParams.get("page") ?? "1");
      await reply(200, planItems((page - 1) * 12 + 1, page < 2 ? 12 : 8, page < 2, page))(route, call);
    },
    postDecision: reply(200, { changed: 20 }),
    postApprove: reply(200, { state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" }),
    postMoveBack: reply(200, { processed: false }),
    ...given,
  };
  return [
    ["session", "/api/session", "GET", own.session],
    ["requestCode", "/auth/request-code", "POST", own.requestCode],
    ["verifyCode", "/auth/verify-code", "POST", own.verifyCode],
    ["getSettings", "/api/settings", "GET", own.getSettings],
    ["putSettings", "/api/settings", "PUT", own.putSettings],
    ["resetSettings", "/api/settings/reset", "POST", own.resetSettings],
    ["logout", "/auth/logout", "POST", own.logout],
    ["places", "/api/places", "GET", own.places],
    ["getCategories", "/api/categories", "GET", own.getCategories],
    ["putCategories", "/api/categories", "PUT", own.putCategories],
    ["uploadFile", "/api/categories/upload", "POST", own.uploadFile],
    ["confirmUpload", "/api/categories/upload/:id/confirm", "POST", own.confirmUpload],
    ["restorePrevious", "/api/categories/restore-previous", "POST", own.restorePrevious],
    ["exportList", "/api/categories/export", "GET", own.exportList],
    ["getPlan", "/api/plan", "GET", own.getPlan],
    ["getLatestResort", "/api/resort-requests/latest", "GET", own.getLatestResort],
    ["postResort", "/api/resort-requests", "POST", own.postResort],
    ["getPlanItems", "/api/plan/items", "GET", own.getPlanItems],
    ["postDecision", "/api/plan/decisions", "POST", own.postDecision],
    ["postApprove", "/api/plan/approve", "POST", own.postApprove],
    ["postMoveBack", "/api/plan/:id/move-back", "POST", own.postMoveBack],
  ];
}

/** A path matches exactly, or segment by segment where the stub path has `:id`. */
function samePath(stubPath: string, pathname: string): boolean {
  const want = stubPath.split("/");
  const have = pathname.split("/");
  return want.length === have.length && want.every((part, index) => part.startsWith(":") || part === have[index]);
}

/** Installs the stubs on the page. A request under /api or /auth without a stub is answered 599 and shows up as a failure. */
export async function stubApi(page: Page, handlers: Handlers = {}): Promise<Stub> {
  const state: StubState = { signedIn: handlers.signedIn ?? false };
  const calls: Stub["calls"] = { session: 0, requestCode: 0, verifyCode: 0, getSettings: 0, putSettings: 0, resetSettings: 0, logout: 0, places: 0, getCategories: 0, putCategories: 0, uploadFile: 0, confirmUpload: 0, restorePrevious: 0, exportList: 0, getPlan: 0, getLatestResort: 0, postResort: 0, getPlanItems: 0, postDecision: 0, postApprove: 0, postMoveBack: 0 };
  const table = tableOf(handlers);
  await page.route(
    (url) => url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/"),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      const method = route.request().method();
      const hit = table.find(([, path, verb]) => samePath(path, pathname) && verb === method);
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
