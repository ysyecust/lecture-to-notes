import {loadCatalog} from './catalog.js';
import {createPaperCard} from './components.js';

const grid = document.querySelector('#paper-grid');
const status = document.querySelector('#papers-status');
const error = document.querySelector('#papers-error');

async function start() {
  error.hidden = true;
  status.textContent = '正在加载论文目录…';
  try {
    const catalog = await loadCatalog();
    grid.replaceChildren(...catalog.papers.map(createPaperCard));
    status.textContent = catalog.papers.length ? `共 ${catalog.papers.length} 篇解读` : '暂未收录论文解读';
  } catch {
    status.textContent = '';
    error.hidden = false;
  }
}

document.querySelector('#papers-retry').addEventListener('click', start);
start();
