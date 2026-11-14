// Reads the newest message of the prod-like mail catcher over its HTTP interface (U-web-settings-38).
// The catcher listens on the loopback only; MAIL_URL overrides the default for another port.

export interface Mail {
  subject: string;
  text: string;
}

interface Listing {
  messages: { ID: string }[];
}

interface Detail {
  Subject: string;
  Text: string;
}

const DEFAULT_URL = process.env.MAIL_URL ?? "http://127.0.0.1:8025";
const SIX_DIGITS = /(?<!\d)(\d{6})(?!\d)/;

// The code is the first run of exactly six digits.
export function extractCode(text: string): string {
  const found = SIX_DIGITS.exec(text);
  if (!found?.[1]) {
    throw new Error("the message has no six-digit code");
  }
  return found[1];
}

export async function newestMessage(baseUrl: string = DEFAULT_URL): Promise<Mail> {
  const listing = (await (await fetch(`${baseUrl}/api/v1/messages?limit=1`)).json()) as Listing;
  const newest = listing.messages[0];
  if (!newest) {
    throw new Error("the mailbox is empty");
  }
  const detail = (await (await fetch(`${baseUrl}/api/v1/message/${newest.ID}`)).json()) as Detail;
  return { subject: detail.Subject, text: detail.Text };
}

export async function newestCode(baseUrl: string = DEFAULT_URL): Promise<string> {
  return extractCode((await newestMessage(baseUrl)).text);
}

export async function clearMailbox(baseUrl: string = DEFAULT_URL): Promise<void> {
  const response = await fetch(`${baseUrl}/api/v1/messages`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`the mailbox could not be emptied: ${String(response.status)}`);
  }
}
