const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {test} = require('node:test');
const baseline = require('../build/baseline/index.js');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'baseline-test-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const repo = path.join(root, 'repo');
  fs.mkdirSync(repo);
  const git = (...args) => execFileSync('git', ['-c', 'user.name=CI Fixture', '-c', 'user.email=ci@example.invalid', ...args], {
    cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
  const commit = name => {
    fs.writeFileSync(path.join(repo, name), name);
    git('add', name); git('commit', '-qm', name);
    return git('rev-parse', 'HEAD');
  };
  git('init', '-q', '-b', 'main');
  const older = commit('older');
  const base = commit('base');
  git('checkout', '-qb', 'feature');
  const head = commit('feature');
  git('checkout', '-q', 'main');
  const advanced = commit('advanced');
  git('merge', '-q', '--no-ff', '--no-edit', 'feature');
  const merge = git('rev-parse', 'HEAD');
  const context = {repo: {owner: 'example', repo: 'project'}, sha: merge, runId: 100,
    ref: 'refs/pull/1/merge', eventName: 'pull_request',
    payload: {pull_request: {base: {ref: 'main', sha: advanced}, head: {sha: head}}}};
  return {root, repo, git, older, base, head, advanced, merge, context};
}

const run = (id, sha, overrides = {}) => ({
  id, head_sha: sha, head_branch: 'main', status: 'completed', conclusion: 'success',
  event: 'push', created_at: '2026-01-01T00:00:00Z', html_url: `https://example.test/actions/runs/${id}`, ...overrides,
});

async function lookup(f, options = {}) {
  const env = {BASELINE_CHECKOUT: f.repo, BASELINE_PATH: '', RUNNER_TEMP: f.root,
    BASELINE_RESOLVE_ONLY: 'false', BASELINE_REFERENCE: '',
    BASELINE_ARTIFACT: options.artifact || 'results', BASELINE_WORKFLOW: 'release.yml',
    BASELINE_ALLOW_ANCESTOR: options.allowAncestor || 'false', BASELINE_CONCLUSION: options.conclusion || 'success',
    ...options.env};
  const previous = {...process.env};
  Object.assign(process.env, env);
  const outputs = {}, calls = [], messages = [];
  const core = {setOutput: (key, value) => { outputs[key] = value; },
    info: value => messages.push(['info', value]), warning: value => messages.push(['warning', value]),
    notice: value => messages.push(['notice', value])};
  const api = (name, args, data) => {
    calls.push({name, args});
    if (options.errorAt === name) throw Object.assign(new Error('private response'), {status: 403});
    return {data};
  };
  try {
    await baseline.find({core, context: options.context || f.context, github: {rest: {actions: {
      listWorkflowRuns: async args => api(args.head_sha ? 'exact' : 'runs', args, {workflow_runs: args.head_sha
        ? (options.exactRuns || (options.runs || [run(3, f.advanced)]).filter(r => r.head_sha === args.head_sha))
        : options.runs || []}),
      listWorkflowRunArtifacts: async args => api('artifacts', args, {artifacts:
        options.artifacts || [{name: env.BASELINE_ARTIFACT, expired: false}]}),
    }}}});
    if (env.BASELINE_RESOLVE_ONLY === 'true') return {outputs, calls, messages};
    // github-script writes its reserved result output after the script completes.
    core.setOutput('result', '');
    const action = fs.readFileSync(path.join(__dirname, '../build/baseline/action.yml'), 'utf8');
    const resultKey = action.match(/BASELINE_RESULT: \$\{\{ steps.find.outputs.([\w-]+) \}\}/)[1];
    const result = outputs[resultKey];
    Object.assign(process.env, {BASELINE_ROOT: outputs.root,
      BASELINE_RESULT: typeof result === 'string' ? result : JSON.stringify(result),
      BASELINE_DOWNLOAD_OUTCOME: options.download || (outputs['run-id'] ? 'success' : 'skipped')});
    baseline.finish({core});
    return {outputs, calls, messages, metadata: JSON.parse(fs.readFileSync(outputs['metadata-file']))};
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in previous)) delete process.env[key];
    Object.assign(process.env, previous);
  }
}

test('PR merge uses its target parent; PR head uses the merge base', t => {
  const f = fixture(t);
  f.context.payload.pull_request.base.sha = f.base; // Stale payload: checked-out merge wins.
  assert.deepEqual(baseline.resolveReference(f.context, f.repo), {branch: 'main', commits: [f.advanced, f.base, f.older]});
  f.context.payload.pull_request.base.sha = f.advanced;
  f.git('checkout', '-q', '--detach', f.head);
  assert.deepEqual(baseline.resolveReference(f.context, f.repo).commits, [f.base, f.older]);
});

test('multi-commit and force pushes use before, including previous history', t => {
  const f = fixture(t);
  const context = {...f.context, eventName: 'push', ref: 'refs/heads/main', payload: {before: f.base, after: f.merge}};
  assert.deepEqual(baseline.resolveReference(context, f.repo).commits, [f.base, f.older]);
  f.git('checkout', '-q', '--detach', f.head);
  context.payload = {before: f.merge, after: f.head, forced: true};
  assert.deepEqual(baseline.resolveReference(context, f.repo).commits, [f.merge, f.advanced, f.base, f.older]);
});

test('manual/scheduled events use first parent and mismatched events are unavailable', t => {
  const f = fixture(t);
  for (const eventName of ['schedule', 'workflow_dispatch']) {
    const context = {...f.context, eventName, ref: 'refs/heads/main', payload: {}};
    assert.deepEqual(baseline.resolveReference(context, f.repo).commits, [f.advanced, f.base, f.older]);
    assert.deepEqual(baseline.resolveReference({...context, sha: f.head}, f.repo).commits, []);
  }
  for (const [ref, payload] of [
    ['refs/tags/v1', {before: f.base, after: f.merge}],
    ['refs/heads/main', {before: '0'.repeat(40), after: f.merge}],
    ['refs/heads/main', {before: f.base, after: f.head}],
    ['refs/heads/main', {before: f.base, after: f.merge, deleted: true}],
  ]) assert.deepEqual(baseline.resolveReference({...f.context, eventName: 'push', ref, payload}, f.repo).commits, []);
});

test('shallow checkout retains the exact event baseline without invented ancestry', t => {
  const f = fixture(t);
  const shallow = path.join(f.root, 'shallow');
  f.git('clone', '-q', '--depth=1', `file://${f.repo}`, shallow);
  f.context.payload.pull_request.base.sha = f.base;
  assert.deepEqual(baseline.resolveReference(f.context, shallow).commits, [f.advanced]);
  const scheduled = {...f.context, eventName: 'schedule', ref: 'refs/heads/main', payload: {}};
  assert.deepEqual(baseline.resolveReference(scheduled, shallow).commits, [f.advanced]);
});

test('exact run lookup precedes bounded ancestor search and retains provenance', async t => {
  const f = fixture(t);
  const result = await lookup(f, {exactRuns: [run(1, f.base), run(3, f.advanced)]});
  assert.equal(result.outputs.status, 'exact');
  assert.equal(result.outputs['run-id'], 3);
  assert.equal(result.metadata.sha, f.advanced);
  assert.equal(result.metadata.requested_sha, f.advanced);
  assert.equal(result.metadata.run_url, 'https://example.test/actions/runs/3');
  assert.deepEqual(result.calls.map(c => c.name), ['exact', 'artifacts']);
  assert.equal(result.calls[0].args.head_sha, f.advanced);
  assert.ok(!('status' in result.calls[0].args));
  assert.deepEqual(result.messages, []);
});

test('prepare resolves without API access and lookup reuses its reference without a checkout', async t => {
  const f = fixture(t);
  const resolved = await lookup(f, {env: {
    BASELINE_RESOLVE_ONLY: 'true', BASELINE_ARTIFACT: '', BASELINE_WORKFLOW: '',
  }});
  assert.deepEqual(resolved.outputs, {reference: {branch: 'main', commits: [f.advanced, f.base, f.older]}});
  assert.deepEqual(resolved.calls, []);
  assert.deepEqual(fs.readdirSync(f.root), ['repo']);
  const result = await lookup(f, {env: {
    BASELINE_CHECKOUT: path.join(f.root, 'no-checkout'), BASELINE_REFERENCE: JSON.stringify(resolved.outputs.reference),
  }});
  assert.equal(result.outputs.status, 'exact');
  assert.equal(result.metadata.requested_sha, f.advanced);
  assert.deepEqual(result.calls.map(c => c.name), ['exact', 'artifacts']);
});

test('an unresolved prepared reference stays unavailable without falling back to the checkout', async t => {
  const f = fixture(t);
  const result = await lookup(f, {env: {BASELINE_REFERENCE: JSON.stringify({branch: '', commits: []})}});
  assert.equal(result.outputs.status, 'unavailable');
  assert.equal(result.metadata.path, '');
  assert.deepEqual(result.calls, []);
});

test('baseline metadata still locates its artifacts after transfer to another runner', async t => {
  const f = fixture(t);
  const result = await lookup(f);
  assert.ok(path.isAbsolute(result.outputs.path));
  assert.equal(result.metadata.path, 'artifacts');
  fs.mkdirSync(result.outputs.path);
  fs.writeFileSync(path.join(result.outputs.path, 'coverage.json'), '{"line_rate":0.5}');
  const downloaded = path.join(f.root, 'another-runner', '.build-baseline');
  fs.cpSync(result.outputs.root, downloaded, {recursive: true});
  fs.rmSync(result.outputs.root, {recursive: true});
  const metadata = JSON.parse(fs.readFileSync(path.join(downloaded, 'metadata.json')));
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(downloaded, metadata.path, 'coverage.json'))), {line_rate: 0.5});
});

test('malformed prepared references fail before allocating an output directory', async t => {
  const f = fixture(t);
  for (const reference of [null, {}, {branch: '', commits: [f.base]}, {branch: 'main\n', commits: []},
    {branch: 'main', commits: ['wrong']}, {branch: 'main', commits: Array(101).fill(f.base)}]) {
    await assert.rejects(lookup(f, {env: {BASELINE_REFERENCE: JSON.stringify(reference)}}), /reference must contain/);
  }
  await assert.rejects(lookup(f, {env: {BASELINE_REFERENCE: '{'}}), SyntaxError);
  assert.deepEqual(fs.readdirSync(f.root), ['repo']);
});

test('disabled baseline leaves command jobs runnable; enabled lookup failure or cancellation blocks them', () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../.github/workflows/build.yml'), 'utf8');
  for (const phase of ['pre', 'post']) {
    const job = workflow.split(`\n  ${phase}-steps:\n`)[1].split(/\n  [\w-]+:\n/)[0];
    const expression = job.match(/^    if: \$\{\{ (.*) \}\}$/m)[1]
      .replace(/\.([\w]+(?:-[\w]+)+)/g, "['$1']");
    const evaluate = new Function('inputs', 'needs', 'failure', 'cancelled', `return !!(${expression})`);
    for (const [enabled, status, cancelled, hasCommands, expected] of [
      [false, 'skipped', false, true, true], [true, 'success', false, true, true],
      [true, 'failure', false, true, false], [true, 'success', true, true, false],
      [false, 'skipped', false, false, false], [true, 'success', false, false, false],
    ]) {
      assert.equal(evaluate({'baseline-enabled': enabled}, {
        prepare: {result: 'success', outputs: {[`${phase}-step-matrix`]: hasCommands ? '[{}]' : '[]'}},
        baseline: {result: status},
      }, () => status === 'failure', () => cancelled), expected, `${phase}: ${enabled}/${status}/${cancelled}/${hasCommands}`);
    }
  }
});

test('ancestor fallback is opt-in, bounded and independent of API ordering', async t => {
  const f = fixture(t);
  const options = {runs: [run(9, f.older), run(1, f.base), run(2, f.head)]};
  const disabled = await lookup(f, options);
  assert.equal(disabled.outputs.status, 'unavailable');
  assert.deepEqual(disabled.calls.map(c => c.name), ['exact']);
  const enabled = await lookup(f, {...options, allowAncestor: 'true'});
  assert.equal(enabled.outputs.status, 'approximate');
  assert.equal(enabled.metadata.sha, f.base);
  assert.equal(enabled.calls[1].args.per_page, 100);
  assert.equal(enabled.messages[0][0], 'notice');
});

test('selection excludes current, PR, incomplete and unrelated-branch runs', async t => {
  const f = fixture(t);
  const result = await lookup(f, {runs: [run(100, f.advanced),
    run(2, f.advanced, {event: 'pull_request'}), run(4, f.advanced, {status: 'in_progress'}),
    run(5, f.advanced, {head_branch: 'other'}), run(6, f.head)]});
  assert.equal(result.outputs.status, 'unavailable');
});

test('failed run artifacts require explicit any conclusion policy', async t => {
  const f = fixture(t);
  const runs = [run(1, f.advanced, {conclusion: 'failure'})];
  assert.equal((await lookup(f, {runs})).outputs.status, 'unavailable');
  assert.equal((await lookup(f, {runs, conclusion: 'any', artifact: 'test-results'})).outputs.status, 'exact');
});

test('missing or expired artifact never silently substitutes an older run', async t => {
  const f = fixture(t);
  for (const artifacts of [[], [{name: 'other', expired: false}], [{name: 'results', expired: true}]]) {
    const result = await lookup(f, {artifacts, allowAncestor: 'true', runs: [run(1, f.base), run(3, f.advanced)]});
    assert.equal(result.outputs.status, 'unavailable');
    assert.equal(result.outputs.path, '');
    assert.deepEqual(result.calls.map(c => c.name), ['exact', 'artifacts']);
    assert.equal(result.messages[0][0], 'warning');
  }
});

test('API/download errors warn once, keep metadata and never expose response bodies', async t => {
  const f = fixture(t);
  for (const options of [{errorAt: 'exact'}, {errorAt: 'artifacts'},
    {errorAt: 'runs', runs: [], allowAncestor: 'true'}, {download: 'failure'}]) {
    const result = await lookup(f, options);
    assert.equal(result.outputs.status, 'unavailable');
    assert.equal(result.outputs.path, '');
    assert.equal(result.outputs['run-id'], '');
    assert.equal(result.messages.length, 1);
    assert.equal(result.messages[0][0], 'warning');
    assert.doesNotMatch(JSON.stringify(result), /private response/);
  }
});

test('unresolvable events make no API calls and log an explanation', async t => {
  const f = fixture(t);
  const result = await lookup(f, {context: {...f.context, eventName: 'workflow_run'}});
  assert.equal(result.outputs.status, 'unavailable');
  assert.equal(result.calls.length, 0);
  assert.equal(result.messages[0][0], 'info');
});

test('invalid options and existing output directories fail instead of reusing stale data', async t => {
  const f = fixture(t);
  for (const env of [{BASELINE_CONCLUSION: 'typo'}, {BASELINE_ALLOW_ANCESTOR: 'yes'},
    {BASELINE_RESOLVE_ONLY: 'yes'},
    {BASELINE_ARTIFACT: ''}, {BASELINE_WORKFLOW: ''}, {BASELINE_PATH: f.repo}]) {
    await assert.rejects(lookup(f, {env}));
  }
  assert.equal(fs.readFileSync(path.join(f.repo, 'base'), 'utf8'), 'base');
});
