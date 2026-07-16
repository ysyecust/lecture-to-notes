export async function loadCatalog() {
  const response = await fetch('./data/catalog.json', {credentials: 'same-origin'});
  if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
  const catalog = await response.json();
  if (catalog.schema_version !== 1) throw new Error('Unsupported catalog schema');
  return catalog;
}

export function normalize(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase('zh-CN');
}

export function itemMap(catalog) {
  return new Map(catalog.items.map(item => [item.id, item]));
}

export function searchCourses(catalog, query) {
  const needle = normalize(query).trim();
  if (!needle) return catalog.courses;
  const items = itemMap(catalog);
  return catalog.courses.filter(course => {
    const lectures = course.item_ids.map(id => items.get(id)).filter(Boolean);
    return [
      course.title,
      course.institution,
      course.term,
      course.description,
      ...(course.tags || []),
      ...lectures.flatMap(item => [item.title, item.instructor, item.meta]),
    ].some(value => normalize(value).includes(needle));
  });
}

export function readerUrl(itemId) {
  const params = new URLSearchParams({id: itemId});
  return `reader.html?${params.toString()}`;
}
