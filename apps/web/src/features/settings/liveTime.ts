const formatters = new Map<string, Intl.DateTimeFormat>();

function formatterFor(zone: string): Intl.DateTimeFormat {
  const cached = formatters.get(zone);
  if (cached) {
    return cached;
  }
  const created = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  formatters.set(zone, created);
  return created;
}

interface Wall {
  clock: string;
  day: number;
}

function wallTime(zone: string, at: Date): Wall | null {
  try {
    const parts = Object.fromEntries(formatterFor(zone).formatToParts(at).map((part) => [part.type, part.value]));
    const clock = `${String(parts["hour"])}:${String(parts["minute"])}`;
    const day = Date.UTC(Number(parts["year"]), Number(parts["month"]) - 1, Number(parts["day"])) / 86_400_000;
    return Number.isFinite(day) ? { clock, day } : null;
  } catch {
    return null;
  }
}

/** The local clock time "HH:MM" in a zone at a moment, or null when the zone is not a known zone. */
export function clockIn(zone: string, at: Date): string | null {
  return wallTime(zone, at)?.clock ?? null;
}

/** " (tomorrow)" or " (yesterday)" when the date in `zone` differs from the date in `reference`; else "". */
export function dayNote(zone: string, reference: string, at: Date): string {
  const there = wallTime(zone, at);
  const here = wallTime(reference, at);
  if (!there || !here || there.day === here.day) {
    return "";
  }
  return there.day > here.day ? " (tomorrow)" : " (yesterday)";
}

/** "UTC+7", "UTC+5:30", "UTC-3", "UTC+0". */
export function offsetLabel(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const total = Math.abs(minutes);
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return `UTC${sign}${String(hours)}${rest > 0 ? `:${String(rest).padStart(2, "0")}` : ""}`;
}

/** The place name without the offset the API appends: "New York, United States (UTC-5)" gives "New York, United States". */
export function placeName(label: string): string {
  return label.replace(/\s*\(UTC[^)]*\)\s*$/, "");
}

/** The city of a zone id: "America/New_York" gives "New York". */
export function cityOf(zone: string): string {
  return (zone.split("/").pop() ?? zone).replaceAll("_", " ");
}
