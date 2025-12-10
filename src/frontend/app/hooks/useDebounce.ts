import { useEffect, useState } from "react";

/**
 * Hook para debounce de valores.
 * Evita re-renders e API calls desnecessários durante digitação.
 *
 * @param value - Valor a ser debounced
 * @param delay - Delay em ms (padrão: 300ms)
 * @returns Valor debounced
 */
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    // Set timeout to update debounced value after delay
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    // Cleanup timeout if value changes before delay
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}
