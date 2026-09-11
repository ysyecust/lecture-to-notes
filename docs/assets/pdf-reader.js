// PDF.js owns scaling and rendering; the browser's native PDF plug-in is unused.
export async function createPdfReader(container, viewerElement, onChange) {
  const lib = await import('./vendor/pdfjs/build/pdf.mjs');
  globalThis.pdfjsLib = lib;
  lib.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdfjs/build/pdf.worker.mjs', import.meta.url).href;
  const {EventBus, PDFViewer, PDFLinkService, PDFFindController} = await import('./vendor/pdfjs/web/pdf_viewer.mjs');
  const eventBus = new EventBus();
  const linkService = new PDFLinkService({eventBus, externalLinkTarget: 2, externalLinkRel: 'noopener noreferrer'});
  const findController = new PDFFindController({eventBus, linkService});
  const viewer = new PDFViewer({container, viewer: viewerElement, eventBus, linkService, findController,
    imageResourcesPath: new URL('./vendor/pdfjs/web/images/', import.meta.url).href,
    textLayerMode: 1, annotationMode: lib.AnnotationMode.ENABLE, removePageBorders: true,
    maxCanvasPixels: 16777216, maxCanvasDim: 8192, enableDetailCanvas: true});
  linkService.setViewer(viewer);
  let loadingTask, document, ready = false;
  eventBus.on('pagechanging', e => onChange({page: e.pageNumber}));
  eventBus.on('scalechanging', e => onChange({scale: e.scale, scaleValue: viewer.currentScaleValue}));
  eventBus.on('updateviewarea', e => {if (ready) onChange({location: e.location, scaleValue: viewer.currentScaleValue});});
  eventBus.on('updatefindmatchescount', e => onChange({matches: e.matchesCount}));
  return {
    async load(url, saved) {
      loadingTask = lib.getDocument({url, cMapUrl: new URL('./vendor/pdfjs/cmaps/', import.meta.url).href,
        cMapPacked: true, standardFontDataUrl: new URL('./vendor/pdfjs/standard_fonts/', import.meta.url).href,
        isEvalSupported: false, useWasm: false});
      document = await loadingTask.promise;
      const initialized = new Promise(resolve => eventBus.on('pagesinit', resolve, {once: true}));
      viewer.setDocument(document); linkService.setDocument(document); await initialized;
      const storedScale = saved?.scaleValue;
      const scale = ['page-width','page-fit'].includes(storedScale) ? storedScale : Number.isFinite(Number(storedScale)) && Number(storedScale)>0 ? String(Math.max(.25,Math.min(8,Number(storedScale)))) : 'page-width';
      viewer.currentScaleValue = container.clientWidth ? scale : '1';
      if (Number.isInteger(saved?.page) && saved.page>0) viewer.scrollPageIntoView({pageNumber: Math.max(1, Math.min(document.numPages, saved.page)),
        destArray: [null, {name:'XYZ'}, Number.isFinite(saved.left) ? saved.left : 0, Number.isFinite(saved.top) ? saved.top : null, null], allowNegativeOffset: true});
      ready = true; viewer.update();
      return {pages: document.numPages, outline: await document.getOutline()};
    },
    page(value) {if (document) viewer.currentPageNumber = Math.max(1, Math.min(document.numPages, value));},
    next(delta) {if (document) viewer.currentPageNumber = Math.max(1, Math.min(document.numPages, viewer.currentPageNumber + delta));},
    zoom(value) {viewer.currentScaleValue = typeof value === 'number' ? String(Math.max(.25, Math.min(8, value))) : value;},
    zoomBy(factor) {viewer.currentScale = Math.max(.25, Math.min(8, viewer.currentScale * factor));},
    refresh() {if (ready) {viewer.currentScaleValue = viewer.currentScaleValue; viewer.update();}},
    find(query, again = false) {eventBus.dispatch('find', {source: this, type: again ? 'again' : '', query,
      caseSensitive:false, entireWord:false, highlightAll:true, findPrevious:false, matchDiacritics:false});},
    goTo(destination) {return linkService.goToDestination(destination);},
    get pageNumber() {return viewer.currentPageNumber;},
    async destroy() {ready = false; viewer.setDocument(null); await loadingTask?.destroy();},
  };
}
