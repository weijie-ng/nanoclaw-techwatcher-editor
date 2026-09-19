/**
 * `findParentMessagingGroup` — the sub-conversation ancestry rule.
 *
 * There is no parent/child column: a sub-conversation (a Telegram forum
 * topic, and anything shaped like one) is identified by its platform id
 * EXTENDING its chat's at a delimiter boundary. Two consumers depend on the
 * exact boundary semantics — the router, which refuses to auto-create a row
 * under a denied chat and inherits the chat's unknown_sender_policy, and
 * topic-spawn, which refuses to spawn a topic from inside a topic. A
 * false positive silently swallows an unrelated chat's traffic; a false
 * negative reopens the escalation loop the router closes.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { initTestDb, closeDb } from './connection.js';
import { runMigrations } from './migrations/index.js';
import { createMessagingGroup, findParentMessagingGroup, setMessagingGroupDeniedAt } from './messaging-groups.js';
import type { MessagingGroup } from '../types.js';

function mg(overrides: Partial<MessagingGroup> & { id: string; platform_id: string }): MessagingGroup {
  return {
    channel_type: 'telegram',
    instance: 'telegram',
    name: null,
    is_group: 1,
    unknown_sender_policy: 'request_approval',
    denied_at: null,
    created_at: new Date().toISOString(),
    ...overrides,
  } as MessagingGroup;
}

beforeEach(async () => {
  await runMigrations(await initTestDb());
});

afterEach(async () => {
  await closeDb();
});

describe('findParentMessagingGroup', () => {
  it('finds the chat a topic id extends', async () => {
    await createMessagingGroup(mg({ id: 'mg-chat', platform_id: 'telegram:-1001' }));

    expect((await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001:42'))?.id).toBe('mg-chat');
  });

  it('does not treat a numeric sibling as a parent', async () => {
    // 'telegram:-100' is a STRING prefix of 'telegram:-1001', but not at a
    // delimiter boundary — two unrelated chats.
    await createMessagingGroup(mg({ id: 'mg-other', platform_id: 'telegram:-100' }));

    expect(await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001')).toBeUndefined();
  });

  it('is not its own parent', async () => {
    await createMessagingGroup(mg({ id: 'mg-chat', platform_id: 'telegram:-1001' }));

    expect(await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001')).toBeUndefined();
  });

  it('returns the NEAREST ancestor when both a chat and a topic are registered', async () => {
    await createMessagingGroup(mg({ id: 'mg-chat', platform_id: 'telegram:-1001' }));
    await createMessagingGroup(mg({ id: 'mg-topic', platform_id: 'telegram:-1001:42' }));

    expect((await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001:42:7'))?.id).toBe('mg-topic');
  });

  it('ignores a sibling adapter instance — a different bot identity', async () => {
    await createMessagingGroup(mg({ id: 'mg-chat', platform_id: 'telegram:-1001', instance: 'telegram-second' }));

    expect(await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001:42')).toBeUndefined();
    expect((await findParentMessagingGroup('telegram', 'telegram-second', 'telegram:-1001:42'))?.id).toBe('mg-chat');
  });

  it("carries the parent's decisions, not just its identity", async () => {
    await createMessagingGroup(mg({ id: 'mg-chat', platform_id: 'telegram:-1001', unknown_sender_policy: 'public' }));
    await setMessagingGroupDeniedAt('mg-chat', '2026-08-12T00:00:00.000Z');

    const parent = await findParentMessagingGroup('telegram', 'telegram', 'telegram:-1001:42');
    expect(parent?.denied_at).toBe('2026-08-12T00:00:00.000Z');
    expect(parent?.unknown_sender_policy).toBe('public');
  });

  it('supports path-shaped sub-conversation ids too', async () => {
    await createMessagingGroup(
      mg({ id: 'mg-repo', channel_type: 'github', instance: 'github', platform_id: 'github:o/r' }),
    );

    expect((await findParentMessagingGroup('github', 'github', 'github:o/r/issues/12'))?.id).toBe('mg-repo');
  });
});
