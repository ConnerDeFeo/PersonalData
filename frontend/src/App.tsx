import { useEffect, useMemo, useState } from "react";
import { fetchRecords, type DayRecord } from "./api";
import { currentWeek } from "./stats";
import WeekRow from "./components/WeekRow";
import HoursDonut from "./components/HoursDonut";
import TrendCharts from "./components/TrendCharts";
import WeekdayAverages from "./components/WeekdayAverages";
import DayDetail from "./components/DayDetail";

export default function App() {
  const [records, setRecords] = useState<DayRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRecords().then(setRecords).catch((e) => setError(String(e)));
  }, []);

  const week = useMemo(() => (records ? currentWeek(records) : []), [records]);

  if (error) return <div className="p-6 text-[#e34948]">Failed to load: {error}</div>;
  if (!records) return <div className="p-6 text-[#898781]">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto p-6 flex flex-col gap-8">
      <h1 className="text-xl font-semibold">Personal Data Dashboard</h1>

      <section>
        <h2 className="text-sm text-[#898781] mb-2">This week</h2>
        <WeekRow week={week} />
      </section>

      <section className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <HoursDonut records={records} />
        <TrendCharts records={records} />
      </section>

      <section>
        <WeekdayAverages records={records} />
      </section>

      <section>
        <DayDetail records={records} />
      </section>
    </div>
  );
}
