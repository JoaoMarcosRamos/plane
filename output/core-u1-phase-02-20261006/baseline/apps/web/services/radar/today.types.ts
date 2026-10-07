export type TodayObject = { id: string; title: string; status: string };
export type TodayRisk = TodayObject & { score: number | null; review_date: string | null; review_overdue: boolean };
export type TodayAction = TodayObject & { due_date: string };
export type TodaySuggestion = {
  id: string;
  title: string;
  component: "relation" | "action";
  explanation: string;
  confidence: number;
};
export type RadarTodayQueue = {
  date: string;
  timezone: string;
  risks: TodayRisk[];
  decisions: TodayObject[];
  overdue_actions: TodayAction[];
  suggestions: TodaySuggestion[];
};
