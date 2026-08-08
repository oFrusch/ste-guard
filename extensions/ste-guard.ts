/**
 * ste-guard for pi. Checks each assistant reply and asks for one rewrite when a rule fails.
 *
 * pi has no block primitive on an assistant message. The extension therefore sends a
 * follow-up user message, which makes the model regenerate. The Codex target behaves the
 * same way, so all three agents share one mental model.
 *
 * Set STE_GUARD_OFF=1 to disable. The rules live in the Python engine, never here.
 */

import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const HERE = dirname(fileURLToPath(import.meta.url));
const CHECKER = join(HERE, "..", "hooks", "ste-check");

interface Verdict {
  clean: boolean;
  too_short: boolean;
  words: number;
  profile: string;
  hard: string[];
  soft: string[];
  violations: string[];
  max_blocks_per_chain: number;
}

/** Consecutive rewrites asked for. A reply that passes resets it. */
let chain = 0;

/** The last assistant text seen, because agent_end does not carry the message. */
let lastAssistantText = "";

function textOf(message: any): string {
  const content = message?.content;

  if (typeof content === "string") {
    return content;
  }

  if (!Array.isArray(content)) {
    return "";
  }

  return content
    .filter((block: any) => block?.type === "text" && typeof block.text === "string")
    .map((block: any) => block.text)
    .join("\n");
}

function buildPrompt(violations: string[]): string {
  const listed = violations
    .slice(0, 8)
    .map((item) => `  - ${item}`)
    .join("\n");

  return [
    "STE lint failed on your last message. Rewrite it, then stop.",
    "Keep the same content and the same conclusions. Fix only the prose.",
    "",
    listed,
    "",
    "Do not explain the rewrite. Just send the clean version.",
  ].join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("message_end", (event: any) => {
    if (event?.message?.role !== "assistant") {
      return;
    }

    lastAssistantText = textOf(event.message);
  });

  pi.on("agent_end", async (_event: any, ctx: any) => {
    if (process.env.STE_GUARD_OFF) {
      return;
    }

    const draft = lastAssistantText;
    lastAssistantText = "";

    if (!draft.trim()) {
      return;
    }

    // pi.exec has no stdin channel, so the draft travels through a temp file.
    const scratch = mkdtempSync(join(tmpdir(), "ste-guard-"));
    const draftPath = join(scratch, "draft.md");

    let parsed: Verdict;

    try {
      writeFileSync(draftPath, draft);

      const result = await pi.exec("python3", [CHECKER, "--json", draftPath], { timeout: 10_000 });

      parsed = JSON.parse(result.stdout);
    } catch {
      return;
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }

    if (parsed.clean) {
      chain = 0;
      return;
    }

    // The cap stops a stubborn reply from looping. Only a clean reply clears it.
    if (chain >= parsed.max_blocks_per_chain) {
      chain = 0;
      return;
    }

    chain += 1;
    ctx?.ui?.notify?.(`ste-guard: ${parsed.violations.length} violations, asking for a rewrite`, "info");
    pi.sendUserMessage(buildPrompt(parsed.violations), { deliverAs: "followUp" });
  });
}
