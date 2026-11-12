import { expect, test } from "@playwright/test";

import { clearMailbox, extractCode, newestCode, newestMessage } from "./support/mailbox";

const ORIGIN = process.env.E2E_BASE_URL ?? "https://mail-assistant.localhost:8443";
const USERNAME = process.env.E2E_USERNAME ?? "e2e-owner";
const CODE = /^\d{6}$/;

test.describe("extractCode", () => {
  test("returns the six-digit code of the message body", () => {
    expect(extractCode("Your sign-in code is 042917.\n\nIt is valid for 10 minutes.")).toBe("042917");
  });

  test("ignores digit runs of other lengths and fails when there is no code", () => {
    expect(extractCode("ref 1234567 and 12345 then 654321 end")).toBe("654321");
    expect(() => extractCode("no digits here 12345")).toThrow(/code/);
  });
});

// One request at a time: the stack has one allowed user and one mailbox, so only the desktop project runs this.
test.describe("mailbox over the running stack", () => {
  test("returns the newest message with a six-digit code and a subject without it", async ({ request }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one project only: the mailbox is shared");
    await clearMailbox();
    const response = await request.post(`${ORIGIN}/auth/request-code`, {
      data: { username: USERNAME },
      headers: { Origin: new URL(ORIGIN).origin },
    });
    expect(response.status()).toBe(200);

    await expect.poll(async () => (await newestMessage().catch(() => null))?.text ?? "", { timeout: 20_000 }).toMatch(/\d{6}/);
    const mail = await newestMessage();
    const code = await newestCode();

    expect(code).toMatch(CODE);
    expect(mail.text).toContain(code);
    expect(mail.subject).not.toMatch(/\d{6}/);
  });
});
