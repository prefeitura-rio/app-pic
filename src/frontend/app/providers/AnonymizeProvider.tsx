"use client";

import {
	createContext,
	useCallback,
	useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";
import {
	maskCpf,
	maskDate,
	maskField,
	maskId,
	maskName,
	type AnonymizableField,
} from "@/app/utils/anonymization";

export const STORAGE_KEY = "app-pic:anonymize-data";

export interface AnonymizeContextType {
	isAnonymized: boolean;
	setIsAnonymized: (value: boolean) => void;
	maskCpf: (cpf: string) => string;
	maskName: (name: string) => string;
	maskId: (value: string) => string;
	maskDate: (value: string) => string;
	maskField: (value: string, fieldType: AnonymizableField) => string;
}

export const AnonymizeContext = createContext<AnonymizeContextType | undefined>(
	undefined,
);

const listeners = new Set<() => void>();

function readStoredValue(): boolean {
	try {
		const raw = window.localStorage.getItem(STORAGE_KEY);
		if (!raw) return false;
		const parsed = JSON.parse(raw);
		return parsed?.isAnonymized === true;
	} catch {
		return false;
	}
}

function writeStoredValue(value: boolean) {
	try {
		window.localStorage.setItem(
			STORAGE_KEY,
			JSON.stringify({ isAnonymized: value }),
		);
	} catch {
		// localStorage indisponível: mantém apenas o estado em memória
	}
}

function subscribe(listener: () => void) {
	listeners.add(listener);
	return () => {
		listeners.delete(listener);
	};
}

function getSnapshot(): boolean {
	return readStoredValue();
}

function getServerSnapshot(): boolean {
	return false;
}

export function AnonymizeProvider({ children }: { children: ReactNode }) {
	const isAnonymized = useSyncExternalStore(
		subscribe,
		getSnapshot,
		getServerSnapshot,
	);

	const setIsAnonymized = useCallback((value: boolean) => {
		writeStoredValue(value);
		listeners.forEach((listener) => listener());
	}, []);

	const value: AnonymizeContextType = {
		isAnonymized,
		setIsAnonymized,
		maskCpf,
		maskName,
		maskId,
		maskDate,
		maskField,
	};

	return (
		<AnonymizeContext.Provider value={value}>
			{children}
		</AnonymizeContext.Provider>
	);
}
