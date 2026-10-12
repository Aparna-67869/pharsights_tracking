"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  Loader2,
  Send,
  Sparkles,
  Terminal,
  UserRound,
  Wrench,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CopilotAnswer } from "@/types/api";

interface Turn {
  id: string;
  question: string;
  answer?: CopilotAnswer;
  error?: string;
}

export default function CopilotPage() {
  const params = useSearchParams();
  const [input, setInput] = React.useState("");
  const [useLlm, setUseLlm] = React.useState(true);
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [conversationId, setConversationId] = React.useState<string | undefined>(undefined);

  const suggested = useQuery({ queryKey: ["copilot-suggested"], queryFn: () => api.copilotSuggested() });

  const ask = useMutation({
    mutationFn: (question: string) => api.copilotAsk(question, useLlm, conversationId),
    onSuccess: (data, question) => {
      setTurns((prev) =>
        prev.map((turn) => (turn.question === question && !turn.answer ? { ...turn, answer: data } : turn)),
      );
    },
    onError: (error: Error, question) => {
      setTurns((prev) =>
        prev.map((turn) => (turn.question === question && !turn.answer ? { ...turn, error: error.message } : turn)),
      );
    },
  });

  const submit = (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || ask.isPending) return;
    setTurns((prev) => [...prev, { id: crypto.randomUUID(), question: trimmed }]);
    setInput("");
    ask.mutate(trimmed);
  };

  React.useEffect(() => {
    const seeded = params.get("q");
    if (seeded && turns.length === 0) submit(seeded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <BrainCircuit className="h-5 w-5 text-primary" /> AI Copilot
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask regulatory questions in plain English. Answers are grounded in the platform&apos;s own records via
          tool calls — every response shows exactly which data it used.
        </p>
      </header>

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="space-y-4 xl:col-span-3">
          {turns.length === 0 ? (
            <Card className="p-8">
              <div className="mx-auto max-w-xl text-center">
                <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-primary/12 text-primary ring-1 ring-primary/25">
                  <Sparkles className="h-6 w-6" />
                </span>
                <h2 className="mt-3 text-base font-semibold">What would you like to know?</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  The copilot can compare Orange Book supplements, list new PTE applications, find Paragraph IV
                  filings by therapy area, identify expiring patents and surface generic opportunities.
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {(suggested.data ?? []).slice(0, 6).map((question) => (
                    <button
                      key={question}
                      onClick={() => submit(question)}
                      className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2 text-left text-xs transition-colors hover:bg-muted/50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          ) : (
            turns.map((turn) => <TurnView key={turn.id} turn={turn} />)
          )}

          {ask.isPending ? (
            <Card className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Analysing platform records…
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">Reasoning mode</span>
                <button
                  onClick={() => setUseLlm((value) => !value)}
                  className={cn(
                    "relative h-5 w-9 rounded-full transition-colors",
                    useLlm ? "bg-primary" : "bg-muted",
                  )}
                  aria-label="Toggle LLM reasoning"
                >
                  <span
                    className={cn(
                      "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      useLlm ? "translate-x-4.5 left-0.5" : "left-0.5",
                    )}
                  />
                </button>
              </div>
              <p className="text-[11px] text-muted-foreground">
                {useLlm
                  ? "Uses the configured LLM to narrate results, falling back to the deterministic engine if unavailable."
                  : "Deterministic mode — no LLM. Fast, fully offline, grounded in tool output only."}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-2 pt-4 text-xs">
              <p className="font-medium">Example questions</p>
              {(suggested.data ?? []).map((question) => (
                <button
                  key={question}
                  onClick={() => submit(question)}
                  className="block w-full rounded-md px-2 py-1.5 text-left text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
                >
                  {question}
                </button>
              ))}
            </CardContent>
          </Card>

          {turns.length > 0 ? (
            <Button variant="outline" size="sm" className="w-full" onClick={() => { setTurns([]); setConversationId(undefined); }}>
              New conversation
            </Button>
          ) : null}
        </div>
      </div>

      <div className="sticky bottom-0 z-20">
        <Card className="glass-strong p-3">
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
              placeholder="Ask about FTF filings, PTE extensions, active moieties, Orange Book changes, expiring patents…"
              className="min-h-[44px] resize-none"
              rows={1}
            />
            <Button onClick={() => submit(input)} disabled={!input.trim() || ask.isPending} className="h-11 px-4">
              {ask.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            Answers are generated from platform data and are not legal advice. Press Enter to send, Shift+Enter for
            a new line.
          </p>
        </Card>
      </div>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-muted/60">
          <UserRound className="h-3.5 w-3.5" />
        </span>
        <p className="pt-1 text-sm font-medium">{turn.question}</p>
      </div>

      {turn.error ? (
        <Card className="border-destructive/30 p-4 text-sm text-destructive">{turn.error}</Card>
      ) : !turn.answer ? (
        <Card className="flex items-center gap-2 p-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="space-y-3 pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="default">
                <Bot className="h-3 w-3" /> {turn.answer.provider}
              </Badge>
              <Badge variant="outline">intent: {turn.answer.intent}</Badge>
              <Badge variant="secondary">{turn.answer.model}</Badge>
              <span className="text-[10px] text-muted-foreground">{turn.answer.latency_ms} ms</span>
            </div>

            <div className="whitespace-pre-wrap text-sm leading-relaxed">{turn.answer.answer}</div>

            {turn.answer.tool_calls.length ? (
              <details className="group rounded-lg border border-border/70 bg-surface-muted/40 p-3">
                <summary className="flex cursor-pointer items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                  <Wrench className="h-3 w-3" />
                  {turn.answer.tool_calls.length} tool call
                  {turn.answer.tool_calls.length === 1 ? "" : "s"} used to ground this answer
                </summary>
                <div className="mt-2 space-y-2">
                  {turn.answer.tool_calls.map((call, index) => (
                    <div key={index} className="rounded-md border border-border/60 bg-card/60 p-2">
                      <p className="flex items-center gap-1.5 font-mono text-[11px] text-primary">
                        <Terminal className="h-3 w-3" />
                        {call.name}
                        {call.error ? <Badge variant="destructive">error</Badge> : <CheckCircle2 className="h-3 w-3 text-success" />}
                      </p>
                      <pre className="scrollbar-thin mt-1 max-h-40 overflow-auto text-[10px] text-muted-foreground">
                        {JSON.stringify(call.arguments, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
