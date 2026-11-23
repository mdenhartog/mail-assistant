import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { INVOICES, LIST, json, renderPageInRouter, wire } from "@/test/categories";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Categories page: a link to the edit view of one category (AC-52)", () => {
  it("given ?edit=<category id>, then that category's edit view opens and the address is cleaned", async () => {
    wire({ get: () => json(LIST) });
    const { router } = renderPageInRouter(`/categories?edit=${INVOICES.id}`);

    expect(await screen.findByRole("heading", { level: 2, name: "Edit category" })).toBeInTheDocument();
    expect(router.state.location.search).toBe("");
  });

  it("given ?edit= with an id that is not in the list, then the list shows and nothing opens", async () => {
    wire({ get: () => json(LIST) });
    renderPageInRouter("/categories?edit=nope");

    expect(await screen.findByRole("button", { name: `Edit ${INVOICES.name}` })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Edit category" })).not.toBeInTheDocument();
  });
});
