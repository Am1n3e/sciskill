const {test} = require('node:test');
const assert = require('node:assert/strict');
const publish = require('./publish.cjs');
const cleanup = require('./cleanup.cjs');

const SHA = 'a'.repeat(40);
const MARKER = '<!-- paper-diff-preview -->';

function fixture(overrides = {}) {
  const run = {
    id: 42, run_attempt: 1, event: 'pull_request', status: 'completed',
    conclusion: 'success', path: '.github/workflows/paper-diff.yml',
    head_sha: SHA, head_repository: {id: 2}, repository: {id: 1},
    pull_requests: [{number: 3}], ...overrides,
  };
  const pr = {number: 3, state: 'open', merged: false, base: {repo: {id: 1}}, head: {sha: SHA, repo: {id: 2}}};
  const comments = [];
  const artifacts = [
    {id: 51, name: `paper-diff-pr-3-${SHA}`, expired: false, expires_at: '2099-12-02T14:30:00Z', workflow_run: {id: 42}},
    {id: 52, name: `paper-pr-3-${SHA}`, expired: false, expires_at: '2099-12-01T14:30:00Z', workflow_run: {id: 42}},
  ];
  const runs = new Map([[42, run]]);
  const deleted = [];
  const files = [{filename: 'content/imgs/plot.png', status: 'modified'}];
  const github = {rest: {
    actions: {
      getWorkflowRun: async ({run_id}) => ({data: runs.get(run_id)}),
      listWorkflowRunArtifacts: async () => artifacts,
      listArtifactsForRepo: async () => [...artifacts],
      deleteArtifact: async ({artifact_id}) => {
        const index = artifacts.findIndex(a => a.id === artifact_id);
        if (index < 0) throw Object.assign(new Error('Not found'), {status: 404});
        deleted.push(artifact_id); artifacts.splice(index, 1);
      },
    },
    pulls: {get: async () => ({data: pr}), listFiles: async () => files},
    repos: {listPullRequestsAssociatedWithCommit: async () => [{number: 3}]},
    issues: {
      listComments: async () => comments,
      createComment: async ({body}) => comments.push({id: 7, body, user: {login: 'github-actions[bot]'}}),
      updateComment: async ({comment_id, body}) => { comments.find(c => c.id === comment_id).body = body; },
    },
  }, paginate: (method, args) => method(args)};
  const context = {repo: {owner: 'owner', repo: 'paper'}, serverUrl: 'https://github.com',
    payload: {repository: {id: 1}, workflow_run: {...run}}};
  return {github, context, run, pr, comments, artifacts, files, runs, deleted};
}

async function run(f) { return publish({github: f.github, context: f.context, core: {info() {}}}); }

test('publishes verified artifact links, head revision, and changed figures', async () => {
  const f = fixture(); await run(f);
  assert.equal(f.comments.length, 1);
  assert.ok(f.comments[0].body.includes('/actions/runs/42/artifacts/51'));
  assert.ok(f.comments[0].body.includes(SHA));
  assert.ok(f.comments[0].body.includes('content/imgs/plot.png'));
});

test('updates one bot comment while preserving human comments', async () => {
  const f = fixture();
  f.comments.push({id: 6, body: MARKER + ' human text', user: {login: 'researcher'}});
  await run(f); const id = f.comments[1].id;
  await run(f);
  assert.equal(f.comments.length, 2);
  assert.equal(f.comments[1].id, id);
  assert.equal(f.comments[0].body, MARKER + ' human text');
});

test('stale heads and closed or unrelated PRs cannot be updated', async () => {
  for (const change of [f => f.pr.head.sha = 'b'.repeat(40), f => f.pr.state = 'closed',
                        f => f.pr.base.repo.id = 99, f => f.pr.head.repo.id = 99]) {
    const f = fixture(); change(f); await run(f); assert.equal(f.comments.length, 0);
  }
});

test('fork runs with empty pull_requests are resolved through GitHub', async () => {
  const f = fixture({pull_requests: []}); await run(f); assert.equal(f.comments.length, 1);
});

test('other workflows and outdated attempts cannot publish', async () => {
  for (const change of [f => f.run.path = '.github/workflows/other.yml',
                        f => f.run.event = 'push', f => f.run.run_attempt = 2]) {
    const f = fixture(); change(f); await run(f); assert.equal(f.comments.length, 0);
  }
});

test('failed builds replace the preview with a failure link', async () => {
  const f = fixture(); await run(f); f.run.conclusion = 'failure'; await run(f);
  assert.equal(f.comments.length, 1);
  assert.ok(f.comments[0].body.includes('failed'));
  assert.ok(!f.comments[0].body.includes('/artifacts/'));
});

test('missing or expired PDFs cannot be reported as successful previews', async () => {
  const f = fixture(); f.artifacts[0].expired = true; await run(f);
  assert.ok(!f.comments[0].body.includes('/artifacts/51'));
  assert.ok(f.comments[0].body.includes('unavailable'));
});


test('a head update during publication prevents a stale comment', async () => {
  const f = fixture(); let reads = 0;
  f.github.rest.pulls.get = async () => {
    const pr = structuredClone(f.pr);
    if (++reads > 1) pr.head.sha = 'b'.repeat(40);
    return {data: pr};
  };
  await run(f); assert.equal(f.comments.length, 0);
});

test('figure filenames are escaped as text', async () => {
  const f = fixture(); f.files[0].filename = 'content/<img src=x>.png';
  await run(f);
  assert.ok(f.comments[0].body.includes('&lt;img src=x&gt;'));
  assert.ok(!f.comments[0].body.includes('<img src=x>'));
});

test('a custom App updates only its own preview comment', async () => {
  const f = fixture();
  f.comments.push({id: 8, body: MARKER + ' old workflow bot', user: {login: 'github-actions[bot]'}});
  f.github.rest.issues.createComment = async ({body}) => f.comments.push({id: 9, body, user: {login: 'sciskill[bot]'}});
  const custom = () => publish({...f, core: {info() {}}, botLogin: 'sciskill[bot]'});
  await custom(); await custom();
  assert.equal(f.comments.length, 2);
  assert.equal(f.comments[0].body, MARKER + ' old workflow bot');
  assert.ok(f.comments[1].body.includes('/artifacts/51'));
});

test('a configured workflow path replaces the default path restriction', async () => {
  const f = fixture({path: '.github/workflows/custom-paper.yml'});
  await publish({...f, core: {info() {}}, workflow: '.github/workflows/custom-paper.yml'});
  assert.equal(f.comments.length, 1);
});

test('the comment uses the earlier PDF expiry from GitHub metadata', async () => {
  const f = fixture(); await run(f);
  assert.ok(f.comments[0].body.includes('1 Dec 2099, 14:30 UTC'));
  assert.ok(!f.comments[0].body.includes('30 days'));
  assert.ok(!f.comments[0].body.includes('2 Dec 2099'));
});

test('missing expiry metadata cannot produce a ready preview', async () => {
  const f = fixture(); delete f.artifacts[0].expires_at;
  await run(f);
  assert.ok(f.comments[0].body.includes('unavailable'));
  assert.ok(!f.comments[0].body.includes('/artifacts/'));
});

function merged(f) { f.pr.state = 'closed'; f.pr.merged = true; return f; }
async function clean(f, options = {}) {
  return cleanup({...f, core: {info() {}}, pullNumber: 3, ...options});
}

test('merge cleanup removes PDFs from every revision and preserves unrelated artifacts and comments', async () => {
  const f = fixture(); await run(f); merged(f);
  const older = 'b'.repeat(40);
  f.runs.set(43, {...f.run, id: 43, head_sha: older});
  f.artifacts.push(
    {id: 53, name: `paper-diff-pr-3-${older}`, workflow_run: {id: 43}},
    {id: 54, name: `paper-pr-3-${older}`, workflow_run: {id: 43}},
    {id: 55, name: `paper-pr-30-${SHA}`, workflow_run: {id: 42}},
    {id: 56, name: 'paper-diff-logs-42-1', workflow_run: {id: 42}},
  );
  f.comments.push({id: 8, body: MARKER + ' human notes', user: {login: 'researcher'}});
  await clean(f);
  assert.deepEqual(f.deleted, [51, 52, 53, 54]);
  assert.deepEqual(f.artifacts.map(a => a.id), [55, 56]);
  assert.ok(f.comments[0].body.includes('PR merged — preview PDFs removed'));
  assert.ok(!f.comments[0].body.includes('/artifacts/'));
  assert.ok(f.comments[0].body.includes('/pull/3/checks'));
  assert.equal(f.comments[1].body, MARKER + ' human notes');
});

test('only a canonically merged PR in this repository can be cleaned', async () => {
  for (const change of [f => {}, f => { f.pr.state = 'closed'; },
    f => { merged(f); f.pr.base.repo.id = 99; }]) {
    const f = fixture(); change(f);
    f.context.payload.pull_request = {number: 3, merged: true};
    await clean(f);
    assert.deepEqual(f.deleted, []); assert.deepEqual(f.comments, []);
  }
});

test('cleanup verifies workflow, repository, PR association and revision before deletion', async () => {
  for (const change of [f => { f.run.path = '.github/workflows/unrelated.yml'; },
    f => { f.run.repository = {id: 99}; }, f => { f.run.event = 'push'; },
    f => { f.run.pull_requests = [{number: 4}]; }, f => { f.run.head_sha = 'b'.repeat(40); }]) {
    const f = merged(fixture()); change(f); await clean(f);
    assert.deepEqual(f.deleted, []);
  }
});

test('fork run associations can be resolved for merged PR cleanup', async () => {
  const f = merged(fixture({pull_requests: []})); await clean(f);
  assert.deepEqual(f.deleted, [51, 52]);
  assert.equal(f.comments.length, 0);
});

test('cleanup is idempotent and tolerates a concurrently removed artifact', async () => {
  const f = fixture(); await run(f); merged(f);
  const remove = f.github.rest.actions.deleteArtifact;
  f.github.rest.actions.deleteArtifact = async args => {
    await remove(args);
    if (args.artifact_id === 51) throw Object.assign(new Error('Already removed'), {status: 404});
  };
  await clean(f); const body = f.comments[0].body; await clean(f);
  assert.equal(f.comments.length, 1); assert.equal(f.comments[0].body, body);
  assert.deepEqual(f.deleted, [51, 52]);
});

test('a deletion error cannot claim the PDFs were removed', async () => {
  const f = fixture(); await run(f); merged(f);
  f.github.rest.actions.deleteArtifact = async () => { throw Object.assign(new Error('Denied'), {status: 403}); };
  await assert.rejects(clean(f), /Denied/);
  assert.ok(f.comments[0].body.includes('/artifacts/51'));
});

test('cleanup updates only comments belonging to the configured App', async () => {
  const f = merged(fixture());
  f.comments.push({id: 8, body: MARKER + ' original bot', user: {login: 'github-actions[bot]'}},
    {id: 9, body: MARKER + ' app preview', user: {login: 'sciskill[bot]'}});
  await clean(f, {botLogin: 'sciskill[bot]'});
  assert.equal(f.comments[0].body, MARKER + ' original bot');
  assert.ok(f.comments[1].body.includes('PR merged'));
});

test('a build finishing after merge cleans its newly uploaded artifacts, including cancelled builds', async () => {
  for (const conclusion of ['success', 'cancelled']) {
    const f = fixture(); await run(f); merged(f); f.run.conclusion = conclusion;
    await run(f);
    assert.deepEqual(f.deleted, [51, 52]);
    assert.ok(f.comments[0].body.includes('PR merged'));
  }
});

test('a merge during publication switches to cleanup instead of posting download links', async () => {
  const f = fixture();
  f.comments.push({id: 7, body: MARKER + ' previous preview', user: {login: 'github-actions[bot]'}});
  f.github.rest.issues.listComments = async () => { merged(f); return f.comments; };
  await run(f);
  assert.deepEqual(f.deleted, [51, 52]);
  assert.ok(f.comments[0].body.includes('PR merged'));
});
