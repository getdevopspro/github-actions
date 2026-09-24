const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');

const isSha = value => typeof value === 'string' && /^[0-9a-f]{40}$/.test(value) && !/^0+$/.test(value);

function resolveReference(context, directory) {
  const git = (...args) => {
    try {
      return execFileSync('git', args, {cwd: directory, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe']}).trim();
    } catch {
      return '';
    }
  };
  const tested = git('rev-parse', '--verify', 'HEAD');
  // Raw commit parents remain available even at a shallow checkout boundary.
  const parents = isSha(tested) ? git('cat-file', '-p', tested).split('\n\n', 1)[0].split('\n')
    .filter(line => line.startsWith('parent ')).map(line => line.slice(7)).filter(isSha) : [];
  const event = context.payload;
  let sha = '';
  let branch = '';
  if (context.eventName === 'pull_request' && event.pull_request) {
    const {base, head} = event.pull_request;
    branch = base.ref;
    if (tested === head.sha && isSha(base.sha)) {
      sha = git('merge-base', base.sha, tested);
    } else if (tested === context.sha) {
      if (parents.length === 2 && parents[1] === head.sha) sha = parents[0];
    }
  } else if (context.ref?.startsWith('refs/heads/')) {
    branch = context.ref.slice(11);
    if (context.eventName === 'push' && !event.deleted && tested === event.after) sha = event.before;
    else if (['schedule', 'workflow_dispatch'].includes(context.eventName) && tested === context.sha) {
      sha = parents[0];
    }
  }
  const commits = isSha(sha)
    ? [...new Set([sha, ...git('rev-list', '--first-parent', '--max-count=100', sha).split('\n').filter(isSha)])].slice(0, 100)
    : [];
  return {branch, commits};
}

async function find({github, context, core}) {
  const env = process.env;
  if (!['true', 'false'].includes(env.BASELINE_RESOLVE_ONLY || 'false')) throw new Error('resolve-only must be true or false');
  const reference = env.BASELINE_REFERENCE ? JSON.parse(env.BASELINE_REFERENCE) : resolveReference(context, env.BASELINE_CHECKOUT);
  if (!reference || typeof reference.branch !== 'string' || /[\r\n\0]/.test(reference.branch) ||
      !Array.isArray(reference.commits) || reference.commits.length > 100 ||
      reference.commits.some(sha => !isSha(sha)) || (reference.commits.length && !reference.branch.trim())) {
    throw new Error('reference must contain a branch and an ordered array of up to 100 commit SHAs');
  }
  core.setOutput('reference', reference);
  if (env.BASELINE_RESOLVE_ONLY === 'true') return;
  if (!env.BASELINE_ARTIFACT?.trim() || !env.BASELINE_WORKFLOW?.trim()) {
    throw new Error('artifact-name and workflow must be nonempty');
  }
  if (!['true', 'false'].includes(env.BASELINE_ALLOW_ANCESTOR)) throw new Error('allow-ancestor must be true or false');
  if (!['success', 'any'].includes(env.BASELINE_CONCLUSION)) throw new Error('run-conclusion must be success or any');
  const root = env.BASELINE_PATH
    ? path.resolve(env.BASELINE_CHECKOUT, env.BASELINE_PATH)
    : fs.mkdtempSync(path.join(env.RUNNER_TEMP || os.tmpdir(), 'build-baseline-'));
  if (env.BASELINE_PATH) {
    // Never mix a new lookup with old results or overwrite repository files.
    fs.mkdirSync(path.dirname(root), {recursive: true});
    fs.mkdirSync(root);
  }
  core.setOutput('root', root);
  const {branch, commits} = reference;
  let result = {status: 'unavailable', requested_sha: commits[0] || '', reason: 'No reference revision is available for this checkout and event'};
  if (branch && commits.length) {
    try {
      const distance = new Map(commits.map((sha, index) => [sha, index]));
      const findRun = async (query, allowed) => {
        const {data} = await github.rest.actions.listWorkflowRuns({
          ...context.repo, workflow_id: env.BASELINE_WORKFLOW, branch, per_page: 100, ...query,
        });
        return data.workflow_runs.filter(run =>
          run.status === 'completed' && (env.BASELINE_CONCLUSION === 'any' || run.conclusion === 'success') &&
          run.head_branch === branch && run.id !== context.runId && !run.event.startsWith('pull_request') && allowed.has(run.head_sha),
        ).sort((a, b) => distance.get(a.head_sha) - distance.get(b.head_sha) ||
          Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)[0];
      };
      let run = await findRun({head_sha: commits[0]}, new Set([commits[0]]));
      if (!run && env.BASELINE_ALLOW_ANCESTOR === 'true' && commits.length > 1) run = await findRun({}, distance);
      result.reason = 'No eligible baseline run found in the searched history';
      if (run) {
        const {data} = await github.rest.actions.listWorkflowRunArtifacts({
          ...context.repo, run_id: run.id, name: env.BASELINE_ARTIFACT, per_page: 100,
        });
        result.reason = 'The selected baseline run has no available artifact';
        if (data.artifacts.some(artifact => artifact.name === env.BASELINE_ARTIFACT && !artifact.expired)) {
          result = {
            status: run.head_sha === commits[0] ? 'exact' : 'approximate', requested_sha: commits[0],
            sha: run.head_sha, run_id: run.id, run_url: run.html_url, created_at: run.created_at,
          };
          core.setOutput('run-id', run.id);
        }
      }
    } catch (error) {
      result.reason = `Baseline lookup failed (HTTP ${error.status ?? 'unknown'})`;
    }
  }
  core.setOutput('baseline-result', result);
}

function finish({core}) {
  const result = JSON.parse(process.env.BASELINE_RESULT);
  if (result.status !== 'unavailable' && process.env.BASELINE_DOWNLOAD_OUTCOME !== 'success') {
    result.status = 'unavailable';
    result.reason = 'Baseline artifact download failed';
  }
  const available = result.status !== 'unavailable';
  // Keep metadata portable when the bundle is downloaded on another runner.
  result.path = available ? 'artifacts' : '';
  const metadata = path.join(process.env.BASELINE_ROOT, 'metadata.json');
  fs.writeFileSync(metadata, JSON.stringify(result, null, 2) + '\n');
  for (const [key, value] of Object.entries({
    status: result.status, path: available ? path.join(process.env.BASELINE_ROOT, result.path) : '', 'metadata-file': metadata, 'requested-sha': result.requested_sha,
    sha: available ? result.sha : '', 'run-id': available ? result.run_id : '', 'run-url': available ? result.run_url : '',
  })) core.setOutput(key, value);
  if (!available) {
    if (result.requested_sha) core.warning(result.reason);
    else core.info(result.reason);
  } else if (result.status === 'approximate') core.notice('Baseline uses an earlier ancestor; comparisons are approximate');
}

module.exports = {resolveReference, find, finish};
