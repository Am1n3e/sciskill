// Metadata-only cleanup: validate the merged PR and each artifact's source run.
const MARKER = '<!-- paper-diff-preview -->';

module.exports = async function cleanup({github, context, core, pullNumber,
  workflow = '.github/workflows/paper-diff.yml', botLogin = 'github-actions[bot]'}) {
  if (!Number.isSafeInteger(pullNumber) || pullNumber < 1) {
    throw new Error('A positive pull request number is required for cleanup.');
  }
  const {owner, repo} = context.repo;
  const repositoryId = context.payload.repository.id;
  const {data: pr} = await github.rest.pulls.get({owner, repo, pull_number: pullNumber});
  if (pr.state !== 'closed' || pr.merged !== true || pr.base.repo.id !== repositoryId) {
    core.info('Cleanup applies only to merged pull requests in this repository.');
    return;
  }

  // Finish pagination before deletion so removing an item cannot shift later pages.
  const artifacts = await github.paginate(github.rest.actions.listArtifactsForRepo,
    {owner, repo, per_page: 100});
  const namePattern = new RegExp(`^paper(?:-diff)?-pr-${pullNumber}-([0-9a-f]{40})$`);
  const verifiedRuns = new Map();
  let deleted = 0;
  for (const artifact of artifacts) {
    const match = namePattern.exec(artifact.name);
    if (!match) continue;
    const runId = artifact.workflow_run?.id;
    if (!Number.isSafeInteger(runId)) throw new Error('Preview artifact is missing workflow run metadata.');
    if (!verifiedRuns.has(runId)) {
      let run;
      try {
        ({data: run} = await github.rest.actions.getWorkflowRun({owner, repo, run_id: runId}));
      } catch (error) {
        if (error.status !== 404) throw error;
      }
      let verified = run?.event === 'pull_request' && run.path === workflow
        && run.repository?.id === repositoryId;
      if (verified) {
        const associations = run.pull_requests.length ? run.pull_requests
          : await github.paginate(github.rest.repos.listPullRequestsAssociatedWithCommit,
            {owner, repo, commit_sha: run.head_sha, per_page: 100});
        verified = associations.some(candidate => candidate.number === pullNumber);
      }
      verifiedRuns.set(runId, verified ? run : null);
    }
    if (verifiedRuns.get(runId)?.head_sha !== match[1]) continue;
    try {
      await github.rest.actions.deleteArtifact({owner, repo, artifact_id: artifact.id});
      deleted++;
    } catch (error) {
      if (error.status !== 404) throw error;
    }
  }

  const comments = await github.paginate(github.rest.issues.listComments,
    {owner, repo, issue_number: pullNumber, per_page: 100});
  const body = [MARKER, '### PR merged — preview PDFs removed', '',
    'The preview PDFs have been deleted.', '',
    `[View checks and workflow logs](${context.serverUrl}/${owner}/${repo}/pull/${pullNumber}/checks)`].join('\n');
  for (const comment of comments) {
    if (comment.user?.login === botLogin && comment.body?.startsWith(MARKER) && comment.body !== body) {
      await github.rest.issues.updateComment({owner, repo, comment_id: comment.id, body});
    }
  }
  core.info(`Removed ${deleted} preview artifact(s) for PR #${pullNumber}.`);
};
