import { useMemo } from "react";
import { useSubjects } from "../../hooks/useSubjects";
import { Spinner } from "../common/Spinner";
import { ErrorBanner } from "../common/ErrorBanner";
import { MasteryBar } from "../common/MasteryBar";
import type { MasteryRow } from "../../api/types";
import "./Sidebar.css";

interface SidebarProps {
  selectedSubject: string | null;
  onSelectSubject: (subject: string) => void;
  mastery: MasteryRow[];
}

export function Sidebar({ selectedSubject, onSelectSubject, mastery }: SidebarProps) {
  const { subjects, loading, error } = useSubjects();

  // Per-subject rollup: average estimate across that subject's topics
  // with real data (n_obs > 0) — a subject with zero rows gets the
  // MasteryBar's "no data yet" state, not a fabricated zero.
  const rollupBySubject = useMemo(() => {
    const map = new Map<string, { estimate: number; nObs: number }>();
    const bySubject = new Map<string, MasteryRow[]>();
    for (const row of mastery) {
      if (!bySubject.has(row.subject)) bySubject.set(row.subject, []);
      bySubject.get(row.subject)!.push(row);
    }
    for (const [subject, rows] of bySubject) {
      const totalObs = rows.reduce((sum, r) => sum + r.n_obs, 0);
      const avg = rows.reduce((sum, r) => sum + r.estimate, 0) / rows.length;
      map.set(subject, { estimate: avg, nObs: totalObs });
    }
    return map;
  }, [mastery]);

  return (
    <div className="sidebar">
      <div className="sidebar__heading">Subjects</div>
      {loading && <Spinner />}
      {error && <ErrorBanner message={`Couldn't load subjects: ${error}`} />}
      {!loading && !error && subjects.length === 0 && (
        <div className="sidebar__empty">No subjects configured.</div>
      )}
      <ul className="sidebar__list">
        {subjects.map((subject) => {
          const rollup = rollupBySubject.get(subject);
          return (
            <li key={subject}>
              <button
                type="button"
                className={
                  "sidebar__item" +
                  (subject === selectedSubject ? " sidebar__item--active" : "")
                }
                onClick={() => onSelectSubject(subject)}
              >
                <span className="sidebar__item-label">{subject}</span>
                <MasteryBar estimate={rollup?.estimate} nObs={rollup?.nObs} />
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
