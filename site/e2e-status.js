// Public GitHub Actions metadata only: no token or backend required.
const status = document.getElementById('e2eStatus');
const meta = document.getElementById('e2eMeta');
const link = document.getElementById('e2eLink');
const api = 'https://api.github.com/repos/frankwang98/ROS2Drive-Cloud/actions/workflows/e2e.yml/runs?per_page=1';
try {
  const response = await fetch(api, {headers: {Accept: 'application/vnd.github+json'}});
  if (!response.ok) throw new Error('HTTP ' + response.status);
  const {workflow_runs: runs = []} = await response.json();
  if (!runs.length) throw new Error('尚无 E2E 测试记录');
  const run = runs[0];
  const state = run.status !== 'completed' ? '运行中' :
    run.conclusion === 'success' ? '通过' : '未通过';
  status.textContent = 'MQTT E2E：' + state;
  status.style.fontWeight = '700';
  status.style.color = run.status !== 'completed' ? '#e8b967' :
    run.conclusion === 'success' ? '#5be3b1' : '#ff7777';
  const date = run.updated_at ? new Date(run.updated_at).toLocaleString('zh-CN') : '未知';
  meta.textContent = '更新时间：' + date + ' · Commit ' + run.head_sha.slice(0, 7) +
    ' · Backend → MQTT → Mock Robot → ACK（非真实 ROS2 / 实车）';
  link.href = run.html_url;
} catch (error) {
  status.textContent = '暂时无法读取 E2E 结果';
  meta.textContent = 'GitHub API 不可用或访问受限；请点击右侧链接查看工作流。' +
    ' 本页面不会将无法读取误显示为通过。';
}
