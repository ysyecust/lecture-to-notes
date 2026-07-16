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

export function createCourseCard(course, items) {
  const article = element('article', `course-card${course.featured ? ' featured' : ''}`);
  article.dataset.courseId = course.id;

  const spine = element('div', 'course-spine');
  spine.append(element('span', 'spine-code', course.id.toUpperCase()), element('span', 'spine-mark', 'L/N'));
  const body = element('div', 'course-card-body');
  const overline = element('p', 'course-overline', `${course.institution} / ${course.term}`);
  const title = element('h3', '', course.title);
  const description = element('p', 'course-description', course.description);
  const metrics = element('div', 'course-metrics');
  metrics.append(metric(course.item_count, '份'), metric(course.page_count, '页'));

  const ticks = element('div', 'lecture-ticks');
  ticks.setAttribute('aria-label', `${course.item_count} 份讲义`);
  for (const item of items) {
    const tick = element('span', `lecture-tick${item.kind === 'bundle' ? ' bundle' : ''}`);
    tick.title = item.title;
    ticks.append(tick);
  }

  const link = element('a', 'course-link', '查看课程');
  link.href = `#course=${encodeURIComponent(course.id)}`;
  link.setAttribute('aria-label', `查看课程：${course.title}`);
  body.append(overline, title, description, metrics, ticks, link);
  article.append(spine, body);
  return article;
}

export function createItemRow(item) {
  const row = element('article', `item-row${item.kind === 'bundle' ? ' bundle' : ''}`);
  const number = item.kind === 'bundle' ? '合集' : String(item.order || '').padStart(2, '0');
  row.append(element('p', 'item-number', number));
  const copy = element('div', 'item-copy');
  copy.append(element('h3', '', item.title));
  const meta = element('p', 'item-meta', `${item.pages} 页${item.instructor ? ` · ${item.instructor}` : ''}`);
  copy.append(meta);
  const link = element('a', 'button button-primary', '阅读 PDF');
  link.href = readerUrl(item.id);
  row.append(copy, link);
  return row;
}

export function createPaperCard(paper) {
  const article = element('article', 'paper-card');
  article.append(element('p', 'paper-icon', paper.icon || '↗'));
  const copy = element('div', 'paper-copy');
  copy.append(element('h3', '', paper.title), element('p', '', paper.meta || '论文解读'));
  const link = element('a', 'paper-link', '阅读解读 ↗');
  link.href = paper.url;
  copy.append(link);
  article.append(copy);
  return article;
}
