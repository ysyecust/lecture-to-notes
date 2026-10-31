import {readerUrl} from './catalog.js';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function metric(value, label) {
  const wrapper = element('span', 'metric');
  wrapper.append(element('strong', '', String(value)), document.createTextNode(` ${label}`));
  return wrapper;
}

export function createCourseGroupHeader(titleText, subtitleText, countText) {
  const header = element('div', 'course-group-header');
  const left = element('div', 'course-group-title');
  left.append(element('h3', '', titleText));
  if (subtitleText) left.append(element('p', '', subtitleText));
  header.append(left);
  if (countText) header.append(element('span', 'course-group-count', countText));
  return header;
}

export function createCourseCard(course, items) {
  const article = element('article', `course-card${course.featured ? ' featured' : ''}`);
  article.dataset.courseId = course.id;

  const spine = element('div', 'course-spine');
  spine.append(element('span', 'spine-code', course.id.toUpperCase()), element('span', 'spine-mark', 'L/N'));
  const body = element('div', 'course-card-body');
  const overline = element('p', 'course-overline', `${course.institution} / ${course.term}`);
  const title = element('h3', '', course.title);
  const description = element('p', 'course-description', course.description);

  const tags = element('div', 'course-tags');
  for (const tag of (course.tags || []).slice(0, 4)) {
    tags.append(element('span', 'course-tag', tag));
  }

  const lectureCount = course.lecture_count ?? course.item_count;
  const bundleCount = course.bundle_count ?? items.filter(item => item.kind === 'bundle').length;
  const webCount = items.filter(item => Boolean(item.web)).length;

  const metrics = element('div', 'course-metrics');
  metrics.append(metric(lectureCount, '讲'), metric(course.page_count, '页'));
  if (bundleCount > 0) {
    metrics.append(element('span', 'course-badge bundle-badge', bundleCount === 1 ? '含完整合集' : `${bundleCount} 份合集`));
  }
  if (webCount > 0) {
    metrics.append(
      element(
        'span',
        'course-badge web-badge',
        webCount >= lectureCount ? '全讲网页精读' : `${webCount} 讲网页精读`,
      ),
    );
  }

  const ticks = element('div', 'lecture-ticks');
  ticks.setAttribute('aria-label', `${course.item_count} 份讲义`);
  for (const item of items) {
    const tick = element('span', `lecture-tick${item.kind === 'bundle' ? ' bundle' : ''}${item.web ? ' web-ready' : ''}`);
    tick.title = item.title;
    ticks.append(tick);
  }

  const link = element('a', 'course-link', '查看讲义');
  link.href = `#course=${encodeURIComponent(course.id)}`;
  link.setAttribute('aria-label', `查看讲义：${course.title}`);
  body.append(overline, title, description);
  if (tags.childElementCount > 0) body.append(tags);
  body.append(metrics, ticks, link);
  article.append(spine, body);
  return article;
}

export function createItemRow(item) {
  const row = element('article', `item-row${item.kind === 'bundle' ? ' bundle' : ''}`);
  const number = item.kind === 'bundle' ? '合集' : String(item.order || '').padStart(2, '0');
  row.append(element('p', 'item-number', number));
  const copy = element('div', 'item-copy');
  copy.append(element('h3', '', item.title));
  const metaParts = [`${item.pages} 页`];
  if (item.duration_minutes) metaParts.push(`${item.duration_minutes} min`);
  if (item.instructor) metaParts.push(item.instructor);
  const metaRow = element('div', 'item-meta-row');
  metaRow.append(element('p', 'item-meta', metaParts.join(' · ')));
  if (item.web) {
    metaRow.append(element('span', 'item-badge web-badge', '网页 + PDF'));
  } else if (item.kind === 'bundle') {
    metaRow.append(element('span', 'item-badge bundle-badge', '完整合集 PDF'));
  }
  copy.append(metaRow);
  const link = element('a', 'button button-primary', '进入讲义');
  link.href = readerUrl(item.id);
  row.append(copy, link);
  return row;
}

export function createSearchLectureRow(item, course) {
  const row = element('div', `search-lecture-row${item.kind === 'bundle' ? ' bundle' : ''}`);
  const orderText = item.kind === 'bundle' ? '合集' : `#${String(item.order || '').padStart(2, '0')}`;
  row.append(element('span', 'search-lecture-order', orderText));
  const copy = element('div', 'search-lecture-copy');
  const titleLine = element('div', 'search-lecture-header');
  titleLine.append(
    element('span', 'search-lecture-course', `${course.institution} · ${course.title}`),
  );
  if (item.web) {
    titleLine.append(element('span', 'item-badge web-badge', '网页 + PDF'));
  }
  const title = element('p', 'search-lecture-title', item.title);
  const metaParts = [`${item.pages} 页`];
  if (item.duration_minutes) metaParts.push(`${item.duration_minutes} min`);
  if (item.instructor) metaParts.push(item.instructor);
  const meta = element('p', 'search-lecture-meta', metaParts.join(' · '));
  copy.append(titleLine, title, meta);
  const link = element('a', 'button button-secondary search-lecture-link', '直接阅读 ↗');
  link.href = readerUrl(item.id);
  row.append(copy, link);
  return row;
}

export function createPaperCard(paper) {
  const article = element('article', 'paper-card');
  article.append(element('p', 'paper-icon', paper.icon || '↗'));
  const copy = element('div', 'paper-copy');
  copy.append(element('h3', '', paper.title), element('p', '', paper.meta || '论文解读'));
  const link = element('a', 'paper-link', '查看全文 ↗');
  link.href = paper.url;
  copy.append(link);
  article.append(copy);
  return article;
}
