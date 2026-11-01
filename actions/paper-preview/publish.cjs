// This Action runs in a trusted workflow and reads GitHub metadata only.
const cleanup = require('./cleanup.cjs');
const MARKER = '<!-- paper-diff-preview -->';
const html = text => text.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

module.exports = async function publish({github, context, core, workflow = '.github/workflows/paper-diff.yml', botLogin = 'github-actions[bot]'}) {
  const {owner, repo} = context.repo;
  const eventRun = context.payload.workflow_run;
  const {data: run} = await github.rest.actions.getWorkflowRun({owner, repo, run_id: eventRun.id});
  if (run.event !== 'pull_request' || run.path !== workflow
      || run.repository.id !== context.payload.repository.id || run.status !== 'completed'
      || run.run_attempt !== eventRun.run_attempt) {
    core.info('Ignoring unrelated, unfinished, or superseded workflow run.');
    return;
  }
  const candidates = run.pull_requests.length ? run.pull_requests
    : await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit,
      {owner, repo, commit_sha: run.head_sha, per_page: 100});

  for (const candidate of candidates) {
    const pull_number = candidate.number;
    const current = async () => (await github.rest.pulls.get({owner, repo, pull_number})).data;
    const eligible = pr => pr.state === 'open' && pr.base.repo.id === context.payload.repository.id
      && pr.head.sha === run.head_sha && pr.head.repo?.id === run.head_repository?.id;
    const initial = await current();
    if (initial.merged === true) {
      await cleanup({github, context, core, pullNumber: pull_number, workflow, botLogin});
      continue;
    }
    if (!eligible(initial) || run.conclusion === 'cancelled') continue;
    const runUrl = `${context.serverUrl}/${owner}/${repo}/actions/runs/${run.id}`;
    const commit = `[\`${run.head_sha.slice(0, 12)}\`](${context.serverUrl}/${owner}/${repo}/commit/${run.head_sha})`;
    const lines = [MARKER];
    let footer = `Commit: ${commit} · [Build details](${runUrl})`;
    if (run.conclusion === 'success') {
      const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts,
        {owner, repo, run_id: run.id, per_page: 100});
      const find = prefix => artifacts.find(a => a.name === `${prefix}-pr-${pull_number}-${run.head_sha}`
        && !a.expired && Number.isFinite(Date.parse(a.expires_at)));
      const diff = find('paper-diff');
      const clean = find('paper');
      if (diff && clean) {
        lines.push('### Paper PDFs ready for review', '',
          'These PDFs were built automatically from this pull request.', '',
          '| PDF | What it shows |',
          '|---|---|',
          `| [**Review highlighted changes**](${runUrl}/artifacts/${diff.id}) | Changes introduced by this PR: additions in blue, deletions in red. |`,
          `| [**Read the updated paper**](${runUrl}/artifacts/${clean.id}) | The complete paper with all changes applied. |`);
        const expires = new Date(Math.min(Date.parse(diff.expires_at), Date.parse(clean.expires_at)));
        const expiry = new Intl.DateTimeFormat('en-GB', {
          dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
        }).format(expires);
        footer = `Built from ${commit} · Downloads available until ${expiry} UTC · [Build details](${runUrl})`;
        const files = await github.paginate(github.rest.pulls.listFiles,
          {owner, repo, pull_number, per_page: 100});
        const figures = files.filter(f => /\.(pdf|png|jpe?g|svg|webp|gif|eps)$/i.test(f.filename));
        if (figures.length) {
          lines.push('', 'Changed figures (image contents may not be highlighted):');
          for (const file of figures) lines.push(`- <code>${html(file.filename)}</code> (${file.status})`);
        }
      } else {
        lines.push('### Paper PDFs unavailable', '',
          'The PDF downloads are unavailable. Check the build details below.');
      }
    } else {
      lines.push('### Paper PDFs could not be built', '',
        `Paper diff generation failed (${run.conclusion}). Check the build details below.`);
    }
    lines.push('', footer);
    const comments = await github.paginate(github.rest.issues.listComments,
      {owner, repo, issue_number: pull_number, per_page: 100});
    const previous = comments.find(c => c.user?.login === botLogin && c.body?.startsWith(MARKER));
    // Re-check after API reads in case another commit arrived during publication.
    const latest = await current();
    if (latest.merged === true) {
      await cleanup({github, context, core, pullNumber: pull_number, workflow, botLogin});
      continue;
    }
    if (!eligible(latest)) continue;
    const body = lines.join('\n');
    if (previous) {
      await github.rest.issues.updateComment({owner, repo, comment_id: previous.id, body});
    } else {
      await github.rest.issues.createComment({owner, repo, issue_number: pull_number, body});
    }
  }
};
