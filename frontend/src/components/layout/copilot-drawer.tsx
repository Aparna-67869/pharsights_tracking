"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Loader2, Maximize2, Send, Sparkles, Wrench, X } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CopilotAnswer } from "@/types/api";

interface Turn {
  id: string;
  question: string;
  answer?: CopilotAnswer;
  error?: string;
}

/**
 * Floating Copilot available from every screen. Full conversations live on
 * /copilot; this is the quick-ask surface for the terminal experience.
 */
export function CopilotDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [input, setInput] = React.useState("");
  const [turns, setTurns] = React.useState<Turn[]>([]);

  const suggested = useQuery({
    queryKey: ["copilot-suggested"],
    queryFn: () => api.copilotSuggested(),
    enabled: open,
  });

  const ask = useMutation({
    mutationFn: (question: string) => api.copilotAsk(question, true),
    onSuccess: (data, question) =>
      setTurns((prev) => prev.map((t) => (t.question === question && !t.answer ? { ...t, answer: data } : t))),
    onError: (error: Error, question) =>
      setTurns((prev) => prev.map((t) => (t.question === question && !t.answer ? { ...t, error: error.message } : t))),
  });

  const submit = (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || ask.isPending) return;
    setTurns((prev) => [...prev, { id: `${Date.now()}`, question: trimmed }]);
    setInput("");
    ask.mutate(trimmed);
  };

  return (
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-background/50 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border/70 bg-panel shadow-2xl"
          >
            <header className="flex h-14 items-center gap-2 border-b border-border/70 px-4">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/12 text-primary ring-1 ring-primary/25">
                <Sparkles className="h-4 w-4" />
              </span>
              <div className="flex-1">
                <p className="text-sm font-semibold">AI Copilot</p>
                <p className="text-[10px] text-muted-foreground">Grounded in your platform data</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  onClose();
                  router.push("/copilot");
                }}
                aria-label="Open full copilot"
              >
                <Maximize2 className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close copilot">
                <X className="h-4 w-4" />
              </Button>
            </header>

            <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4">
              {turns.length === 0 ? (
                <div className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Ask about filings, extensions, moieties, expiries or opportunities.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {(suggested.data ?? [
                      "Show new PTE applications this month",
                      "Show patents expiring before 2028",
                      "Show Paragraph IV filings for oncology products",
                    ]).map((question) => (
                      <button
                        key={question}
                        onClick={() => submit(question)}
                        className="rounded-full border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                      >
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                turns.map((turn) => (
                  <div key={turn.id} className="space-y-2">
                    <div className="ml-auto w-fit max-w-[85%] rounded-lg rounded-br-sm bg-primary/15 px-3 py-1.5 text-xs">
                      {turn.question}
                    </div>
                    {turn.error ? (
                      <div className="rounded-lg border border-destructive/30 p-3 text-xs text-destructive">
                        {turn.error}
                      </div>
                    ) : !turn.answer ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
                      </div>
                    ) : (
                      <div className="rounded-lg border border-border/70 bg-surface/50 p-3">
                        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                          <Badge variant="default" className="text-[10px]">
                            <Bot className="h-3 w-3" /> {turn.answer.provider}
                          </Badge>
                          <Badge variant="outline" className="text-[10px]">
                            {turn.answer.intent}
                          </Badge>
                          {turn.answer.tool_calls.length ? (
                            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                              <Wrench className="h-3 w-3" />
                              {turn.answer.tool_calls.length} tools
                            </span>
                          ) : null}
                        </div>
                        <div className="whitespace-pre-wrap text-xs leading-relaxed">{turn.answer.answer}</div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className={cn("border-t border-border/70 p-3")}>
              <div className="flex items-end gap-2">
                <Textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      submit(input);
                    }
                  }}
                  rows={1}
                  placeholder="Ask the copilot…"
                  className="min-h-[40px] resize-none"
                />
                <Button onClick={() => submit(input)} disabled={!input.trim() || ask.isPending} className="h-10 px-3">
                  {ask.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              <p className="mt-1.5 text-[10px] text-muted-foreground">
                Informational only — not legal advice.
              </p>
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}
