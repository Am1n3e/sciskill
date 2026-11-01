const {test} = require('node:test');
const assert = require('node:assert/strict');
const publish = require('./publish.cjs');

const SHA = 'a'.repeat(40);
const MARKER = '<!-- paper-diff-preview -->';

function fixture(overrides = {}) {
  const run = {
    id: 42, run_attempt: 1, event: 'pull_request', status: 'completed',
    conclusion: 'success', path: '.github/workflows/paper-diff.yml',
    head_sha: SHA, head_repository: {id: 2}, repository: {id: 1},
    pull_requests: [{number: 3}], ...overrides,
  };
  const pr = {number: 3, state: 'open', base: {repo: {id: 1}}, head: {sha: SHA, repo: {id: 2}}};
  const comments = [];
  const artifacts = [
    {id: 51, name: `paper-diff-pr-3-${SHA}`, expired: false},
    {id: 52, name: `paper-pr-3-${SHA}`, expired: false},
  ];
  const files = [{filename: 'content/imgs/plot.png', status: 'modified'}];
  const github = {rest: {
    actions: {
      getWorkflowRun: async () => ({data: run}),
      listWorkflowRunArtifacts: async () => artifacts,
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
  return {github, context, run, pr, comments, artifacts, files};
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
