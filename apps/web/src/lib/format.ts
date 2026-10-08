/** UTC timestamp for display, e.g. "2026-01-01 10:00:00Z". */
export const formatUtc = (date: Date): string => `${date.toISOString().slice(0, 19).replace("T", " ")}Z`;
