import type { DayRecord } from "../api";
import { NUMERIC_FIELDS } from "../stats";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function WeekRow({ week }: { week: DayRecord[] }) {
  return (
    <div className="overflow-x-auto">
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
          {week.map((day, i) => (
            <tr key={day.date} className="border-t border-[#e1e0d9] dark:border-[#2c2c2a]">
              <td className="py-1">
                {WEEKDAY_LABELS[i]} <span className="text-[#898781]">{day.date}</span>
              </td>
              {NUMERIC_FIELDS.map((f) => (
                <td key={f} className="text-right pl-3 tabular-nums">
                  {day[f] ?? "–"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
