import type { DayRecord } from "./api";

export const HOURS_FIELDS = ["hours_worked", "hours_worked_out", "hours_reading"] as const;
export const NUMERIC_FIELDS = [...HOURS_FIELDS, "weight", "calories"] as const;
export type NumericField = (typeof NUMERIC_FIELDS)[number];

function toDate(dateStr: string): Date {
  // Parse as local date, not UTC, so weekday math matches the user's calendar.
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function currentWeek(records: DayRecord[], today: Date = new Date()): DayRecord[] {
  const byDate = new Map(records.map((r) => [r.date, r]));
  const sunday = new Date(today);
  sunday.setDate(today.getDate() - today.getDay());

  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(sunday);
    d.setDate(sunday.getDate() + i);
    const dateStr = toDateStr(d);
    return byDate.get(dateStr) ?? { date: dateStr };
  });
}

/** Average of each field per weekday (0=Sun..6=Sat), counting only present values. */
export function weekdayAverages(records: DayRecord[]): Record<NumericField, number | null>[] {
  const sums: Record<NumericField, number>[] = Array.from({ length: 7 }, () =>
    Object.fromEntries(NUMERIC_FIELDS.map((f) => [f, 0])) as Record<NumericField, number>,
  );
  const counts: Record<NumericField, number>[] = Array.from({ length: 7 }, () =>
    Object.fromEntries(NUMERIC_FIELDS.map((f) => [f, 0])) as Record<NumericField, number>,
  );

  for (const record of records) {
    const weekday = toDate(record.date).getDay();
    for (const field of NUMERIC_FIELDS) {
      const value = record[field];
      if (value === undefined) continue;
      sums[weekday][field] += value;
      counts[weekday][field] += 1;
    }
  }

  return sums.map((daySums, weekday) =>
    Object.fromEntries(
      NUMERIC_FIELDS.map((f) => [f, counts[weekday][f] > 0 ? daySums[f] / counts[weekday][f] : null]),
    ) as Record<NumericField, number | null>,
  );
}

/** All-time average (present-only) of the 3 hours fields. */
export function hoursDonut(records: DayRecord[]): { field: (typeof HOURS_FIELDS)[number]; value: number }[] {
  return HOURS_FIELDS.map((field) => {
    const present = records.map((r) => r[field]).filter((v): v is number => v !== undefined);
    const value = present.length > 0 ? present.reduce((a, b) => a + b, 0) / present.length : 0;
    return { field, value };
  });
}

export function trend(records: DayRecord[], field: NumericField): { date: string; value: number }[] {
  return records
    .filter((r) => r[field] !== undefined)
    .map((r) => ({ date: r.date, value: r[field] as number }))
    .sort((a, b) => a.date.localeCompare(b.date));
}
