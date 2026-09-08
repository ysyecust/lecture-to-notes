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

test('reader failures offer recovery without inactive PDF actions', async ({page}) => {
  for (const url of ['/reader.html', '/reader.html?id=missing-note']) {
    await page.goto(url);
    await expect(page.getByRole('heading', {name: '无法打开这份 PDF'})).toBeVisible();
    await expect(page.locator('.reader-actions')).toBeHidden();
    await expect(page.locator('#reader-course')).toHaveText('阅读暂不可用');
    await page.locator('#reader-error').getByRole('link', {name: '返回课程资料'}).click();
    await expect(page.getByRole('heading', {name: '课程资料', exact: true})).toBeVisible();
  }
});

test('switches lectures and returns to the current course', async ({page, request}, testInfo) => {
  const data = await catalog(request);
  const course = data.courses.find(candidate => candidate.item_ids.length >= 2);
  const [first, second] = course.item_ids.map(id => data.items.find(item => item.id === id));
  await page.goto(`/reader.html?id=${first.id}`);
  await expect(page.locator('#reader-title')).toHaveText(first.title);
  if (testInfo.project.name.startsWith('mobile')) {
    await page.locator('#mobile-item-select').selectOption(second.id);
  } else {
    await page.locator('#course-nav').getByRole('link').filter({hasText: second.title}).click();
  }
  await expect(page.locator('#reader-title')).toHaveText(second.title);
  await expect(page.locator('#pdf-frame')).toHaveAttribute('src', `${second.pdf}#view=FitH`);
  if (!testInfo.project.name.startsWith('mobile')) {
    await page.locator('.reader-rail .back-link').click();
    await expect(page.locator('#course-detail-title')).toHaveText(course.title);
  }
});

test('every paper has site navigation and a readable viewport', async ({page, request}) => {
  const data = await catalog(request);
  for (const paper of data.papers) {
    await page.goto(`/${paper.url}`, {waitUntil: 'domcontentloaded'});
    await expect(page.getByRole('navigation', {name: '主导航'})).toBeVisible();
    await expect(page.locator('.paper-back')).toHaveAttribute('href', '../index.html#papers-title');
    await expect(page.locator('.paper-document h1')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  }
  await page.locator('.paper-back').click();
  await expect(page.getByRole('heading', {name: '论文解读', exact: true})).toBeInViewport();
});

test('catalog failure can recover and reader failure stops loading', async ({page}) => {
  await page.route('**/data/catalog.json', route => route.fulfill({status: 503, body: 'Unavailable'}));
  await page.goto('/index.html');
  await expect(page.locator('#catalog-error')).toBeVisible();
  await page.unroute('**/data/catalog.json');
  await page.getByRole('button', {name: '重新加载'}).click();
  await expect(page.locator('.course-card').first()).toBeVisible();
  await expect(page.locator('#catalog-error')).toBeHidden();
  await page.route('**/data/catalog.json', route => route.fulfill({status: 503, body: 'Unavailable'}));
  await page.goto('/reader.html?id=unavailable');
  await expect(page.locator('#reader-error')).toBeVisible();
  await expect(page.locator('#reader-course')).toHaveText('阅读暂不可用');
  await expect(page.locator('.reader-actions')).toBeHidden();
});
