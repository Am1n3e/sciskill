/* Generalized from the local Rebuttal Review Desk; no paper-specific data. */
let workspace;
const content = document.querySelector('#content');
const nav = document.querySelector('#reviewer-nav');
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function prose(html) {
  const item = node('div', undefined, 'markdown-rendered');
  // HTML is sanitized server-side; CSP additionally blocks scripts and remote resources.
  item.innerHTML = html;
  return item;
}
function drafted(source) { return Boolean(source.trim()) && !/^\[?\s*tbd\s*\]?$/i.test(source.trim()); }
function metrics(source) { return `${source.trim() ? source.trim().split(/\s+/u).length : 0} words · ${Array.from(source).length} characters`; }
function aggregate(review) {
  const sources = review.concerns.map(c => c.response.source).filter(drafted);
  const source = sources.map(s => s.trim()).join('\n\n');
  const card = node('section', undefined, 'aggregate-response');
  card.append(node('h2', 'Assembled response'));
  const limit = workspace.presentation.character_limit;
  const count = Array.from(source).length;
  const detail = `${sources.length} / ${review.concerns.length} responses drafted · ${metrics(source)}`;
  card.append(node('p', `${detail}${limit ? ` · limit ${limit}${count > limit ? ' (over limit)' : ''}` : ''}`));
  card.append(node('p', 'Drafted means a nonempty response, not a resolved concern.'));
  card.append(node('pre', source || 'No response drafts yet.', 'aggregate-plain'));
  return card;
}
function relatedLink(id) {
  const review = workspace.reviews.find(r => r.concerns.some(c => c.id === id));
  const link = node('a', id, 'related-chip');
  link.href = `#${review.id}/${id}`;
  return link;
}
function concernDrawer(concern, selected) {
  const drawer = node('details', undefined, 'workbench-drawer');
  drawer.id = concern.id;
  drawer.open = selected === concern.id;
  drawer.append(node('summary', concern.title));
  const tabs = node('div', undefined, 'workbench-tabs');
  const body = node('div');
  function show(mode) {
    body.replaceChildren(prose(concern[mode].html));
    if (mode === 'response') body.prepend(node('p', metrics(concern.response.source)));
    for (const button of tabs.children) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  }
  for (const mode of ['response', 'analysis']) {
    const button = node('button', mode === 'response' ? 'Response' : 'Analysis', 'workbench-tab');
    button.type = 'button'; button.dataset.mode = mode;
    button.addEventListener('click', () => show(mode)); tabs.append(button);
  }
  drawer.append(tabs, body);
  if (concern.related.length) {
    const links = node('p', 'Related concerns: ');
    concern.related.forEach(id => links.append(relatedLink(id), ' ')); drawer.append(links);
  }
  show('response');
  return drawer;
}
function render() {
  const [reviewId, concernId] = location.hash.slice(1).split('/');
  const review = workspace.reviews.find(r => r.id === reviewId) || workspace.reviews[0];
  nav.replaceChildren();
  for (const candidate of workspace.reviews) {
    const button = node('button', `${candidate.label} (${candidate.concerns.length})`, 'reviewer-button');
    button.type = 'button'; button.setAttribute('aria-current', candidate === review ? 'page' : 'false');
    button.addEventListener('click', () => { location.hash = candidate.id; }); nav.append(button);
  }
  content.className = `content profile-${workspace.presentation.profile}`;
  content.replaceChildren(node('h2', review.label), prose(review.document.html));
  if (review.comments.length) {
    const comments = node('section', undefined, `review-comments ${workspace.presentation.comment_layout}`);
    comments.append(node('h3', 'Comments'));
    for (const comment of review.comments) {
      const entry = node('article', undefined, 'review-comment');
      entry.append(node('h4', comment.label), prose(comment.document.html));
      comments.append(entry);
    }
    content.append(comments);
  }
  review.concerns.forEach(c => content.append(concernDrawer(c, concernId)));
  content.append(aggregate(review));
  if (concernId) document.getElementById(concernId)?.scrollIntoView({block:'center'});
}
async function load() {
  try {
    const response = await fetch('/workspace.json');
    if (!response.ok) throw new Error('Workspace validation failed. Run rebuttal-desk validate.');
    workspace = await response.json();
    document.querySelector('#title').textContent = workspace.title;
    render();
  } catch (error) { content.replaceChildren(node('p', error.message)); }
}
document.querySelector('#refresh').addEventListener('click', load);
window.addEventListener('hashchange', () => { if (workspace) render(); });
load();
