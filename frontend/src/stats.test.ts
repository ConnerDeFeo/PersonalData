import assert from "node:assert";
import { weekdayAverages } from "./stats.ts";
import type { DayRecord } from "./api.ts";

// 2026-07-12 = Sunday, 2026-07-13 = Monday, 2026-07-19 = next Sunday.
const fixture: DayRecord[] = [
  { date: "2026-07-12", weight: 100 }, // Sun
  { date: "2026-07-19", weight: 200 }, // Sun (2nd sample)
  { date: "2026-07-13", calories: 2000 }, // Mon, no weight
];

const result = weekdayAverages(fixture);

assert.strictEqual(result[0].weight, 150, "Sunday weight should average only present values (100+200)/2");
assert.strictEqual(result[1].weight, null, "Monday weight has no samples -> null, not 0");
assert.strictEqual(result[1].calories, 2000, "Monday calories should be the single present value");
assert.strictEqual(result[2].weight, null, "Tuesday has no records -> null");

console.log("stats.test.ts: all assertions passed");
