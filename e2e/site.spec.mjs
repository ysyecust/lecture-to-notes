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
  await expect(page.locator('#pdf-viewer canvas').first()).toBeVisible();
  await expect(page.locator('#page-count')).toHaveText(`/ ${item.pages}`);
  await expect(page.locator('#open-pdf')).toHaveAttribute('href', item.pdf);
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
    await expect(page.getByRole('heading', {name: '无法打开这份讲义'})).toBeVisible();
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
    await page.locator('#toggle-rail').click();
    await page.locator('#mobile-item-select').selectOption(second.id);
  } else {
    await page.locator('#tab-course').click();
    await page.locator('#course-nav').getByRole('link').filter({hasText: second.title}).click();
  }
  await expect(page.locator('#reader-title')).toHaveText(second.title);
  await expect(page.locator('#open-pdf')).toHaveAttribute('href',second.pdf);
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

test('all three pilot lectures expose complete web documents', async ({page,request}) => {
  const data=await catalog(request);const items=data.items.filter(i=>i.course_id==='nju-gse-2026' && i.kind==='lecture' && i.order>=1 && i.order<=3);
  expect(items).toHaveLength(3);
  for(const item of items){
    expect(item.web).toBeTruthy();const report=await (await request.get('/'+item.web.report)).json();
    expect(report.status).toBe('passed');expect(report.pdf_sha256).toBe(item.sha256);
    await page.goto(`/reader.html?id=${item.id}&format=html`);
    await expect(page.locator('.web-document')).toBeVisible();
    await expect(page.locator('.web-document figure')).toHaveCount(report.counts.figures);
    await expect(page.locator('.web-document .video-link')).toHaveCount(report.counts.figures);
    await expect(page.locator('.web-document math')).toHaveCount(report.counts.math);
    await expect(page.locator('#reader-error')).toBeHidden();
    await page.locator('.figure-zoom').first().click();await expect(page.locator('#figure-dialog')).toBeVisible();await page.locator('#close-figure').click();
  }
});

test('CMU lectures render complete HTML with YouTube interval links', async ({page, request}) => {
  const data = await catalog(request);
  const items = data.items.filter(item => item.course_id === 'cmu-ai-agents');
  expect(items).toHaveLength(4);
  for (const item of items) {
    const report = await (await request.get('/' + item.web.report)).json();
    expect(report.status).toBe('passed');
    expect(report.pdf_sha256).toBe(item.sha256);
    await page.goto(`/reader.html?id=${item.id}&format=html`);
    await expect(page.locator('.web-document')).toBeVisible();
    await expect(page.locator('.web-document figure')).toHaveCount(report.counts.figures);
    await expect(page.locator('.web-document math')).toHaveCount(report.counts.math);
    await expect(page.locator('.web-document .video-link')).toHaveCount(report.counts.figures);
    const links = await page.locator('.web-document figure').evaluateAll(figures =>
      figures.map(figure => ({time: figure.dataset.start, href: figure.querySelector('.video-link').href}))
    );
    for (const link of links) {
      const expected = new URL(item.source_url);
      const [h, m, s] = link.time.split(':').map(Number);
      expected.searchParams.set('t', String(h * 3600 + m * 60 + s));
      expect(link.href).toBe(expected.href);
    }
    await expect(page.locator('#reader-error')).toBeHidden();
  }
});

test('PDF zoom changes actual page size through 800 percent and fit width', async ({page,request}) => {
  const data=await catalog(request);const item=data.items.find(i=>i.course_id==='nju-gse-2026'&&i.order===3);
  await page.goto(`/reader.html?id=${item.id}&format=pdf`);
  await expect(page.locator('#pdf-viewer canvas').first()).toBeVisible();
  const paper=page.locator('#pdf-viewer .page').first();
  await page.locator('#pdf-zoom').selectOption('1');
  const w100=(await paper.boundingBox()).width;
  await page.locator('#pdf-zoom').selectOption('4');await expect.poll(async()=>(await paper.boundingBox()).width/w100).toBeGreaterThan(3.9);
  await page.locator('#pdf-zoom').selectOption('8');await expect.poll(async()=>(await paper.boundingBox()).width/w100).toBeGreaterThan(7.9);
  await expect(page.locator('#zoom-in')).toBeDisabled();
  await page.locator('#pdf-zoom').selectOption('page-width');
  await expect.poll(async()=>{const a=await paper.boundingBox(),b=await page.locator('#pdf-container').boundingBox();return a.width/b.width;}).toBeGreaterThan(.9);
  await expect.poll(async()=>{const a=await paper.boundingBox(),b=await page.locator('#pdf-container').boundingBox();return a.width/b.width;}).toBeLessThan(1.02);
  await page.locator('#focus-mode').click();await expect(page.locator('body')).toHaveClass(/focus-reading/);
  await expect(page.locator('#reader-rail')).toBeHidden();
});

test('PDF page and zoom survive a reload',async({page,request})=>{
  const data=await catalog(request);const item=data.items.find(i=>i.course_id==='nju-gse-2026'&&i.order===2);
  await page.goto(`/reader.html?id=${item.id}&format=pdf`);await expect(page.locator('#pdf-viewer canvas').first()).toBeVisible();
  await page.locator('#pdf-zoom').selectOption('1.5');await page.locator('#page-number').fill('4');await page.locator('#page-number').press('Tab');
  await page.waitForFunction(sha=>JSON.parse(localStorage.getItem(`lecture-reader:v2:${sha}`)||'{}').pdf?.page===4,item.sha256);
  await page.reload();await expect(page.locator('#page-number')).toHaveValue('4');await expect(page.locator('#pdf-zoom')).toHaveValue('1.5');
});

test('HTML position and typography survive a reload and corrupt HTML offers PDF',async({page,request})=>{
  const data=await catalog(request);const item=data.items.find(i=>i.course_id==='nju-gse-2026'&&i.order===2);
  await page.goto(`/reader.html?id=${item.id}&format=html`);await expect(page.locator('.web-document')).toBeVisible();
  await page.locator('#font-larger').click();await page.locator('#chapter-7').scrollIntoViewIfNeeded();
  await page.waitForFunction(sha=>!!JSON.parse(localStorage.getItem(`lecture-reader:v2:${sha}`)||'{}').html,item.sha256);
  const top=await page.locator('#html-container').evaluate(el=>el.scrollTop);
  await page.reload();await expect(page.locator('.web-document')).toBeVisible();
  await expect.poll(()=>page.locator('#html-container').evaluate(el=>el.scrollTop)).toBeGreaterThan(top-150);
  expect(await page.locator('body').evaluate(el=>getComputedStyle(el).getPropertyValue('--reading-font-size'))).toBe('21px');
  await page.route('**/notes/**/article.html',r=>r.fulfill({status:200,contentType:'text/html',body:'<article>corrupt</article>'}));
  await page.reload();await expect(page.locator('#fallback-pdf')).toBeVisible();await page.locator('#fallback-pdf').click();await expect(page.locator('#pdf-viewer canvas').first()).toBeVisible();
});

test('PDF search uses the text layer and finds Chinese text',async({page,request})=>{
  const data=await catalog(request);const item=data.items.find(i=>i.course_id==='nju-gse-2026'&&i.order===3);
  await page.goto(`/reader.html?id=${item.id}&format=pdf`);await expect(page.locator('#pdf-viewer .textLayer').first()).toBeVisible();
  await page.locator('.pdf-search summary').click();await page.locator('#pdf-search').fill('软件');
  await expect.poll(async()=>Number((await page.locator('#find-count').innerText()).split('/')[1])).toBeGreaterThan(0);
});
