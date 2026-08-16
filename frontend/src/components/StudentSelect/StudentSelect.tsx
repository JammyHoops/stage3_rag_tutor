import { useEffect, useMemo, useRef, useState } from "react";
import { useStudents } from "../../hooks/useStudents";
import "./StudentSelect.css";

interface StudentSelectProps {
  studentId: string;
  onChange: (id: string) => void;
}

// Replaces the old plain-text StudentIdBar. There is no login and no real
// student roster (see stage3/api/students.py's module docstring) — a
// bare text input gives a new user nothing to search against, which is
// exactly the problem this fixes: a small hand-rolled combobox (no UI
// library elsewhere in this project — see package.json) that shows every
// id seen before, filters as you type, and still lets a brand-new id be
// typed and used freely (that's not an edge case here, it's the normal
// way a first-time student starts).
export function StudentSelect({ studentId, onChange }: StudentSelectProps) {
  const { students, loading, error } = useStudents();
  const [inputValue, setInputValue] = useState(studentId);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Keep the input in sync if studentId changes from outside (e.g.
  // restored from localStorage on load).
  useEffect(() => setInputValue(studentId), [studentId]);

  const trimmed = inputValue.trim();
  const filtered = useMemo(() => {
    if (!trimmed) return students;
    const q = trimmed.toLowerCase();
    return students.filter((s) => s.toLowerCase().includes(q));
  }, [students, trimmed]);
  const isNewId = trimmed !== "" && !students.includes(trimmed);

  useEffect(() => {
    function onDocPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocPointerDown);
    return () => document.removeEventListener("mousedown", onDocPointerDown);
  }, []);

  function commit(value: string) {
    const next = value.trim();
    setInputValue(next);
    onChange(next);
    setOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    const optionCount = filtered.length + (isNewId ? 1 : 0);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlighted((h) => Math.min(h + 1, optionCount - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (open && filtered[highlighted]) {
        commit(filtered[highlighted]);
      } else {
        commit(inputValue);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="student-select" ref={containerRef}>
      <span className="student-select__label">Student ID</span>
      <div className="student-select__combobox">
        <input
          className="student-select__input"
          type="text"
          value={inputValue}
          placeholder="Search or enter a new student ID..."
          onChange={(e) => {
            setInputValue(e.target.value);
            setOpen(true);
            setHighlighted(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          onBlur={() => commit(inputValue)}
        />
        {open && !loading && (
          <ul className="student-select__dropdown">
            {filtered.length === 0 && !trimmed && (
              <li className="student-select__empty">
                No students yet — type an ID to start.
              </li>
            )}
            {filtered.map((s, i) => (
              <li
                key={s}
                className={
                  "student-select__option" +
                  (i === highlighted ? " student-select__option--active" : "")
                }
                // mousedown (not click) fires before the input's blur, so
                // selecting an option wins the race against onBlur's commit.
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(s);
                }}
              >
                {s}
              </li>
            ))}
            {isNewId && (
              <li
                className={
                  "student-select__option student-select__option--new" +
                  (filtered.length === highlighted ? " student-select__option--active" : "")
                }
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(inputValue);
                }}
              >
                Use new ID "{trimmed}"
              </li>
            )}
          </ul>
        )}
      </div>
      {error && (
        <span className="student-select__hint">
          Couldn't load student list: {error}
        </span>
      )}
      <span className="student-select__hint">
        Pseudonymous ID — no login exists in this prototype.
      </span>
    </div>
  );
}
