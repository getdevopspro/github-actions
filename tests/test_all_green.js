'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const action = fs.readFileSync(path.join(root, 'all-green/action.yml'), 'utf8');
const workflow = fs.readFileSync(path.join(root, '.github/workflows/all-green.yml'), 'utf8');
const COPILOT = '^copilot-pull-request-reviewer$';

// Evaluates an allcheckspassed `with:` expression from the action for the given inputs.
function expression(name) {
  const source = action.match(new RegExp(`^        ${name}: \\$\\{\\{ (.*) \\}\\}$`, 'm'))[1]
    .replace(/\.([\w]+(?:-[\w]+)+)/g, "['$1']");
  return new Function('inputs', `return (${source})`);
}

function inputBlock(source, name, indent) {
  const lines = source.split('\n');
  const start = lines.indexOf(`${' '.repeat(indent)}${name}:`);
  assert.notEqual(start, -1, name);
  const rest = lines.slice(start + 1);
  const end = rest.findIndex(line => !line.startsWith(' '.repeat(indent + 2)));
  return rest.slice(0, end).join('\n');
}

test('include wins over exclude, so allcheckspassed never receives both', () => {
  const include = expression('checks_include');
  const exclude = expression('checks_exclude');
  for (const [inputs, expected] of [
    [{'checks-include': '', 'checks-exclude': COPILOT}, ['-1', COPILOT]],
    [{'checks-include': '', 'checks-exclude': ''}, ['-1', '-1']],
    [{'checks-include': '', 'checks-exclude': '-1'}, ['-1', '-1']],
    [{'checks-include': '-1', 'checks-exclude': COPILOT}, ['-1', COPILOT]],
    [{'checks-include': '^Lint$', 'checks-exclude': COPILOT}, ['^Lint$', '-1']],
    [{'checks-include': '^Lint$,^Unit Tests$', 'checks-exclude': '^Other$'}, ['^Lint$,^Unit Tests$', '-1']],
  ]) {
    assert.deepEqual([include(inputs), exclude(inputs)], expected, JSON.stringify(inputs));
  }
});

test('the reusable workflow repeats the action defaults and forwards every input', () => {
  assert.match(inputBlock(action, 'checks-include', 2), /^    default: ''$/m);
  assert.match(inputBlock(workflow, 'checks-include', 6), /^        default: ''$/m);
  assert.match(inputBlock(action, 'checks-exclude', 2), /^    default: '\^copilot-pull-request-reviewer\$'$/m);
  assert.match(inputBlock(workflow, 'checks-exclude', 6), /^        default: '\^copilot-pull-request-reviewer\$'$/m);
  assert.match(inputBlock(action, 'fail-on-missing-checks', 2), /^    default: 'false'$/m);
  assert.match(inputBlock(workflow, 'fail-on-missing-checks', 6), /^        default: false$/m);
  for (const name of ['checks-include', 'checks-exclude', 'fail-on-missing-checks']) {
    assert.ok(workflow.includes(`          ${name}: \${{ inputs.${name} }}\n`), name);
  }
  assert.match(action, /^        fail_on_missing_checks: \$\{\{ inputs\.fail-on-missing-checks \}\}$/m);
});
