import {mkdir} from 'node:fs/promises';
import {expect, test} from '@playwright/test';

const REVIEW_DIR = 'artifacts/site-review';

async function catalog(request) {
  const response = await request.get('/data/catalog.json');
  expect(response.ok()).toBeTruthy();
  return response.json();
}

test.beforeAll(async () => {
  await mkdir(REVIEW_DIR, {recursive: true});
});

test('searches the catalog and opens a course', async ({page, request}, testInfo) => {
  const data = await catalog(request);
  const lecture = data.items.find(item => item.title.toLowerCase().includes('tokenization'));
  expect(lecture).toBeTruthy();
  const course = data.courses.find(candidate => candidate.id === lecture.course_id);

  await page.goto('/index.html');
  await expect(page.getByRole('heading', {name: '课程资料', exact: true})).toBeVisible();
  await page.getByRole('searchbox').fill('Tokenization');
  await expect(page.getByText('找到 1 门匹配课程')).toBeVisible();
  await page.getByRole('link', {name: `查看讲义：${course.title}`}).click();
  await expect(page.getByRole('heading', {name: course.title, level: 2})).toBeFocused();
  await expect(page.getByRole('heading', {name: lecture.title})).toBeVisible();

  await page.screenshot({
    path: `${REVIEW_DIR}/${testInfo.project.name}-course.png`,
    fullPage: true,
  });
});

test('opens a catalog-whitelisted PDF in the dedicated reader', async ({page, request}, testInfo) => {
  const data = await catalog(request);
  const course = data.courses.find(candidate => candidate.id.includes('cs336'));
  expect(course).toBeTruthy();
  const item = data.items.find(candidate =>
    candidate.course_id === course.id && candidate.kind !== 'bundle'
  );
  expect(item).toBeTruthy();

  await page.goto(`/reader.html?id=${encodeURIComponent(item.id)}`);
  await expect(page.getByRole('heading', {name: item.title, level: 1})).toBeVisible();
  await expect(page.locator('#pdf-frame')).toHaveAttribute('src', `${item.pdf}#view=FitH`);
  await expect(page.getByRole('link', {name: '直接打开 PDF'})).toHaveAttribute('href', item.pdf);
  await expect(page.getByRole('link', {name: '下载 PDF'})).toHaveAttribute(
    'download',
    item.pdf.split('/').pop(),
  );

  await page.screenshot({
    path: `${REVIEW_DIR}/${testInfo.project.name}-reader.png`,
    fullPage: true,
  });
});

test('explains fork permissions and starts the contribution flow', async ({page}, testInfo) => {
  await page.goto('/contribute.html');
  const fork = page.getByRole('link', {name: '第一步：Fork 仓库'});
  await expect(fork).toHaveAttribute('href', 'https://github.com/ysyecust/lecture-to-notes/fork');
  await expect(page.getByText('普通贡献者不能直接修改这个仓库', {exact: false})).toBeVisible();
  await expect(page.getByText('PR 只提交变更和说明，不会获得原仓库写入权限。')).toBeVisible();
  await page.screenshot({
    path: `${REVIEW_DIR}/${testInfo.project.name}-contribute.png`,
    fullPage: true,
  });
});
