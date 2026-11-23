import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { expectNoAxeViolations } from "@/test/axe";
import { INVOICES, LIST, json, renderPage } from "@/test/categories";

const PREVIEW = {
  previewId: "5b0c1c2e-1b1e-4c52-9d0e-0a6a1b1c00aa",
  fileHash: "a".repeat(64),
  baseVersion: 3,
  expiresAt: "2026-11-22T12:10:00Z",
  added: 3,
  changed: 5,
  removed: 2,
  removedCategories: ["Travel", "Huis/Energie"],
  instructionsChanged: false,
  archiveLabelChanged: false,
};
const PROBLEMS = {
  type: "about:blank",
  title: "Unprocessable content",
  status: 422,
  problems: [
    { rule: "unknown_field", line: 4, field: "categories[0].colour", message: "This field is not part of the format." },
    { rule: "empty_segment", line: 9, field: "categories[1].name", message: "A name cannot have an empty part." },
  ],
};

interface Call {
  method: string;
  path: string;
  body: string | null;
  bytes: Uint8Array | null;
  contentType: string | null;
}

type Answer = () => Response;
interface Answers {
  upload?: Answer;
  confirm?: Answer;
  restore?: Answer;
  exported?: Answer;
}

const YAML_FILE = (): Response => new Response("schema: 1\n", { status: 200, headers: { "Content-Type": "application/yaml" } });

function answerFor(path: string, answers: Answers): Response {
  const own: Record<string, Answer | undefined> = {
    "/api/categories/upload": answers.upload ?? (() => json(PREVIEW)),
    [`/api/categories/upload/${PREVIEW.previewId}/confirm`]: answers.confirm ?? (() => json({ ...LIST, version: 4 })),
    "/api/categories/restore-previous": answers.restore ?? (() => json({ ...LIST, version: 5 })),
    "/api/categories/export": answers.exported ?? YAML_FILE,
  };
  return (own[path] ?? (() => json(LIST)))();
}

/** The bytes a request body would put on the wire, or null when there is no binary body. */
async function bytesOf(body: BodyInit | null | undefined): Promise<Uint8Array | null> {
  if (body instanceof Blob) {
    return new Uint8Array(await body.arrayBuffer());
  }
  if (body instanceof ArrayBuffer) {
    return new Uint8Array(body);
  }
  if (ArrayBuffer.isView(body)) {
    return new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
  }
  return null;
}

/** A stubbed `fetch` for the categories page and the file routes; every call is recorded. */
function wire(answers: Answers = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      calls.push({
        method: (init.method ?? "GET").toUpperCase(),
        path: input,
        body: typeof init.body === "string" ? init.body : null,
        bytes: await bytesOf(init.body),
        contentType: new Headers(init.headers).get("Content-Type"),
      });
      return answerFor(input, answers);
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

let container: HTMLElement;

const FILE = new File(["schema: 1\ncategories: []\n"], "categories.yaml", { type: "application/yaml" });

async function uploaded(): Promise<ReturnType<typeof userEvent.setup>> {
  const user = userEvent.setup();
  container = renderPage();
  await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });
  await user.upload(screen.getByLabelText("Choose a YAML file"), FILE);
  return user;
}

describe("Upload: the preview (criterion 1, 2, 6)", () => {
  it("given a valid file, then the preview leads with the counts and shows the removed block with its sentence", async () => {
    const calls = wire();
    await uploaded();

    const preview = await screen.findByRole("region", { name: "Preview of your file" });
    expect(preview).toHaveTextContent("3 added, 5 changed, 2 removed");
    expect(within(preview).getByText("3 added").tagName).toBe("STRONG");
    const removed = within(preview).getByRole("region", { name: "Removed categories" });
    expect(removed).toHaveTextContent("Removed categories disappear from the app. Their Gmail labels and mail stay as they are.");
    expect(within(removed).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Travel", "Huis/Energie"]);
    const sent = calls.find((call) => call.path === "/api/categories/upload");
    expect(sent).toMatchObject({ method: "POST", contentType: "application/yaml" });
    expect(new TextDecoder().decode(sent?.bytes ?? new Uint8Array())).toBe("schema: 1\ncategories: []\n");
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });

  it("given the archive label changes, then the preview says so; otherwise it says nothing about it", async () => {
    wire({ upload: () => json({ ...PREVIEW, archiveLabelChanged: true }) });
    await uploaded();
    const preview = await screen.findByRole("region", { name: "Preview of your file" });
    expect(within(preview).getByText("The archive label changes too.")).toBeInTheDocument();
  });

  it("given the archive label stays, then the preview has no archive label line", async () => {
    wire();
    await uploaded();
    const preview = await screen.findByRole("region", { name: "Preview of your file" });
    expect(within(preview).queryByText(/archive label/i)).not.toBeInTheDocument();
  });

  it("given removals, then the confirm button names the count and does not hold the focus", async () => {
    wire();
    await uploaded();

    const confirm = await screen.findByRole("button", { name: "Replace my whole list (2 removed)" });
    expect(confirm).not.toHaveFocus();
    expect(screen.getByRole("heading", { name: "Preview of your file" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });

  it("given nothing removed, then there is no removed block and the button has no count", async () => {
    wire({ upload: () => json({ ...PREVIEW, removed: 0, removedCategories: [] }) });
    await uploaded();

    expect(await screen.findByRole("button", { name: "Replace my whole list" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Removed categories" })).not.toBeInTheDocument();
  });

  it("given added, changed and removed, then each is marked with a word and an icon", async () => {
    wire();
    await uploaded();

    await screen.findByRole("region", { name: "Preview of your file" });
    for (const word of ["3 added", "5 changed", "2 removed"]) {
      const mark = screen.getByText(word).closest("span");
      expect(mark?.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    }
  });

  it("given Cancel, then the preview goes away and nothing was stored", async () => {
    const calls = wire();
    const user = await uploaded();

    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("region", { name: "Preview of your file" })).not.toBeInTheDocument();
    expect(calls.some((call) => call.path.endsWith("/confirm"))).toBe(false);
  });

  it("passes axe with the preview open", async () => {
    wire();
    await uploaded();
    await screen.findByRole("region", { name: "Preview of your file" });

    await expectNoAxeViolations(container);
  });
});

describe("Upload: a refused file (criterion 3)", () => {
  it("given an invalid file, then every problem shows line and field, they can be copied and nothing changes", async () => {
    const calls = wire({ upload: () => json(PROBLEMS, 422, { "Content-Type": "application/problem+json" }) });
    const user = await uploaded();

    const errors = await screen.findByRole("region", { name: "Your file was not accepted" });
    expect(errors).toHaveTextContent("Nothing was changed.");
    const items = within(errors).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Line 4, categories[0].colour: This field is not part of the format.");
    expect(items[1]).toHaveTextContent("Line 9, categories[1].name: A name cannot have an empty part.");
    expect(screen.queryByRole("button", { name: /Replace my whole list/ })).not.toBeInTheDocument();

    await user.click(within(errors).getByRole("button", { name: "Copy errors" }));

    expect(await navigator.clipboard.readText()).toBe(
      "Line 4, categories[0].colour: This field is not part of the format.\nLine 9, categories[1].name: A name cannot have an empty part.",
    );
    expect(await screen.findByText("Copied.")).toBeInTheDocument();
    expect(calls.filter((call) => call.method !== "GET" && call.path !== "/api/categories/upload")).toEqual([]);
    await expectNoAxeViolations(container);
  });

  it.each([
    ["a BOM", [0xef, 0xbb, 0xbf, ...new TextEncoder().encode("schema: 1\n")], "bom", "The file starts with a byte order mark."],
    ["a Windows-1252 byte", [...new TextEncoder().encode("name: caf"), 0xe9, 0x0a], "not_utf8", "The file is not UTF-8."],
  ])("given a file with %s, then its bytes reach the API unchanged and the API's problem is shown", async (_label, raw, rule, message) => {
    const bytes = Uint8Array.from(raw);
    const problems = { ...PROBLEMS, problems: [{ rule, line: 1, field: "file", message }] };
    const calls = wire({ upload: () => json(problems, 422, { "Content-Type": "application/problem+json" }) });
    const user = userEvent.setup();
    container = renderPage();
    await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });

    await user.upload(screen.getByLabelText("Choose a YAML file"), new File([bytes], "list.yaml", { type: "application/yaml" }));

    const errors = await screen.findByRole("region", { name: "Your file was not accepted" });
    expect(errors).toHaveTextContent(`Line 1, file: ${message}`);
    const sent = calls.find((call) => call.path === "/api/categories/upload");
    expect(sent?.contentType).toBe("application/yaml");
    expect(Array.from(sent?.bytes ?? [])).toEqual(Array.from(bytes));
  });

  it.each([
    [413, "The file is too large."],
    [415, "That is not a YAML file."],
    [429, "Too many changes to the list this hour."],
    [500, "Could not check the file. Nothing was changed."],
  ])("given a %i, then the page says so in words", async (status, text) => {
    wire({ upload: () => json({}, status) });
    await uploaded();

    expect(await screen.findByText(text, { exact: false })).toBeInTheDocument();
  });
});

describe("Upload: confirm and restore (criteria 4 and 7)", () => {
  it("given a confirm, then the new list is stored and Restore previous version is offered and works", async () => {
    const calls = wire();
    const user = await uploaded();

    await user.click(await screen.findByRole("button", { name: "Replace my whole list (2 removed)" }));

    const confirmed = calls.find((call) => call.path === `/api/categories/upload/${PREVIEW.previewId}/confirm`);
    expect(confirmed).toMatchObject({ method: "POST", body: JSON.stringify({ fileHash: PREVIEW.fileHash }) });
    expect(await screen.findByText("Your list was replaced.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Preview of your file" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Restore previous version" }));

    await waitFor(() => {
      expect(calls.find((call) => call.path === "/api/categories/restore-previous")).toMatchObject({
        method: "POST",
        body: JSON.stringify({ version: 4 }),
      });
    });
    expect(await screen.findByText("The previous version is back.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore previous version" })).not.toBeInTheDocument();
  });

  it("given a 409 on confirm, then the page says the list changed and asks to upload again, with nothing to restore", async () => {
    wire({ confirm: () => json({ title: "Conflict" }, 409) });
    const user = await uploaded();

    await user.click(await screen.findByRole("button", { name: "Replace my whole list (2 removed)" }));

    expect(await screen.findByText("The list changed.")).toBeInTheDocument();
    expect(screen.getByText(/Upload the file again/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore previous version" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Preview of your file" })).not.toBeInTheDocument();
  });

  it("given a 409 on restore, then the page says the list changed", async () => {
    wire({ restore: () => json({ title: "Conflict" }, 409) });
    const user = await uploaded();
    await user.click(await screen.findByRole("button", { name: "Replace my whole list (2 removed)" }));

    await user.click(await screen.findByRole("button", { name: "Restore previous version" }));

    expect(await screen.findByText("The list changed.")).toBeInTheDocument();
  });
});

describe("Export and the template (criterion 5)", () => {
  it("offers the download as mail-categories.yaml and links the template and the example", async () => {
    wire();
    renderPage();
    await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });

    const download = screen.getByRole("link", { name: "Download my list" });
    expect(download).toHaveAttribute("href", "/api/categories/export");
    expect(download).toHaveAttribute("download", "mail-categories.yaml");
    expect(screen.getByRole("link", { name: "Download the template" })).toHaveAttribute("href", "/api/categories/template?file=template");
    expect(screen.getByRole("link", { name: "Download the example" })).toHaveAttribute("href", "/api/categories/template?file=example");
  });

  it("copies the exported file to the clipboard", async () => {
    const calls = wire();
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });

    await user.click(screen.getByRole("button", { name: "Copy my list" }));

    expect(await screen.findByText("Copied.")).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe("schema: 1\n");
    expect(calls.some((call) => call.path === "/api/categories/export")).toBe(true);
  });

  it("says so when the list cannot be copied", async () => {
    wire({ exported: () => json({}, 409) });
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: `Edit ${INVOICES.name}` });

    await user.click(screen.getByRole("button", { name: "Copy my list" }));

    expect(await screen.findByText("Could not copy your list.")).toBeInTheDocument();
  });
});
