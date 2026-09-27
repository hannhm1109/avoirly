"use client";
import { useEffect } from "react";
import type { CasePage } from "./types";
type Tool = {
  name: string;
  description: string;
  inputSchema: object;
  annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
  execute: (input: unknown) => Promise<unknown>;
};
type Context = {
  registerTool: (
    tool: Tool,
    options: { signal: AbortSignal },
  ) => void | Promise<void>;
};
export function useCaseTool(refresh: () => Promise<CasePage | null>) {
  useEffect(() => {
    const context = (document as Document & { modelContext?: Context })
      .modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      void Promise.resolve(
        context.registerTool(
          {
            name: "refresh_visible_cases",
            description:
              "Reload the current Avoirly case-list page and return the visible statuses and currency-separated potential credits. Does not create, analyze, send, close or delete cases.",
            inputSchema: {
              type: "object",
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            async execute(input) {
              if (
                !input ||
                typeof input !== "object" ||
                Array.isArray(input) ||
                Object.keys(input).length
              )
                throw new Error("Expected an empty object.");
              if (lifecycle.signal.aborted)
                throw new Error("The cases page is no longer active.");
              const data = await refresh();
              if (!data) throw new Error("The local API is unavailable.");
              return {
                offset: data.offset,
                cases: data.items.map(
                  ({ id, status, currency, potential_credit_net }) => ({
                    id,
                    status,
                    currency,
                    potential_credit_net,
                  }),
                ),
                potential_credit_by_currency: data.potential_credit_by_currency,
              };
            },
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {
        /* Optional browser capability; normal UI remains available. */
      });
    } catch {
      /* Unsupported browser registration must not break the interface. */
    }
    return () => lifecycle.abort();
  }, [refresh]);
}
