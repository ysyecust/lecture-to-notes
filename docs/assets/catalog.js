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

export function courseMatchesFilter(course, items, filterMode = 'all') {
  if (filterMode === 'university') return Boolean(course.featured);
  if (filterMode === 'collection') return !course.featured;
  if (filterMode === 'web') {
    return course.item_ids.some(id => Boolean(items.get(id)?.web));
  }
  return true;
}

export function searchCourses(catalog, query, filterMode = 'all') {
  const needle = normalize(query).trim();
  const items = itemMap(catalog);
  return catalog.courses.filter(course => {
    if (!courseMatchesFilter(course, items, filterMode)) return false;
    if (!needle) return true;
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

export function searchLectures(catalog, query, filterMode = 'all') {
  const needle = normalize(query).trim();
  if (!needle) return [];
  const items = itemMap(catalog);
  const courseById = new Map(catalog.courses.map(course => [course.id, course]));
  const matches = [];
  for (const item of catalog.items) {
    const course = courseById.get(item.course_id);
    if (!course || !courseMatchesFilter(course, items, filterMode)) continue;
    const matched = [
      item.title,
      item.instructor,
      item.meta,
      course.title,
      ...(course.tags || []),
    ].some(value => normalize(value).includes(needle));
    if (matched) matches.push({item, course});
  }
  return matches;
}

export function readerUrl(itemId) {
  const params = new URLSearchParams({id: itemId});
  return `reader.html?${params.toString()}`;
}
