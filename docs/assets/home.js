import {itemMap, loadCatalog, searchCourses} from './catalog.js';
import {createCourseCard, createItemRow, createPaperCard} from './components.js';

const grid = document.querySelector('#course-grid');
const detail = document.querySelector('#course-detail');
const empty = document.querySelector('#empty-state');
const status = document.querySelector('#library-status');
const search = document.querySelector('#course-search');
const error = document.querySelector('#catalog-error');
const paperGrid = document.querySelector('#paper-grid');
let catalog;
let items;
let focusReturn;
let debounceTimer;

function replaceChildren(node, children) {
  node.replaceChildren(...children);
}

function renderStats() {
  document.querySelector('#stat-courses').textContent = catalog.stats.course_count;
  document.querySelector('#stat-lectures').textContent = catalog.stats.lecture_count;
  document.querySelector('#stat-pages').textContent = catalog.stats.page_count;
  document.querySelector('#stat-papers').textContent = catalog.stats.paper_count;
}

function renderPapers() {
  replaceChildren(paperGrid, catalog.papers.map(createPaperCard));
}

function renderCourses(query = '') {
  const courses = searchCourses(catalog, query);
  const cards = courses.map(course => {
    const courseItems = course.item_ids.map(id => items.get(id)).filter(Boolean);
    const card = createCourseCard(course, courseItems);
    card.querySelector('.course-link').addEventListener('click', event => {
      focusReturn = event.currentTarget;
    });
    return card;
  });
  replaceChildren(grid, cards);
  grid.hidden = false;
  detail.hidden = true;
  empty.hidden = courses.length !== 0;
  status.textContent = query ? `找到 ${courses.length} 门匹配课程` : `共 ${courses.length} 门课程`;
}

function renderDetail(courseId) {
  const course = catalog.courses.find(candidate => candidate.id === courseId);
  if (!course) {
    history.replaceState(null, '', location.pathname + location.search);
    renderCourses(search.value);
    return;
  }
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
  description.textContent = course.description;
  heading.append(back, label, title, description);
  const list = document.createElement('div');
  list.className = 'item-list';
  for (const id of course.item_ids) {
    const item = items.get(id);
    if (item) list.append(createItemRow(item));
  }
  replaceChildren(detail, [heading, list]);
  grid.hidden = true;
  empty.hidden = true;
  detail.hidden = false;
  title.focus({preventScroll: true});
  detail.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
}

function route() {
  const match = location.hash.match(/^#course=(.+)$/);
  if (!match) {
    renderCourses(search.value);
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
    debounceTimer = setTimeout(() => renderCourses(search.value), 120);
  });
  document.addEventListener('keydown', event => {
    if (event.key === '/' && document.activeElement !== search) {
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
    renderPapers();
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
start();
