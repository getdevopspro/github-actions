const fs = require('node:fs');

module.exports = async ({github, context, core}) => {
  const issue_number = context.payload.pull_request.number;
  const marker = '<!-- build-report-summary -->';
  let body = marker + '\n' + fs.readFileSync(process.env.REPORT_MARKDOWN, 'utf8');
  if (process.env.REPORT_ARTIFACT_URL) {
    body += `\n[Download the full HTML report](${process.env.REPORT_ARTIFACT_URL})\n`;
  }
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...context.repo, issue_number,
  });
  const matching = comments.filter(comment => comment.body?.startsWith(marker));
  if (matching.length) {
    await github.rest.issues.updateComment({
      ...context.repo, comment_id: matching[0].id, body,
    });
    for (const comment of matching.slice(1)) {
      try {
        await github.rest.issues.deleteComment({...context.repo, comment_id: comment.id});
      } catch {
        core.warning('Could not remove a duplicate build report comment');
      }
    }
  } else {
    await github.rest.issues.createComment({...context.repo, issue_number, body});
  }
};
