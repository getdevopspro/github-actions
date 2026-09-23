const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {test} = require('node:test');
const publish = require('../build/report/comment.js');

test('create, update, and clean up report comments without live GitHub calls', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'build-report-comment-'));
  try {
    process.env.REPORT_MARKDOWN = path.join(root, 'report.md');
    process.env.REPORT_ARTIFACT_URL = 'https://example.test/report';
    fs.writeFileSync(process.env.REPORT_MARKDOWN, 'Test results');
    const marker = '<!-- build-report-summary -->';
    for (const comments of [[], [{id: 1, body: 'unrelated'}], [
      {id: 1, body: 'unrelated'}, {id: 2, body: marker + '\nold'},
      {id: 3, body: marker + '\nduplicate'}, {id: 4, body: marker + '\nduplicate'},
    ]]) {
      const calls = [];
      const warnings = [];
      const github = {
        paginate: async () => comments,
        rest: {issues: {
          listComments: () => {},
          createComment: async (args) => calls.push(['create', args]),
          updateComment: async (args) => calls.push(['update', args]),
          deleteComment: async (args) => {
            calls.push(['delete', args]);
            if (args.comment_id === 4) throw new Error('cleanup unavailable');
          },
        }},
      };
      await publish({github, context: {
        repo: {owner: 'example', repo: 'project'}, payload: {pull_request: {number: 10}},
      }, core: {warning: (message) => warnings.push(message)}});
      assert.equal(calls[0][0], comments.length > 1 ? 'update' : 'create');
      assert.equal(calls[0][1].body,
        marker + '\nTest results\n[Download the full HTML report](https://example.test/report)\n');
      if (comments.length > 1) {
        assert.equal(calls[0][1].comment_id, 2);
        assert.deepEqual(calls.slice(1).map(([, args]) => args.comment_id), [3, 4]);
        assert.equal(warnings.length, 1);
      } else {
        assert.equal(calls[0][1].issue_number, 10);
        assert.equal(calls.length, 1);
      }
    }
  } finally {
    fs.rmSync(root, {recursive: true, force: true});
  }
});
