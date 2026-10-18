/* Original Rebuttal Desk layout, driven by workspace data. */
let workspace;
const content = document.querySelector('#content');
const nav = document.querySelector('#reviewer-nav');
function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function prose(html, className = 'markdown-rendered') {
  const item = node('div', undefined, className);
  item.innerHTML = html; // Sanitized by the local server.
  return item;
}
function drafted(source) { return Boolean(source.trim()) && !/^\[?\s*tbd\s*\]?$/i.test(source.trim()); }
function count(source) { return {words: source.trim() ? source.trim().split(/\s+/u).length : 0, characters: Array.from(source).length}; }
function relatedLink(id) {
  const review = workspace.reviews.find(r => r.concerns.some(c => c.id === id));
  const link = node('a', id, 'related-chip');
  link.href = `#${review.id}/${id}`;
  link.addEventListener('click', event => event.stopPropagation());
  return link;
}
function concernDrawer(concern, review, selected) {
  const drawer = node('details', undefined, 'workbench-drawer');
  drawer.id = concern.id;
  drawer.open = selected === concern.id;
  const summary = node('summary');
  const heading = node('span', undefined, 'drawer-heading');
  heading.append(node('span', concern.id, 'drawer-kicker'), node('span', concern.title, 'drawer-title'));
  summary.append(heading);
  if (concern.related.length) {
    const links = node('span', undefined, 'related-links');
    links.append(node('span', 'related:', 'related-label'));
    concern.related.forEach(id => links.append(relatedLink(id)));
    summary.append(links);
  }
  drawer.append(summary);
  const body = node('div', undefined, 'workbench-body');
  const tabs = node('div', undefined, 'workbench-tabs');
  tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label',`${concern.id} workbench`);
  const panels = node('div');
  function show(mode) {
    for (const panel of panels.children) panel.hidden = panel.dataset.mode !== mode;
    for (const button of tabs.querySelectorAll('[data-mode]')) {
      const active = button.dataset.mode === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    }
  }
  for (const mode of ['response','analysis']) {
    const button = node('button', mode === 'response' ? 'Response' : 'Analysis', 'workbench-tab');
    button.type='button'; button.dataset.mode=mode; button.id=`${concern.id}-${mode}-tab`;
    button.setAttribute('role','tab'); button.setAttribute('aria-controls',`${concern.id}-${mode}`);
    button.addEventListener('click',()=>show(mode)); tabs.append(button);
    const panel = node('div', undefined, 'workbench-panel'); panel.dataset.mode=mode; panel.id=`${concern.id}-${mode}`;
    panel.setAttribute('role','tabpanel'); panel.setAttribute('aria-labelledby',button.id);
    if (mode==='response') {
      const section=node('section',undefined,'section-block');
      const response=node('div',undefined,'response-markdown response-main');
      const stats=count(concern.response.source);
      response.append(node('div',`${stats.words} words · ${stats.characters} characters`,'response-metrics'),prose(concern.response.html,'response-rendered markdown-rendered'));
      section.append(response); panel.append(section);
    } else panel.append(prose(concern.analysis.html,'external-markdown analysis-markdown markdown-rendered'));
    panels.append(panel);
  }
  const refresh=node('button','Refresh','drawer-refresh'); refresh.type='button';refresh.addEventListener('click',()=>load());tabs.append(refresh);
  body.append(tabs,panels);drawer.append(body);show('response');
  drawer.addEventListener('toggle',()=>{if(drawer.open) history.replaceState(null,'',`#${review.id}/${concern.id}`);});
  return drawer;
}
function aggregate(review) {
  const responses=review.concerns.map(c=>c.response).filter(c=>drafted(c.source));
  const source=responses.map(c=>c.source.trim()).join('\n\n');const stats=count(source);
  const card=node('section',undefined,'aggregate-response');
  const header=node('header',undefined,'aggregate-response-header');header.append(node('h2','Final response'));
  const metrics=node('p',undefined,'aggregate-response-metrics');
  metrics.append(node('span',`${responses.length} / ${review.concerns.length} responses drafted`,'aggregate-addressed'));
  const limit=workspace.presentation.character_limit;
  metrics.append(node('span',`${stats.characters.toLocaleString()}${limit ? ` / ${limit.toLocaleString()}` : ''} characters`,limit && stats.characters>limit?'aggregate-limit is-over-limit':'aggregate-limit'),node('span',`${stats.words} words`));
  header.append(metrics);card.append(header);
  const body=node('div',undefined,'aggregate-response-body markdown-rendered');
  if(responses.length) responses.forEach(c=>body.append(prose(c.html)));
  else body.append(node('p','No response drafts yet.','aggregate-empty'));
  card.append(body);return card;
}
function render() {
  const [reviewId,concernId]=location.hash.slice(1).split('/');
  const review=workspace.reviews.find(r=>r.id===reviewId)||workspace.reviews[0];nav.replaceChildren();
  for(const candidate of workspace.reviews){
    const button=node('button',undefined,'reviewer-button');button.type='button';button.classList.toggle('active',candidate===review);
    button.setAttribute('aria-current',candidate===review?'page':'false');
    button.append(node('span',candidate.label),node('span',candidate.concerns.length,'reviewer-count'));
    button.addEventListener('click',()=>{location.hash=candidate.id;});nav.append(button);
  }
  const article=node('article',undefined,'review-document');
  const note=node('div',undefined,'openreview-note note depth-odd');
  const heading=node('div',undefined,'heading');heading.append(node('h4',`Official Review by ${review.label}`));
  const subheading=node('div',undefined,'subheading');subheading.append(node('span','Official Review','invitation highlight'),node('span',`by ${review.label}`,'signatures'));
  const container=node('div',undefined,'note-content-container');const body=node('div',undefined,'note-content');
  body.append(node('strong','Review:','note-content-field disable-tex-rendering'),prose(review.document.html,'note-content-value markdown-rendered'));
  body.append(node('strong','Concerns / questions:','note-content-field disable-tex-rendering'));
  const list=node('ol',undefined,'note-content-value');review.concerns.forEach(c=>{const item=node('li');item.append(node('p',c.title),concernDrawer(c,review,concernId));list.append(item);});body.append(list);
  if(review.comments.length){body.append(node('strong','Comments:','note-content-field'));review.comments.forEach(c=>body.append(node('h4',c.label),prose(c.document.html)));}
  container.append(body);note.append(heading,subheading,container);article.append(note);content.replaceChildren(article,aggregate(review));
  if(concernId)document.getElementById(concernId)?.scrollIntoView({block:'center'});
}
async function load(){try{const response=await fetch('/workspace.json');if(!response.ok)throw new Error('Workspace could not be loaded.');workspace=await response.json();document.querySelector('#workspace-title').textContent=workspace.title;render();}catch(error){content.replaceChildren(node('p',error.message));}}
window.addEventListener('hashchange',()=>{if(workspace)render();});load();
