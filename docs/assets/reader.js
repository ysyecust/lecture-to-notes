import {itemMap, loadCatalog, readerUrl} from './catalog.js';
import {createPdfReader} from './pdf-reader.js';

const $ = selector => document.querySelector(selector);
const body = document.body;
const htmlContainer = $('#html-container');
const pdfContainer = $('#pdf-container');
let catalog, item, course, webDocument, pdf, pdfPromise, mode, stored = {}, saveTimer, htmlObserver;
const key = () => `lecture-reader:v2:${item.sha256}`;
const read = name => {try {const value=JSON.parse(localStorage.getItem(name) || '{}');return value && typeof value==='object' && !Array.isArray(value) ? value : {};} catch {return {};}};
const write = (name, value) => {try {localStorage.setItem(name, JSON.stringify(value));} catch { /* private mode still reads */ }};
function persist() {if (item) write(key(), stored);}
function scheduleSave() {clearTimeout(saveTimer); saveTimer = setTimeout(persist, 250);}
function error(message, canFallback = false) {
  $('#loading-status').hidden = true; $('#reader-error').hidden = false;
  $('#reader-error-message').textContent = message; $('#fallback-pdf').hidden = !canFallback;
}
function rail(open) {
  body.classList.toggle('rail-closed', !open); $('#toggle-rail').setAttribute('aria-expanded', String(open));
  requestAnimationFrame(() => pdf?.refresh());
}
function tab(name) {
  $('#course-panel').hidden = name !== 'course'; $('#outline-nav').hidden = name !== 'outline';
  $('#tab-course').setAttribute('aria-pressed', String(name === 'course'));
  $('#tab-outline').setAttribute('aria-pressed', String(name === 'outline'));
}
function textElement(tag, text, cls) {const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el;}
function renderCourse() {
  $('#reader-title').textContent = item.title; document.title = `${item.title} · Lecture to Notes`;
  $('#reader-course').textContent = `${course.institution} / ${course.title}`;
  $('#course-nav-title').textContent = course.title; $('#reader-meta').textContent = `${item.pages} 页 · ${item.kind === 'bundle' ? '课程合集' : `第 ${item.order} 讲`}`;
  $('.reader-rail .back-link').href = `index.html#course=${encodeURIComponent(course.id)}`;
  $('#open-pdf').href = item.pdf; $('#download-pdf').href = item.pdf; $('#download-pdf').download = item.pdf.split('/').pop();
  $('.reader-actions').hidden = false;
  if (item.source_url || course.source_url) {$('#source-link').href = item.source_url || course.source_url; $('#source-link').hidden = false;}
  const items = itemMap(catalog); const links = [], options = [];
  for (const id of course.item_ids) {
    const entry = items.get(id); if (!entry) continue;
    const link = textElement('a', '', id === item.id ? 'active' : ''); link.href = readerUrl(id);
    link.append(textElement('span', entry.kind === 'bundle' ? '合集' : String(entry.order).padStart(2,'0')),textElement('span',entry.title));
    if (id === item.id) link.setAttribute('aria-current','page'); links.push(link);
    const option = textElement('option',entry.title); option.value = id; option.selected = id === item.id; options.push(option);
  }
  $('#course-nav').replaceChildren(...links); $('#mobile-item-select').replaceChildren(...options);
  $('#format-html').hidden = !item.web;
}
function pdfUpdate(change) {
  if (change.page) $('#page-number').value = change.page;
  if (change.scale) {
    const scale = $('#pdf-zoom'); const selected = change.scaleValue;
    if (['page-width','page-fit'].includes(selected)) scale.value = selected;
    else {
      let option = scale.querySelector('[data-current]'); if (!option) {option = document.createElement('option');option.dataset.current='true';scale.append(option);}
      option.value = String(change.scale); option.textContent = `${Math.round(change.scale * 100)}%`; scale.value = option.value;
    }
    $('#zoom-in').disabled = change.scale >= 8; $('#zoom-out').disabled = change.scale <= .25;
  }
  if (change.matches) $('#find-count').textContent = `${change.matches.current} / ${change.matches.total}`;
  if (change.location) {
    stored.pdf = {page:change.location.pageNumber,top:change.location.top,left:change.location.left,scaleValue:change.scaleValue}; scheduleSave();
  }
}
async function ensurePdf() {
  if (!pdfPromise) pdfPromise = (async () => {
    pdf = await createPdfReader(pdfContainer, $('#pdf-viewer'), pdfUpdate);
    const result = await pdf.load(item.pdf, stored.pdf);
    $('#page-count').textContent = `/ ${result.pages}`; $('#page-number').max = result.pages;
    pdf.outline = result.outline; return pdf;
  })().catch(cause => {pdfPromise = null; pdf?.destroy(); pdf = null; throw cause;});
  return pdfPromise;
}
async function loadHtml() {
  if (webDocument) return;
  const [response, metadata] = await Promise.all([fetch(item.web.article),fetch(item.web.document)]);
  if (!response.ok || !metadata.ok) throw new Error('网页正文暂时无法加载');
  const source = await response.text(); const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source));
  if ([...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('') !== item.web.sha256) throw new Error('网页版与目录版本不一致');
  const model = await metadata.json(); if (model.schema_version !== 1 || model.item_id !== item.id) throw new Error('网页目录版本不匹配');
  const parsed = new DOMParser().parseFromString(source,'text/html'); const article = parsed.querySelector('article.web-document');
  if (!article || article.querySelector('script,iframe,object,embed,style,form,input')) throw new Error('网页正文格式无效');
  const resourceBase = new URL(item.web.article,location.href);
  for (const el of article.querySelectorAll('*')) {
    if ([...el.attributes].some(a=>a.name.startsWith('on'))) throw new Error('网页正文含无效属性');
    if (el.tagName === 'IMG') {
      const url = new URL(el.getAttribute('src'), resourceBase);
      if (url.origin !== location.origin || !url.href.startsWith(new URL('media/',resourceBase).href)) throw new Error('图片地址无效');
      el.src = url.href;
    }
  }
  const header = document.createElement('header'); header.className='web-document-header';
  header.append(textElement('p',`${course.institution} · ${item.instructor || ""} · ${course.term}`),textElement('h2',item.title),textElement('p',`网页阅读 · 原版 PDF ${item.pages} 页`));
  article.prepend(header); htmlContainer.replaceChildren(document.importNode(article,true)); webDocument = model;
  for (const image of htmlContainer.querySelectorAll('figure img')) {
    const button = document.createElement('button');button.className='figure-zoom';button.type='button';button.setAttribute('aria-label','放大图片');image.replaceWith(button);button.append(image);
    button.addEventListener('click',()=>{const dialog=$('#figure-dialog');dialog.querySelector('img').src=image.src;dialog.querySelector('img').alt=image.alt;dialog.querySelector('p').textContent=image.alt;dialog.showModal();});
  }
  for (const link of htmlContainer.querySelectorAll('a[href^="#"]')) link.addEventListener('click',event=>{
    const target=htmlContainer.querySelector(`[id="${CSS.escape(link.hash.slice(1))}"]`);if(target){event.preventDefault();target.scrollIntoView({block:'start'});}
  });
  applyTypography();
  htmlObserver = new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){
    for(const a of $('#outline-nav').querySelectorAll('button'))a.classList.toggle('active',a.dataset.target===e.target.id);
  }},{root:htmlContainer,rootMargin:'0px 0px -75% 0px'});
  htmlContainer.querySelectorAll('[data-chapter]').forEach(h=>htmlObserver.observe(h));
}
function buildOutline() {
  const nav=$('#outline-nav');nav.replaceChildren();
  if (mode==='html' && webDocument) for(const section of webDocument.sections){
    const button=textElement('button',section.title);button.type='button';button.dataset.target=section.id;
    button.addEventListener('click',()=>{const h=document.getElementById(section.id);h?.scrollIntoView({block:'start'});if(matchMedia('(max-width:820px)').matches)rail(false);});nav.append(button);
  } else if(mode==='pdf' && pdf?.outline){
    const add=(entries,depth=0)=>{for(const entry of entries){
      if(entry.dest){const button=textElement('button',entry.title);button.type='button';button.dataset.depth=String(Math.min(depth,3));button.addEventListener('click',()=>{pdf.goTo(entry.dest);if(matchMedia('(max-width:820px)').matches)rail(false);});nav.append(button);}
      if(entry.items?.length)add(entry.items,depth+1);
    }};add(pdf.outline);
  }
  if(!nav.childElementCount)nav.append(textElement('p','此文件没有章节书签，可使用页码导航。','reader-help'));
}
async function setMode(next) {
  if (!item || (next==='html'&&!item.web)) return;
  persist(); mode=next;stored.mode=next;write(key(),stored);
  $('#reader-error').hidden=true;$('#loading-status').hidden=false;
  htmlContainer.hidden=next!=='html';pdfContainer.hidden=next!=='pdf';
  $('#html-controls').hidden=next!=='html';$('#pdf-controls').hidden=next!=='pdf';
  $('#format-html').setAttribute('aria-pressed',String(next==='html'));$('#format-pdf').setAttribute('aria-pressed',String(next==='pdf'));
  try {
    if(next==='html'){
      const alreadyLoaded=!!webDocument;await loadHtml();
      if(!alreadyLoaded && stored.html?.version===item.web.sha256) requestAnimationFrame(()=>{
        const anchor=document.getElementById(stored.html.anchor);if(anchor)htmlContainer.scrollTop=anchor.offsetTop+(Number(stored.html.offset)||0);
      });
    } else {await ensurePdf();pdf.refresh();}
    if(mode===next){buildOutline();$('#loading-status').hidden=true;}
  } catch(cause){if(mode===next)error(`${next==='html'?'网页版':'PDF'}加载失败。${next==='html'?'可以切换到原版 PDF。':'可以在“更多”中直接打开，或使用下载链接。'}`,next==='html');}
}
const settings=read('lecture-reader:settings');let fontSize=Number(settings.fontSize)||20;
function applyTypography(){fontSize=Math.max(16,Math.min(28,fontSize));body.style.setProperty('--reading-font-size',fontSize+'px');body.classList.toggle('wide-text',$('#text-width').value==='wide');write('lecture-reader:settings',{fontSize,width:$('#text-width').value});}
$('#text-width').value=settings.width==='wide'?'wide':'comfortable';
$('#font-smaller').addEventListener('click',()=>{fontSize--;applyTypography();});$('#font-larger').addEventListener('click',()=>{fontSize++;applyTypography();});$('#text-width').addEventListener('change',applyTypography);
$('#toggle-rail').addEventListener('click',()=>rail(body.classList.contains('rail-closed')));
$('#focus-mode').addEventListener('click',()=>{const on=body.classList.toggle('focus-reading');$('#focus-mode').textContent=on?'退出专注':'专注阅读';$('#focus-mode').setAttribute('aria-pressed',String(on));requestAnimationFrame(()=>pdf?.refresh());});
$('#tab-course').addEventListener('click',()=>tab('course'));$('#tab-outline').addEventListener('click',()=>tab('outline'));
$('#format-html').addEventListener('click',()=>setMode('html'));$('#format-pdf').addEventListener('click',()=>setMode('pdf'));$('#fallback-pdf').addEventListener('click',()=>setMode('pdf'));
$('#mobile-item-select').addEventListener('change',()=>{persist();location.href=readerUrl($('#mobile-item-select').value);});
$('#previous-page').addEventListener('click',()=>pdf?.next(-1));$('#next-page').addEventListener('click',()=>pdf?.next(1));
$('#page-number').addEventListener('change',()=>{const n=Number($('#page-number').value);if(Number.isInteger(n)&&n>0)pdf?.page(n);else $('#page-number').value=pdf?.pageNumber||1;});
$('#pdf-zoom').addEventListener('change',()=>{const v=$('#pdf-zoom').value;pdf?.zoom(isNaN(Number(v))?v:Number(v));});
$('#zoom-out').addEventListener('click',()=>pdf?.zoomBy(1/1.2));$('#zoom-in').addEventListener('click',()=>pdf?.zoomBy(1.2));
let findTimer;$('#pdf-search').addEventListener('input',()=>{clearTimeout(findTimer);findTimer=setTimeout(()=>pdf?.find($('#pdf-search').value),200);});$('#find-next').addEventListener('click',()=>pdf?.find($('#pdf-search').value,true));
$('#pdf-search').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();pdf?.find($('#pdf-search').value,true);}});
$('#close-figure').addEventListener('click',()=>$('#figure-dialog').close());
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#figure-dialog').open){if(body.classList.contains('focus-reading'))$('#focus-mode').click();if(matchMedia('(max-width:820px)').matches)rail(false);}});
htmlContainer.addEventListener('scroll',()=>{if(!item?.web||mode!=='html')return;
  const heads=[...htmlContainer.querySelectorAll('[data-reading-block]')];const h=heads.filter(h=>h.offsetTop<=htmlContainer.scrollTop+80).at(-1)||heads[0];
  if(h){stored.html={version:item.web.sha256,anchor:h.id,offset:htmlContainer.scrollTop-h.offsetTop};scheduleSave();}
},{passive:true});
window.addEventListener('pagehide',persist);
new ResizeObserver(()=>{body.style.setProperty('--bar-height',$('.reader-bar').getBoundingClientRect().height+'px');pdf?.refresh();}).observe($('.reader-bar'));
rail(!matchMedia('(max-width:820px)').matches);
try {
  const id=new URLSearchParams(location.search).get('id');if(!id)throw new Error('链接中缺少讲义编号。');
  catalog=await loadCatalog();item=itemMap(catalog).get(id);if(!item)throw new Error('课程目录中没有这份讲义。');
  course=catalog.courses.find(c=>c.id===item.course_id);if(!course)throw new Error('课程信息缺失。');
  stored=read(key());renderCourse();
  const requested=new URLSearchParams(location.search).get('format');
  await setMode(requested==='pdf'?'pdf':requested==='html'&&item.web?'html':stored.mode==='pdf'?'pdf':item.web?'html':'pdf');
} catch(cause) {
  $('#reader-title').textContent='无法打开讲义';$('#reader-course').textContent='阅读暂不可用';
  $('.reader-actions').hidden=true;$('.mobile-selector').hidden=true;error(cause.message);
}
