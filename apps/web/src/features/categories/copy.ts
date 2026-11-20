/** "1 mail", "12 mails". */
export function countText(count: number): string {
  return `${String(count)} ${count === 1 ? "mail" : "mails"}`;
}
