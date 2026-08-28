#!/usr/bin/env node
// Small deterministic state store for the postflow listener + approval queue.
// Keeps Claude from hand-editing JSON across turns (error-prone) by giving it
// a tiny CLI with atomic read-modify-write commands.
//
// State shape:
// {
//   "active": boolean,                 // listener on/off, set by /postflow start|stop
//   "current": null | {                // the run currently in flight (research..awaiting-approval)
//     "recordId": string,              // Airtable record id
//     "topic": string,
//     "chatId": string,
//     "messageId": string | null       // telegram message id of the approval prompt
//   },
//   "queue": [ { "topic": string, "chatId": string } ]  // topics submitted while current != null
// }
//
// Usage:
//   node state.mjs get
//   node state.mjs start
//   node state.mjs stop
//   node state.mjs set-current '<json>'
//   node state.mjs clear-current
//   node state.mjs enqueue '<json>'
//   node state.mjs dequeue                (pops+returns front of queue, or "null")

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const stateDir = process.env.POSTFLOW_STATE_DIR || join(__dirname, '..', 'state');
const stateFile = join(stateDir, 'state.json');

function load() {
  if (!existsSync(stateFile)) {
    return { active: false, current: null, queue: [] };
  }
  return JSON.parse(readFileSync(stateFile, 'utf8'));
}

function save(state) {
  mkdirSync(stateDir, { recursive: true });
  writeFileSync(stateFile, JSON.stringify(state, null, 2));
}

const [, , cmd, arg] = process.argv;
const state = load();

switch (cmd) {
  case 'get':
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'start':
    state.active = true;
    save(state);
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'stop':
    state.active = false;
    save(state);
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'set-current':
    state.current = JSON.parse(arg);
    save(state);
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'clear-current':
    state.current = null;
    save(state);
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'enqueue':
    state.queue.push(JSON.parse(arg));
    save(state);
    console.log(JSON.stringify(state, null, 2));
    break;
  case 'dequeue': {
    const next = state.queue.shift() ?? null;
    save(state);
    console.log(JSON.stringify(next));
    break;
  }
  default:
    console.error('Unknown command. Use: get|start|stop|set-current|clear-current|enqueue|dequeue');
    process.exit(1);
}
