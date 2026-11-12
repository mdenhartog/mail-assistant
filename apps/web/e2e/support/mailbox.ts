// Reads the newest message of the prod-like mail catcher (U-web-settings-38). Skeleton: implemented next.

export interface Mail {
  subject: string;
  text: string;
}

export function extractCode(text: string): string {
  throw new Error(`not implemented ${String(text.length)}`);
}

export function newestMessage(baseUrl?: string): Promise<Mail> {
  return Promise.reject(new Error(`not implemented ${baseUrl ?? ""}`));
}

export function newestCode(baseUrl?: string): Promise<string> {
  return Promise.reject(new Error(`not implemented ${baseUrl ?? ""}`));
}

export function clearMailbox(baseUrl?: string): Promise<void> {
  return Promise.reject(new Error(`not implemented ${baseUrl ?? ""}`));
}
