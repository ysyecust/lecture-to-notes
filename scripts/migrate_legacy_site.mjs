import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';


const root = process.cwd();
const html = fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8');
const match = html.match(/const DATA = (\[[\s\S]*?\n\]);/);
if (!match) throw new Error('legacy DATA array not found');
const data = vm.runInNewContext(match[1], Object.create(null), {timeout: 1000});

const groups = {
  nju: {
    id: 'nju-os',
    title: '操作系统：设计与实现',
    institution: '南京大学',
    term: '2026 公开课',
    description: '从硬件抽象、进程与地址空间一路走到并发、GPU 和大模型系统。',
    tags: ['操作系统', '系统编程', '并发'],
    featured: false,
  },
  yt: {
    id: 'technical-lectures',
    title: '技术公开课精选',
    institution: 'Multiple',
    term: '精选',
    description: '矩阵计算、优化与流变学等工程主题的深度公开课。',
    tags: ['工程', '优化', '公开课'],
    featured: false,
  },
  sci: {
    id: 'science-explainers',
    title: '工程与科学科普',
    institution: 'Multiple',
    term: '精选',
    description: '从器件、制造到物理机制的工程科普笔记。',
    tags: ['科学', '工程', '硬件'],
    featured: false,
  },
  llm: {
    id: 'large-model-systems',
    title: '大模型系统与注意力优化',
    institution: 'Multiple',
    term: '精选',
    description: '自注意力、KV Cache、FlashAttention 与 PagedAttention 的系统笔记。',
    tags: ['LLM', 'GPU', '注意力'],
    featured: false,
  },
  talk: {
    id: 'technical-talks',
    title: '技术与研究分享',
    institution: 'Multiple',
    term: '精选',
    description: '研究者与工程师关于学习、科研与职业选择的主题分享。',
    tags: ['研究', '分享'],
    featured: false,
  },
};

for (const [category, group] of Object.entries(groups)) {
  const directory = path.join(root, 'content/courses', group.id);
  fs.mkdirSync(directory, {recursive: true});
  const legacyItems = data.filter(item => item.type === 'lecture' && item.cat === category);
  const items = legacyItems.map((item, index) => {
    const source = path.join(root, 'docs', item.pdf);
    const file = path.basename(item.pdf);
    const destination = path.join(directory, file);
    if (!fs.existsSync(source)) throw new Error(`missing legacy PDF: ${source}`);
    fs.renameSync(source, destination);
    const pageMatch = String(item.meta || '').match(/(\d+)\s*页/);
    const durationMatch = String(item.meta || '').match(/(\d+)\s*min/);
    return {
      legacy_id: item.id,
      file,
      title: item.title,
      order: /^\d+$/.test(item.num) ? Number(item.num) : index + 1,
      expected_pages: pageMatch ? Number(pageMatch[1]) : null,
      duration_minutes: durationMatch ? Number(durationMatch[1]) : null,
      instructor: String(item.meta || '').split('·')[0].trim(),
      source_url: item.link,
      source_label: item.linkLabel,
      meta: item.meta,
    };
  });
  fs.writeFileSync(
    path.join(directory, 'course.json'),
    JSON.stringify({...group, items}, null, 2) + '\n',
  );
}

const papers = data
  .filter(item => item.type === 'paper')
  .map(item => ({
    id: item.id,
    title: item.title,
    meta: item.meta,
    url: item.url,
    icon: item.icon,
    style: item.cls,
  }));
fs.mkdirSync(path.join(root, 'content'), {recursive: true});
fs.writeFileSync(
  path.join(root, 'content/papers.json'),
  JSON.stringify(papers, null, 2) + '\n',
);
