import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import type { DayRecord } from "../api";
import { trend, type NumericField } from "../stats";
import { usePalette } from "../colors";

const CHARTS: { field: NumericField; label: string }[] = [
  { field: "hours_worked", label: "Hours worked over time" },
  { field: "weight", label: "Weight over time" },
  { field: "calories", label: "Calories over time" },
];

export default function TrendCharts({ records }: { records: DayRecord[] }) {
  const palette = usePalette();

  return (
    <div className="flex flex-col gap-4">
      {CHARTS.map(({ field, label }) => (
        <div key={field}>
          <h2 className="text-sm text-[#898781] mb-1">{label}</h2>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={trend(records, field)}>
              <CartesianGrid stroke={palette.grid} vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: palette.muted }} minTickGap={30} />
              <YAxis tick={{ fontSize: 10, fill: palette.muted }} width={40} />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke={palette.blue} strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  );
}
