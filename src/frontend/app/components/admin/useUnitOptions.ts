"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiService } from "@/app/services/api";
import { IdWithName, UnitType } from "@/app/types";

/**
 * Lazy unit options for one assignment dropdown.
 *
 * One grouped PostgREST query per unit type, fired on the first dropdown
 * open (cached per unit_type). RLS scopes the rows, so segmented admins
 * naturally see only their own units — no user-ids lookup needed.
 */
export function useUnitOptions(unitType: UnitType): {
  options: IdWithName[];
  isLoading: boolean;
  onOpen: () => void;
} {
  const [opened, setOpened] = useState(false);

  const { data, isFetching } = useQuery({
    queryKey: ["admin", "available-ids", unitType],
    queryFn: () => apiService.getAvailableUnitIds(unitType),
    enabled: opened,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const onOpen = useCallback(() => {
    setOpened(true);
  }, []);

  return {
    options: data ?? [],
    isLoading: opened && isFetching,
    onOpen,
  };
}
