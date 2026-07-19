"use client";

import { useEffect, useState } from "react";
import { ApiError, submitAdminTicket, submitTicket } from "@/lib/api";
import type { GradingResult, Ticket } from "@/lib/types";
import { isAdminResult } from "@/lib/types";

interface TicketResolutionWorkspaceProps {
  ticket: Ticket;
  /** Which submit endpoint (and reward currency) this ticket belongs to. */
  mode?: "learner" | "admin";
  onClose: () => void;
  /** Fired after a graded response comes back (pass or fail) so the parent
   * dashboard can update its own XP/points state without a full refetch. */
  onResolved?: (result: GradingResult) => void;
}

const SEVERITY_STYLES: Record<Ticket["severity"], string> = {
  Low: "border-success/30 bg-success/10 text-success",
  Incident: "border-warning/30 bg-warning/10 text-warning",
  Catastrophic: "border-danger/30 bg-danger/10 text-danger",
};

/** Every ticket's `logs_context` carries these two keys by convention (see
 * app/tickets_db.py) so this panel can render generically across all 7
 * tickets without special-casing each scenario's data shape. */
function readTargetHost(ticket: Ticket): string {
  const value = ticket.logs_context.target_host;
  return typeof value === "string" ? value : "UNKNOWN-HOST";
}

function readRawLog(ticket: Ticket): string {
  const value = ticket.logs_context.raw_log;
  return typeof value === "string" ? value : JSON.stringify(ticket.logs_context, null, 2);
}

function toggleInList(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

/**
 * The ticket resolution workspace -- split-screen incident detail (left) +
 * a diagnostic resolution form (right). There is no code editor here: a
 * ticket is closed the way a real Help Desk / IT Support agent closes one
 * in a system like ServiceNow or Zendesk -- diagnose the root cause, select
 * the correct resolution action(s), and write a resolution note.
 *
 * State management:
 *   - `rootCause`: the single selected radio option.
 *   - `resolutionActions`: the set of selected checkbox options.
 *   - `resolutionNotes`: the free-text resolution summary.
 *     All three reset whenever `ticket.id` changes so switching tickets
 *     never leaks a previous ticket's in-progress answers (parents should
 *     also pass `key={ticket.id}` when rendering this, but the effect below
 *     is a defensive backstop either way).
 *   - `isSubmitting` / `result` / `error`: track one grading round trip.
 *     `result` is the structured pass/fail response from the grader;
 *     `error` is a transport-level failure (network/auth), kept distinct so
 *     the UI can tell "your diagnosis is wrong" apart from "the request failed".
 */
export default function TicketResolutionWorkspace({
  ticket,
  mode = "learner",
  onClose,
  onResolved,
}: TicketResolutionWorkspaceProps) {
  const [rootCause, setRootCause] = useState<string>("");
  const [resolutionActions, setResolutionActions] = useState<string[]>([]);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<GradingResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRootCause("");
    setResolutionActions([]);
    setResolutionNotes("");
    setResult(null);
    setError(null);
  }, [ticket.id]);

  async function handleSubmit() {
    setIsSubmitting(true);
    setError(null);
    try {
      const form = { root_cause: rootCause, resolution_actions: resolutionActions, resolution_notes: resolutionNotes };
      const gradingResult = mode === "admin" ? await submitAdminTicket(ticket.id, form) : await submitTicket(ticket.id, form);
      setResult(gradingResult);
      onResolved?.(gradingResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed -- could not reach the ITC server.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const rewardAmount = result ? (isAdminResult(result) ? result.infra_points_awarded : result.xp_awarded) : 0;
  const rewardLabel = mode === "admin" ? "Infrastructure Stability Points" : "XP";
  const targetHost = readTargetHost(ticket);
  const rawLog = readRawLog(ticket);
  const canSubmit = rootCause.length > 0 && resolutionNotes.trim().length > 0 && !isSubmitting;

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-panel">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-3">
          <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${SEVERITY_STYLES[ticket.severity]}`}>
            {ticket.severity}
          </span>
          <h2 className="text-sm font-semibold text-gray-100">{ticket.title}</h2>
        </div>
        <button
          onClick={onClose}
          aria-label="Close workspace"
          className="rounded-md px-2 py-1 text-xs text-gray-500 transition hover:bg-panel-raised hover:text-gray-200"
        >
          ✕ Close
        </button>
      </div>

      {/* Split-screen body */}
      <div className="grid flex-1 grid-cols-1 divide-y divide-border overflow-hidden md:grid-cols-2 md:divide-x md:divide-y-0">
        {/* Left: enterprise help-desk ticket detail */}
        <div className="itc-scroll overflow-y-auto px-5 py-4">
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1.5 border-b border-border-soft pb-4 font-mono text-xs sm:grid-cols-2">
            <div className="flex justify-between gap-2 sm:block">
              <dt className="text-gray-500">SOURCE DEPT</dt>
              <dd className="text-gray-200">{ticket.department}</dd>
            </div>
            <div className="flex justify-between gap-2 sm:block">
              <dt className="text-gray-500">TARGET MACHINE/IP</dt>
              <dd className="truncate text-gray-200">{targetHost}</dd>
            </div>
          </dl>

          <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-gray-300">{ticket.problem_description}</p>

          <p className="mt-6 text-xs font-medium uppercase tracking-wide text-gray-500">Raw IT / Network Log</p>
          <pre className="itc-scroll mt-2 max-h-72 overflow-auto rounded-lg border border-border-soft bg-panel-raised p-3 font-mono text-xs text-gray-400">
            {rawLog}
          </pre>

          {Object.keys(ticket.validation_criteria).length > 0 && (
            <>
              <p className="mt-6 text-xs font-medium uppercase tracking-wide text-gray-500">Acceptance Criteria</p>
              <ul className="mt-2 space-y-1.5">
                {(ticket.validation_criteria.checks as string[] | undefined)?.map((check, idx) => (
                  <li key={idx} className="flex gap-2 text-sm text-gray-400">
                    <span className="text-accent">▸</span>
                    {check}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        {/* Right: the resolution form -- no code, exactly how a real Help
            Desk ticketing system closes a case. */}
        <div className="flex flex-col overflow-hidden">
          <div className="itc-scroll flex-1 space-y-6 overflow-y-auto px-5 py-4">
            {/* Root cause: single-select */}
            <fieldset>
              <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                Root Cause <span className="text-accent">(select one)</span>
              </legend>
              <div className="space-y-2">
                {ticket.root_cause_options.map((option) => (
                  <label
                    key={option}
                    className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-300 transition hover:border-accent/40"
                  >
                    <input
                      type="radio"
                      name={`root-cause-${ticket.id}`}
                      value={option}
                      checked={rootCause === option}
                      onChange={() => setRootCause(option)}
                      className="mt-0.5 accent-accent"
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {/* Resolution actions: multi-select */}
            <fieldset>
              <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                Resolution Action(s) <span className="text-accent">(select all that apply)</span>
              </legend>
              <div className="space-y-2">
                {ticket.resolution_options.map((option) => (
                  <label
                    key={option}
                    className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-300 transition hover:border-accent/40"
                  >
                    <input
                      type="checkbox"
                      value={option}
                      checked={resolutionActions.includes(option)}
                      onChange={() => setResolutionActions((prev) => toggleInList(prev, option))}
                      className="mt-0.5 accent-accent"
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {/* Resolution notes */}
            <div>
              <label
                htmlFor={`resolution-notes-${ticket.id}`}
                className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-500"
              >
                Resolution Summary <span className="text-accent">(required to close)</span>
              </label>
              <textarea
                id={`resolution-notes-${ticket.id}`}
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                rows={4}
                className="w-full resize-none rounded-lg border border-border-soft bg-panel-raised px-3 py-2 text-sm text-gray-200 outline-none transition focus:border-accent focus:ring-1 focus:ring-accent"
                placeholder="Summarize the diagnosis and steps taken, as you would in a customer-facing ticket note…"
              />
            </div>
          </div>

          <div className="border-t border-border bg-panel px-5 py-3">
            {error && (
              <p role="alert" className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}

            {result && (
              <div
                role="status"
                className={`mb-3 rounded-lg border px-3 py-2.5 text-sm ${
                  result.passed ? "border-success/30 bg-success/10 text-success" : "border-danger/30 bg-danger/10 text-danger"
                }`}
              >
                <p className="font-medium">
                  {result.passed ? "✓ Resolved" : "✗ Not resolved"} — {result.message}
                </p>
                {result.details.length > 0 && (
                  <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs opacity-90">
                    {result.details.map((detail, idx) => (
                      <li key={idx}>{detail}</li>
                    ))}
                  </ul>
                )}
                {rewardAmount > 0 && (
                  <p className="mt-2 font-mono text-xs text-accent">
                    +{rewardAmount} {rewardLabel}
                  </p>
                )}
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-void transition hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSubmitting ? "Submitting…" : mode === "admin" ? "Approve & Close" : "Resolve Ticket"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
