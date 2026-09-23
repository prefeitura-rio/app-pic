"use client";

import { useContext } from "react";
import {
	AnonymizeContext,
	type AnonymizeContextType,
} from "@/app/providers/AnonymizeProvider";

export function useAnonymizeData(): AnonymizeContextType {
	const context = useContext(AnonymizeContext);
	if (!context) {
		throw new Error(
			"useAnonymizeData deve ser usado dentro de <AnonymizeProvider>",
		);
	}
	return context;
}
