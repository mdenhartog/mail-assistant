import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, setCsrfToken } from "@/api/client";
import { approvePlan, classifyPlanError, fetchPlan, fetchPlanItems, moveBack, postDecision } from "@/api/plan/plan.api";
import { INVOICES, json } from "@/test/categories";
import { OTHER_ID, PLAN_ID, itemsPage, wirePlan } from "@/test/plan";

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrfToken(null);
});

describe("plan api: reading", () => {
  it("given a plan answer, then the plan is returned as the contract names it", async () => {
    wirePlan();
    const plan = await fetchPlan();
    expect(plan.state).toBe("ready");
    expect(plan.groups).toHaveLength(2);
  });

  it("given an answer that breaks the contract, then reading throws instead of passing it on", async () => {
    wirePlan({ plan: () => json({ state: "ready", groups: "nope" }) });
    await expect(fetchPlan()).rejects.toThrow("Unexpected plan answer");
  });

  it("given a group and a page, then only ids and the page number go in the query, never sender or subject", async () => {
    const seen = wirePlan({ items: () => json(itemsPage(1, 2, true, 2)) });
    const page = await fetchPlanItems({ from: OTHER_ID, to: INVOICES.id }, 2);
    expect(page.hasMore).toBe(true);
    const call = seen[0];
    expect(call?.path).toBe("/api/plan/items");
    expect([...(call?.search.keys() ?? [])].sort()).toEqual(["from", "page", "to"]);
    expect(call?.search.get("page")).toBe("2");
  });

  it("given no group, then the items of the whole plan are asked for", async () => {
    const seen = wirePlan();
    await fetchPlanItems(null, 1);
    expect([...(seen[0]?.search.keys() ?? [])]).toEqual(["page"]);
  });
});

describe("plan api: writing", () => {
  it("given a decision, then it posts the plan id, the count seen, the scope and the CSRF token", async () => {
    setCsrfToken("tok");
    const seen = wirePlan();
    const result = await postDecision({ planId: PLAN_ID, itemCount: 82, scope: { all: true }, decision: "rejected" });
    expect(result.changed).toBe(1);
    expect(seen[0]?.body).toEqual({ planId: PLAN_ID, itemCount: 82, scope: { all: true }, decision: "rejected" });
    expect(seen[0]?.token).toBe("tok");
  });

  it("given an approval, then it posts the plan id and the count and returns the state and the time", async () => {
    const seen = wirePlan();
    const result = await approvePlan({ planId: PLAN_ID, itemCount: 82 });
    expect(result).toEqual({ state: "scheduled", applyAfter: "2026-11-15T14:20:00Z" });
    expect(seen[0]?.path).toBe("/api/plan/approve");
  });

  it("given Move back, then it posts to the route of that plan", async () => {
    const seen = wirePlan();
    const result = await moveBack(PLAN_ID);
    expect(result.processed).toBe(false);
    expect(seen[0]?.path).toBe(`/api/plan/${PLAN_ID}/move-back`);
  });
});

describe("plan api: failures", () => {
  it("tells a 409, a 422 for too many ids, a 429 and anything else apart", () => {
    expect(classifyPlanError(new ApiError(409, { status: 409 }))).toEqual({ kind: "conflict" });
    expect(classifyPlanError(new ApiError(422, { reason: "too_many_ids" }))).toEqual({ kind: "too-many-ids" });
    expect(classifyPlanError(new ApiError(429))).toEqual({ kind: "rate-limited" });
    expect(classifyPlanError(new ApiError(500))).toEqual({ kind: "failed" });
    expect(classifyPlanError(new Error("offline"))).toEqual({ kind: "failed" });
  });
});
