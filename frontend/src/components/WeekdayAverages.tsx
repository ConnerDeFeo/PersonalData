import type { DayRecord } from "../api";
import { NUMERIC_FIELDS, weekdayAverages } from "../stats";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function WeekdayAverages({ records }: { records: DayRecord[] }) {
  const averages = weekdayAverages(records);

  return (
    <div className="overflow-x-auto">
      <h2 className="text-sm text-[#898781] mb-2">All-time averages by weekday</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[#898781]">
            <th className="text-left font-normal py-1">Day</th>
            {NUMERIC_FIELDS.map((f) => (
              <th key={f} className="text-right font-normal py-1 pl-3">
                {f}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {WEEKDAY_LABELS.map((label, i) => (
            <tr key={label} className="border-t border-[#e1e0d9] dark:border-[#2c2c2a]">
              <td className="py-1">{label}</td>
              {NUMERIC_FIELDS.map((f) => (
                <td key={f} className="text-right pl-3 tabular-nums">
                  {averages[i][f] !== null ? averages[i][f]!.toFixed(1) : "–"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
