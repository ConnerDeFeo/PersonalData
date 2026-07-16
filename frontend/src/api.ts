export type DayRecord = {
  date: string; // YYYY-MM-DD
  hours_worked?: number;
  hours_worked_out?: number;
  hours_reading?: number;
  weight?: number;
  calories?: number;
};

const API_BASE = import.meta.env.VITE_API_BASE as string;

export async function fetchRecords(): Promise<DayRecord[]> {
  const res = await fetch(`${API_BASE}/records`);
  if (!res.ok) throw new Error(`GET /records failed: ${res.status}`);
  const data = await res.json();
  return data.records as DayRecord[];
}
