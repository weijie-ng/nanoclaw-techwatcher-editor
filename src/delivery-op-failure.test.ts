/**
 * A permanently-failed queued op (pin/edit/reaction/delete) has no return path
 * to the child — the tool call already returned "queued". notifyOpFailure drops
 * a `system` row into the child's inbox so its next turn sees the failure.
 * Scoped to ops: a failed chat/file send must NOT be re-surfaced (resend loop).
 */
import Database from 'better-sqlite3';
import fs from 'fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The mock factory is hoisted above module init, so it must inline the literal
// path rather than reference TEST_DIR (which would be in its temporal dead zone).
vi.mock('./config.js', async () => {
  const actual = await vi.importActual<typeof import('./config.js')>('./config.js');
  return { ...actual, DATA_DIR: '/tmp/nanoclaw-test-opfailure', GROUPS_DIR: '/tmp/nanoclaw-test-opfailure/groups' };
});

const TEST_DIR = '/tmp/nanoclaw-test-opfailure';

import { inboundDbPath } from './mailbox/sqlite/paths.js';
import { destroySessionMailbox, withMailboxSession } from './session-manager.js';
import { notifyOpFailure } from './delivery.js';

const AG = 'ag-op';
const SID = 'sess-op';

// The agent mailbox factory is registered globally by test-setup.ts; do NOT
// reset it here (that would unregister it and break withMailboxSession).
// destroySessionMailbox clears this session's cached migration state + files
// so each test provisions a fresh inbox under the wiped TEST_DIR.
beforeEach(async () => {
  await destroySessionMailbox(AG, SID);
  if (fs.existsSync(TEST_DIR)) fs.rmSync(TEST_DIR, { recursive: true });
  fs.mkdirSync(TEST_DIR, { recursive: true });
});

afterEach(async () => {
  await destroySessionMailbox(AG, SID);
  if (fs.existsSync(TEST_DIR)) fs.rmSync(TEST_DIR, { recursive: true });
});

/** Read the child's inbox directly (the container is normally the reader). */
function rows() {
  const db = new Database(inboundDbPath(AG, SID), { readonly: true });
  try {
    return db.prepare('SELECT kind, content, trigger FROM messages_in').all() as Array<{
      kind: string;
      content: string;
      trigger: number;
    }>;
  } finally {
    db.close();
  }
}

describe('notifyOpFailure', () => {
  it('writes a non-waking system note for a failed pin op', async () => {
    await withMailboxSession(AG, SID, () => undefined); // provision the session mailbox
    await notifyOpFailure(
      AG,
      SID,
      { id: 'msg-1', content: JSON.stringify({ operation: 'pin', messageId: '-100:530' }) },
      new Error('Telegram pinChatMessage failed: not enough rights to pin a message'),
    );
    const [row] = rows();
    expect(row.kind).toBe('system');
    expect(row.trigger).toBe(0); // context only, no wake
    const c = JSON.parse(row.content);
    expect(c).toMatchObject({ action: 'pin', status: 'failed' });
    expect(c.result).toContain('not enough rights');
  });

  it('ignores a failed chat send (no operation field) — no resend loop', async () => {
    await withMailboxSession(AG, SID, () => undefined);
    await notifyOpFailure(
      AG,
      SID,
      { id: 'msg-2', content: JSON.stringify({ text: 'hello', files: [] }) },
      new Error('network down'),
    );
    expect(rows()).toHaveLength(0);
  });

  it('swallows unparseable content rather than throwing', async () => {
    await withMailboxSession(AG, SID, () => undefined);
    await expect(
      notifyOpFailure(AG, SID, { id: 'msg-3', content: 'not-json' }, new Error('x')),
    ).resolves.toBeUndefined();
    expect(rows()).toHaveLength(0);
  });
});
