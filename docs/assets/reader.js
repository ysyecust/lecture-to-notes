import {itemMap, loadCatalog, readerUrl} from './catalog.js';

const title = document.querySelector('#reader-title');
const meta = document.querySelector('#reader-meta');
const courseLabel = document.querySelector('#reader-course');
const frame = document.querySelector('#pdf-frame');
const stage = document.querySelector('#pdf-stage');
const error = document.querySelector('#reader-error');
const courseNav = document.querySelector('#course-nav');
const selector = document.querySelector('#mobile-item-select');
const openLink = document.querySelector('#open-pdf');
const downloadLink = document.querySelector('#download-pdf');
const sourceLink = document.querySelector('#source-link');

function showError(message) {
  stage.hidden = true;
  error.hidden = false;
  title.textContent = '讲义不可用';
  meta.textContent = message;
  document.querySelector('.reader-actions').hidden = true;
  selector.closest('.mobile-selector').hidden = true;
}

function navLink(item, active) {
  const link = document.createElement('a');
  link.href = readerUrl(item.id);
  link.className = active ? 'active' : '';
  if (active) link.setAttribute('aria-current', 'page');
  const number = document.createElement('span');
  number.textContent = item.kind === 'bundle' ? 'ALL' : String(item.order).padStart(2, '0');
  const label = document.createElement('span');
  label.textContent = item.title;
  link.append(number, label);
  return link;
}

function render(catalog, item) {
  const course = catalog.courses.find(candidate => candidate.id === item.course_id);
  if (!course) return showError('课程信息缺失，请返回课程库。');
  const items = itemMap(catalog);
  const courseItems = course.item_ids.map(id => items.get(id)).filter(Boolean);
  document.title = `${item.title} · Lecture to Notes`;
  courseLabel.textContent = `${course.institution} / ${course.title}`;
  title.textContent = item.title;
  meta.textContent = `${item.pages} 页 · ${item.kind === 'bundle' ? '课程合集' : `第 ${item.order} 讲`}`;
  frame.src = `${item.pdf}#view=FitH`;
  openLink.href = item.pdf;
  downloadLink.href = item.pdf;
  downloadLink.download = item.pdf.split('/').pop();
  if (item.source_url || course.source_url) {
    sourceLink.href = item.source_url || course.source_url;
    sourceLink.hidden = false;
  }
  courseNav.replaceChildren(...courseItems.map(candidate => navLink(candidate, candidate.id === item.id)));
  selector.replaceChildren(...courseItems.map(candidate => {
    const option = document.createElement('option');
    option.value = candidate.id;
    option.textContent = candidate.title;
    option.selected = candidate.id === item.id;
    return option;
  }));
  selector.addEventListener('change', () => {
    location.href = readerUrl(selector.value);
  });
}

async function start() {
  try {
    const id = new URLSearchParams(location.search).get('id');
    if (!id) return showError('链接中缺少讲义编号。');
    const catalog = await loadCatalog();
    const item = itemMap(catalog).get(id);
    if (!item) return showError('目录中没有这份讲义。');
    render(catalog, item);
  } catch (cause) {
    showError(`课程目录加载失败：${cause.message}`);
  }
}

start();
