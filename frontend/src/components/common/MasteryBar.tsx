import "./common.css";

interface MasteryBarProps {
  // undefined = no mastery data at all for this (student, subject[, topic])
  // — the cold-start case (student_state/store.py returns no row, not a
  // guessed default) — rendered distinctly from a real low estimate.
  estimate?: number;
  nObs?: number;
}

// Small presentational bar: red -> green as estimate goes 0 -> 1, grey/
// empty when there's no diagnostic-derived data yet. Used inline in the
// Sidebar (per-subject rollup) and ConversationList (per-topic) rather
// than a separate dashboard page — see the mastery indicator's design
// note in the usability-pass plan.
export function MasteryBar({ estimate, nObs }: MasteryBarProps) {
  if (estimate === undefined) {
    return (
      <span
        className="mastery-bar mastery-bar--empty"
        title="No check-in yet"
        aria-label="No mastery data yet"
      />
    );
  }
  const pct = Math.round(estimate * 100);
  const hue = Math.max(0, Math.min(120, estimate * 120));
  return (
    <span
      className="mastery-bar"
      title={`${nObs ?? 0} check-in${nObs === 1 ? "" : "s"} — ${pct}% mastery`}
      aria-label={`${pct}% mastery`}
    >
      <span
        className="mastery-bar__fill"
        style={{ width: `${pct}%`, backgroundColor: `hsl(${hue}, 70%, 45%)` }}
      />
    </span>
  );
}
