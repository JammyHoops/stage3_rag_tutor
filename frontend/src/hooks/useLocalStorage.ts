import { useEffect, useState } from "react";

export function useLocalStorage(key: string, initial: string) {
  const [value, setValue] = useState<string>(
    () => localStorage.getItem(key) ?? initial,
  );

  useEffect(() => {
    localStorage.setItem(key, value);
  }, [key, value]);

  return [value, setValue] as const;
}
