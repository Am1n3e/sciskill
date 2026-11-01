// This module is checked out from the default branch, never from the PR.
// It reads GitHub API metadata only; it does not download or execute artifacts.
const MARKER = '<!-- paper-diff-preview -->';
const html = text => text.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

module.exports = async function publish({github, context, core, workflow = '.github/workflows/paper-diff.yml', botLogin = 'github-actions[bot]'}) {
  const {owner, repo} = context.repo;
  const eventRun = context.payload.workflow_run;
  const {data: run} = await github.rest.actions.getWorkflowRun({owner, repo, run_id: eventRun.id});
  if (run.event !== 'pull_request' || run.path !== workflow
      || run.repository.id !== context.payload.repository.id || run.status !== 'completed'
      || run.run_attempt !== eventRun.run_attempt || run.conclusion === 'cancelled') {
    core.info('Ignoring unrelated, unfinished, cancelled, or superseded workflow run.');
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
    if (!eligible(await current())) continue;
    const runUrl = `${context.serverUrl}/${owner}/${repo}/actions/runs/${run.id}`;
    const lines = [MARKER, '### Paper preview', '',
      `Commit: [\`${run.head_sha.slice(0, 12)}\`](${context.serverUrl}/${owner}/${repo}/commit/${run.head_sha})`, ''];
    if (run.conclusion === 'success') {
      const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts,
        {owner, repo, run_id: run.id, per_page: 100});
      const find = prefix => artifacts.find(a => a.name === `${prefix}-pr-${pull_number}-${run.head_sha}` && !a.expired);
      const diff = find('paper-diff');
      const clean = find('paper');
      if (diff && clean) {
        lines.push(`[Download PDF with changes](${runUrl}/artifacts/${diff.id}) · [Download clean PDF](${runUrl}/artifacts/${clean.id})`, '',
          'Compared with the PR merge base. Artifacts are retained for 30 days.');
        const files = await github.paginate(github.rest.pulls.listFiles,
          {owner, repo, pull_number, per_page: 100});
        const figures = files.filter(f => /\.(pdf|png|jpe?g|svg|webp|gif|eps)$/i.test(f.filename));
        if (figures.length) {
          lines.push('', 'Changed figures (image contents may not be highlighted):');
          for (const file of figures) lines.push(`- <code>${html(file.filename)}</code> (${file.status})`);
        }
      } else {
        lines.push('The PDF artifacts are unavailable. Check the workflow run below.');
      }
    } else {
      lines.push(`Paper diff generation failed (${run.conclusion}). Check the workflow run below.`);
    }
    lines.push('', `[View workflow run and logs](${runUrl})`);
    const comments = await github.paginate(github.rest.issues.listComments,
      {owner, repo, issue_number: pull_number, per_page: 100});
    const previous = comments.find(c => c.user?.login === botLogin && c.body?.startsWith(MARKER));
    // Re-check after API reads in case another commit arrived during publication.
    if (!eligible(await current())) continue;
    const body = lines.join('\n');
    if (previous) {
      await github.rest.issues.updateComment({owner, repo, comment_id: previous.id, body});
    } else {
      await github.rest.issues.createComment({owner, repo, issue_number: pull_number, body});
    }
  }
};
