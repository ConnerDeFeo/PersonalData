import { useState } from "react";
import type { DayRecord } from "../api";
import { NUMERIC_FIELDS } from "../stats";

export default function DayDetail({ records }: { records: DayRecord[] }) {
  const [date, setDate] = useState("");
  const record = records.find((r) => r.date === date);

  return (
    <div>
      <h2 className="text-sm text-[#898781] mb-2">Look up a day</h2>
      <input
        type="date"
        value={date}
        onChange={(e) => setDate(e.target.value)}
        className="border border-[#c3c2b7] dark:border-[#383835] bg-transparent rounded px-2 py-1 text-sm"
      />
      {date && (
        <div className="mt-2 text-sm">
          {record ? (
            <ul className="space-y-1">
              {NUMERIC_FIELDS.map((f) =>
                record[f] !== undefined ? (
                  <li key={f}>
                    <span className="text-[#898781]">{f}:</span> {record[f]}
                  </li>
                ) : null,
              )}
            </ul>
          ) : (
            <p className="text-[#898781]">No record for {date}.</p>
          )}
        </div>
      )}
    </div>
  );
}
