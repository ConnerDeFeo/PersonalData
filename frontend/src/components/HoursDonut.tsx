import { PieChart, Pie, Cell, Tooltip, Legend } from "recharts";
import type { DayRecord } from "../api";
import { hoursDonut } from "../stats";
import { usePalette } from "../colors";

export default function HoursDonut({ records }: { records: DayRecord[] }) {
  const palette = usePalette();
  const colors = [palette.blue, palette.green, palette.magenta];
  const data = hoursDonut(records).map((d) => ({ name: d.field, value: Number(d.value.toFixed(2)) }));

  return (
    <div>
      <h2 className="text-sm text-[#898781] mb-2">Avg hours split (all-time)</h2>
      <PieChart width={280} height={240}>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={colors[i]} stroke="none" />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </div>
  );
}
