import {
  courseMatchesFilter,
  itemMap,
  loadCatalog,
  normalize,
  readerUrl,
  searchCourses,
  searchLectures,
} from './catalog.js';
import {
  createCourseCard,
  createCourseGroupHeader,
  createItemRow,
  createSearchLectureRow,
} from './components.js';

const grid = document.querySelector('#course-grid');
const filtersBar = document.querySelector('#course-filters');
const searchLecturesBox = document.querySelector('#search-lectures');
const detail = document.querySelector('#course-detail');
const empty = document.querySelector('#empty-state');
const status = document.querySelector('#library-status');
const search = document.querySelector('#course-search');
const error = document.querySelector('#catalog-error');
let catalog;
let items;
let focusReturn;
let debounceTimer;
let currentFilter = 'all';

function replaceChildren(node, children) {
  node.replaceChildren(...children);
}

function renderStats() {
  document.querySelector('#stat-courses').textContent = catalog.stats.course_count;
  document.querySelector('#stat-lectures').textContent = catalog.stats.lecture_count;
  document.querySelector('#stat-pages').textContent = catalog.stats.page_count;
}

function updateFilterChips() {
  if (!filtersBar || !catalog) return;
  const labels = {
    all: '全部课程',
    university: '高校系统课程',
    collection: '专题与分享',
    web: '支持网页精读',
  };
  for (const button of filtersBar.querySelectorAll('.filter-chip')) {
    const mode = button.dataset.filter || 'all';
    const count = catalog.courses.filter(course => courseMatchesFilter(course, items, mode)).length;
    const isActive = mode === currentFilter;
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-pressed', String(isActive));
    button.textContent = `${labels[mode] || button.textContent} (${count})`;
  }
}

function buildCard(course) {
  const courseItems = course.item_ids.map(id => items.get(id)).filter(Boolean);
  const card = createCourseCard(course, courseItems);
  card.querySelector('.course-link').addEventListener('click', event => {
    focusReturn = event.currentTarget;
  });
  return card;
}

function renderSearchLectures(matchedLectures) {
  if (!searchLecturesBox) return;
  if (!matchedLectures.length) {
    searchLecturesBox.hidden = true;
    replaceChildren(searchLecturesBox, []);
    return;
  }
  const header = document.createElement('div');
  header.className = 'search-lectures-heading';
  const title = document.createElement('p');
  title.className = 'search-lectures-title';
  title.textContent = `直接命中的讲次（共 ${matchedLectures.length} 份）`;
  const hint = document.createElement('span');
  hint.className = 'search-lectures-hint';
  hint.textContent = matchedLectures.length > 8 ? '展示前 8 份，点击直接进入阅读器' : '点击直接进入阅读器';
  header.append(title, hint);

  const list = document.createElement('div');
  list.className = 'search-lectures-list';
  for (const {item, course} of matchedLectures.slice(0, 8)) {
    list.append(createSearchLectureRow(item, course));
  }
  replaceChildren(searchLecturesBox, [header, list]);
  searchLecturesBox.hidden = false;
}

function renderCourses(query = '') {
  const trimmed = query.trim();
  const courses = searchCourses(catalog, trimmed, currentFilter);
  const matchedLectures = trimmed ? searchLectures(catalog, trimmed, currentFilter) : [];

  const nodes = [];
  if (!trimmed && currentFilter === 'all') {
    const featured = courses.filter(course => course.featured);
    const collections = courses.filter(course => !course.featured);
    if (featured.length && collections.length) {
      nodes.push(
        createCourseGroupHeader(
          '高校系统课程',
          '按学期与讲次完整编排的公开课中文精讲讲义',
          `${featured.length} 门课程`,
        ),
      );
      for (const course of featured) nodes.push(buildCard(course));
      nodes.push(
        createCourseGroupHeader(
          '专题精选与技术分享',
          '围绕特定系统方向、工程实践与前沿演讲整理的专题笔记',
          `${collections.length} 组专题`,
        ),
      );
      for (const course of collections) nodes.push(buildCard(course));
    } else {
      for (const course of courses) nodes.push(buildCard(course));
    }
  } else {
    for (const course of courses) nodes.push(buildCard(course));
  }

  replaceChildren(grid, nodes);
  renderSearchLectures(matchedLectures);
  if (filtersBar) filtersBar.hidden = false;
  grid.hidden = courses.length === 0;
  detail.hidden = true;
  empty.hidden = courses.length !== 0 || matchedLectures.length !== 0;
  status.textContent = trimmed
    ? `找到 ${courses.length} 门匹配课程 · ${matchedLectures.length} 份讲义`
    : `共 ${courses.length} 门课程`;
}

function renderDetail(courseId) {
  const course = catalog.courses.find(candidate => candidate.id === courseId);
  if (!course) {
    history.replaceState(null, '', location.pathname + location.search);
    renderCourses(search.value);
    return;
  }
  const courseItems = course.item_ids.map(id => items.get(id)).filter(Boolean);
  const bundles = courseItems.filter(item => item.kind === 'bundle');
  const webCount = courseItems.filter(item => Boolean(item.web)).length;
  const lectureCount = course.lecture_count ?? (courseItems.length - bundles.length || courseItems.length);

  const heading = document.createElement('div');
  heading.className = 'course-detail-heading';
  const back = document.createElement('button');
  back.className = 'back-link detail-back';
  back.type = 'button';
  back.textContent = '← 返回课程列表';
  back.addEventListener('click', () => {
    history.pushState(null, '', location.pathname + location.search);
    renderCourses(search.value);
    focusReturn?.focus();
  });
  const label = document.createElement('p');
  label.className = 'eyebrow';
  label.textContent = `${course.institution} / ${course.term}`;
  const title = document.createElement('h2');
  title.id = 'course-detail-title';
  title.tabIndex = -1;
  title.textContent = course.title;
  const description = document.createElement('p');
  description.className = 'course-detail-description';
  description.textContent = course.description;

  const summaryBar = document.createElement('div');
  summaryBar.className = 'course-detail-summary';
  const statsBadge = document.createElement('span');
  statsBadge.className = 'detail-summary-pill';
  statsBadge.textContent = `${lectureCount} 讲 · ${course.page_count} 页`;
  summaryBar.append(statsBadge);
  if (webCount > 0) {
    const webBadge = document.createElement('span');
    webBadge.className = 'detail-summary-pill web-badge';
    webBadge.textContent = `${webCount} 讲支持网页 + PDF 双模式精读`;
    summaryBar.append(webBadge);
  }
  if (course.source_url) {
    const sourceLink = document.createElement('a');
    sourceLink.className = 'detail-source-link';
    sourceLink.href = course.source_url;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noopener';
    sourceLink.textContent = '课程原视频 / 主页 ↗';
    summaryBar.append(sourceLink);
  }

  heading.append(back, label, title, description, summaryBar);

  if (bundles.length > 0) {
    const bundleCallout = document.createElement('div');
    bundleCallout.className = 'course-bundles-callout';
    const bundleLabel = document.createElement('p');
    bundleLabel.className = 'course-bundles-label';
    bundleLabel.textContent = '合集速览：支持直接打开完整合集 PDF';
    const bundleLinks = document.createElement('div');
    bundleLinks.className = 'course-bundles-links';
    for (const bundle of bundles) {
      const link = document.createElement('a');
      link.className = 'button button-secondary bundle-quick-link';
      link.href = readerUrl(bundle.id);
      link.textContent = `阅读合集 · ${bundle.title}（${bundle.pages} 页）↗`;
      bundleLinks.append(link);
    }
    bundleCallout.append(bundleLabel, bundleLinks);
    heading.append(bundleCallout);
  }

  const list = document.createElement('div');
  list.className = 'item-list';
  const rows = [];
  for (const item of courseItems) {
    const row = createItemRow(item);
    rows.push({item, row});
    list.append(row);
  }

  if (courseItems.length >= 6) {
    const filterWrap = document.createElement('div');
    filterWrap.className = 'detail-filter-bar';
    const filterInput = document.createElement('input');
    filterInput.type = 'text';
    filterInput.className = 'detail-filter-input';
    filterInput.placeholder = '在本课程中筛选讲次（输入讲次号、标题或关键词）…';
    filterInput.setAttribute('aria-label', '筛选本课讲次');
    const filterCount = document.createElement('span');
    filterCount.className = 'detail-filter-count';
    filterCount.textContent = `显示全部 ${courseItems.length} 项`;
    filterInput.addEventListener('input', () => {
      const needle = normalize(filterInput.value).trim();
      let visible = 0;
      for (const {item, row} of rows) {
        const match =
          !needle ||
          [item.title, item.instructor, item.meta, String(item.order || '')].some(val =>
            normalize(val).includes(needle),
          );
        row.hidden = !match;
        if (match) visible += 1;
      }
      filterCount.textContent = needle
        ? `匹配 ${visible} / ${courseItems.length} 项`
        : `显示全部 ${courseItems.length} 项`;
    });
    filterWrap.append(filterInput, filterCount);
    heading.append(filterWrap);
  }

  replaceChildren(detail, [heading, list]);
  grid.hidden = true;
  if (filtersBar) filtersBar.hidden = true;
  if (searchLecturesBox) searchLecturesBox.hidden = true;
  empty.hidden = true;
  detail.hidden = false;
  title.focus({preventScroll: true});
  detail.scrollIntoView({
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
    block: 'start',
  });
}

function route() {
  if (location.hash === '#papers-title') {
    location.replace('papers.html');
    return;
  }
  const match = location.hash.match(/^#course=(.+)$/);
  if (!match) {
    renderCourses(search.value);
    if (location.hash === '#library-title') {
      requestAnimationFrame(() => {
        document.querySelector(location.hash)?.scrollIntoView({behavior: 'instant', block: 'start'});
      });
    }
    return;
  }
  try {
    renderDetail(decodeURIComponent(match[1]));
  } catch {
    history.replaceState(null, '', location.pathname + location.search);
    renderCourses(search.value);
  }
}

function bindControls() {
  search.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (!detail.hidden) {
        history.pushState(null, '', location.pathname + location.search);
      }
      renderCourses(search.value);
    }, 120);
  });
  if (filtersBar) {
    filtersBar.addEventListener('click', event => {
      const button = event.target.closest('.filter-chip');
      if (!button) return;
      currentFilter = button.dataset.filter || 'all';
      updateFilterChips();
      if (!detail.hidden) {
        history.pushState(null, '', location.pathname + location.search);
      }
      renderCourses(search.value);
    });
  }
  document.addEventListener('keydown', event => {
    if (event.key === '/' && document.activeElement !== search && !event.target.closest('input')) {
      event.preventDefault();
      search.focus();
    }
  });
  window.addEventListener('hashchange', route);
}

async function start() {
  error.hidden = true;
  try {
    catalog = await loadCatalog();
    items = itemMap(catalog);
    renderStats();
    updateFilterChips();
    bindControls();
    route();
  } catch (cause) {
    grid.hidden = true;
    detail.hidden = true;
    error.hidden = false;
    document.querySelector('#catalog-error-message').textContent = cause.message;
  }
}

document.querySelector('#catalog-retry').addEventListener('click', () => location.reload());
if (location.hash === '#papers-title') location.replace('papers.html');
else start();
