/**
 * Tests for the pi extension. Node strips the types, so no build step runs here.
 *
 * Run from the repository root with: node --test tests/extension.test.ts
 */

import assert from "node:assert/strict";
import { test } from "node:test";

// Pin the profile before the extension loads, so a user config never skews the run.
process.env.STE_GUARD_PROFILE ??= "default";

const { default: register } = await import("../extensions/ste-guard.ts");

const DIRTY = [
  "Great question. This robust and seamless approach handles the payload for the whole team.",
  "The parser then validates every incoming field against the schema before it writes it.",
  "It logs the field name and the reason whenever the schema check rejects the payload.",
].join(" ");

const CLEAN = [
  "The parser rejects the payload when the schema check fails. It logs the field name.",
  "It also logs the reason for the rejection. The caller then retries the request one time.",
].join(" ");

/** A stand-in for pi that records what the extension asked for. */
function fakePi() {
  const handlers: Record<string, Function> = {};
  const sent: string[] = [];

  const pi = {
    on(event: string, handler: Function) {
      handlers[event] = handler;
    },
    async exec(command: string, args: string[]) {
      const { execFileSync } = await import("node:child_process");
      const stdout = execFileSync(command, args, { encoding: "utf8" });

      return { stdout, stderr: "", code: 0, killed: false };
    },
    sendUserMessage(content: string) {
      sent.push(content);
    },
  };

  return { pi, handlers, sent };
}

function assistantMessage(text: string) {
  return { message: { role: "assistant", content: [{ type: "text", text }] } };
}

async function runTurn(handlers: Record<string, Function>, text: string) {
  handlers.message_end(assistantMessage(text));
  await handlers.agent_end({}, {});
}

test("it registers both handlers", () => {
  const { pi, handlers } = fakePi();
  register(pi as any);

  assert.deepEqual(Object.keys(handlers).sort(), ["agent_end", "message_end"]);
});

test("a clean reply sends nothing", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  await runTurn(handlers, CLEAN);

  assert.equal(sent.length, 0);
});

test("a dirty reply asks for one rewrite", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  await runTurn(handlers, DIRTY);

  assert.equal(sent.length, 1);
  assert.match(sent[0], /STE lint failed/);
  assert.match(sent[0], /Rule 8/);
});

test("it ignores a non-assistant message", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  handlers.message_end({ message: { role: "user", content: [{ type: "text", text: DIRTY }] } });
  await handlers.agent_end({}, {});

  assert.equal(sent.length, 0);
});

test("it reads a plain string content block", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  handlers.message_end({ message: { role: "assistant", content: DIRTY } });
  await handlers.agent_end({}, {});

  assert.equal(sent.length, 1);
});

test("the chain cap stops a stubborn reply from looping", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);

  for (let i = 0; i < 4; i++) {
    await runTurn(handlers, `${DIRTY} Variant ${i}.`);
  }

  assert.equal(sent.length, 2);
});

test("a clean reply resets the chain", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);

  await runTurn(handlers, DIRTY);
  await runTurn(handlers, DIRTY);
  await runTurn(handlers, CLEAN);
  await runTurn(handlers, DIRTY);

  assert.equal(sent.length, 3);
});

test("the off switch disables the check", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  process.env.STE_GUARD_OFF = "1";

  try {
    await runTurn(handlers, DIRTY);
  } finally {
    delete process.env.STE_GUARD_OFF;
  }

  assert.equal(sent.length, 0);
});

test("an empty reply is skipped", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);
  await runTurn(handlers, "   ");

  assert.equal(sent.length, 0);
});

test("a second registration starts with its own chain", async () => {
  const first = fakePi();
  register(first.pi as any);

  await runTurn(first.handlers, DIRTY);
  await runTurn(first.handlers, `${DIRTY} Again.`);

  const second = fakePi();
  register(second.pi as any);

  await runTurn(second.handlers, DIRTY);

  assert.equal(first.sent.length, 2);
  assert.equal(second.sent.length, 1);
});

test("the cap holds until a clean reply clears it", async () => {
  const { pi, handlers, sent } = fakePi();
  register(pi as any);

  for (let i = 0; i < 6; i++) {
    await runTurn(handlers, `${DIRTY} Variant ${i}.`);
  }

  assert.equal(sent.length, 2);
});

test("a checker failure notifies rather than passing in silence", async () => {
  const { pi, handlers, sent } = fakePi();
  const notes: string[] = [];

  pi.exec = async () => {
    throw new Error("python3 not found");
  };

  register(pi as any);
  handlers.message_end(assistantMessage(DIRTY));
  await handlers.agent_end({}, { ui: { notify: (text: string) => notes.push(text) } });

  assert.equal(sent.length, 0);
  assert.ok(notes.some((n) => n.includes("the checker failed")));
});
