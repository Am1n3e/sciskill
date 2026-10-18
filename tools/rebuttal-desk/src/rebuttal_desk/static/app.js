/* Original Rebuttal Desk layout, driven by workspace data. */
let workspace;
const originalToggle = document.createElement('button');
originalToggle.type = 'button';
originalToggle.className = 'original-switch';
originalToggle.setAttribute('role', 'switch');
originalToggle.setAttribute('aria-checked', 'false');
originalToggle.setAttribute('aria-label', 'Hide drafts');
originalToggle.innerHTML = '<span>Hide drafts</span><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>';
let showOriginal = false;
function applyOriginalView() {
  content.querySelectorAll('.workbench-drawer').forEach(item => { item.hidden = showOriginal; });
}
originalToggle.addEventListener('click', () => { showOriginal = !showOriginal; originalToggle.setAttribute('aria-checked', String(showOriginal)); applyOriginalView(); });
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
  const index = review.concerns.findIndex(c => c.id === id) + 1;
  const link = node('a', `${review.label} · Concern ${index}`, 'related-chip');
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
  const concernNumber = review.concerns.findIndex(c => c.id === concern.id) + 1;
  heading.append(node('span', `${review.label} · Concern ${concernNumber}: ${concern.title}`, 'drawer-kicker'));
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
      const overall = count(review.concerns.map(c => c.response.source).filter(drafted).map(source => source.trim()).join('\n\n'));
      const limit = workspace.presentation.character_limit;
      const total = `Overall: ${overall.characters.toLocaleString()}${limit ? ` / ${limit.toLocaleString()}` : ''} characters`;
      response.append(node('div',`${stats.words} words · ${stats.characters} characters · ${total}`,'response-metrics'),prose(concern.response.html,'response-rendered markdown-rendered'));
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
  const header=node('header',undefined,'aggregate-response-header');const titleBlock=node('div',undefined,'aggregate-title');
  titleBlock.append(node('h2','Final response'),node('p','Combined from the drafts above. Read-only—edit the individual drafts.','aggregate-description'));
  header.append(titleBlock);
  const metrics=node('p',undefined,'aggregate-response-metrics');
  metrics.append(node('span',`${responses.length} / ${review.concerns.length} responses drafted`,'aggregate-addressed'));
  const limit=workspace.presentation.character_limit;
  metrics.append(node('span',`${stats.characters.toLocaleString()}${limit ? ` / ${limit.toLocaleString()}` : ''} characters`,limit && stats.characters>limit?'aggregate-limit is-over-limit':'aggregate-limit'),node('span',`${stats.words} words`));
  const copy = node('button', undefined, 'copy-final-response');
  copy.type = 'button'; copy.setAttribute('aria-label', 'Copy final response'); copy.title = 'Copy final response';
  copy.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>';
  const status = node('span', '', 'sr-only'); status.setAttribute('role', 'status');
  copy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(source); status.textContent = 'Final response copied.'; copy.title = 'Copied'; const icon = copy.innerHTML; copy.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>'; window.setTimeout(() => { copy.innerHTML = icon; copy.title = 'Copy final response'; }, 1500); }
    catch { status.textContent = 'Unable to copy. Select the response text to copy it.'; copy.title = 'Unable to copy'; }
  });
  header.append(metrics, copy, status);card.append(header);
  const body=node('div',undefined,'aggregate-response-body markdown-rendered');
  if(responses.length) responses.forEach(c=>body.append(prose(c.html)));
  else body.append(node('p','No response drafts yet.','aggregate-empty'));
  card.append(body);return card;
}
function renderConversation(review,article,initialCard){
  const initialId=review.document_id||review.id;
  const cards=new Map([[initialId,initialCard]]);
  const replies=new Map(review.comments.map(comment=>[comment.id,comment]));
  function depth(comment){
    let level=0,current=comment;
    while(current.reply_to){
      level++;
      current=replies.get(current.reply_to);
      if(!current)break;
    }
    return level;
  }
  for(const comment of review.comments){
    const card=node('div',undefined,`openreview-note note depth-${depth(comment)%2?'even':'odd'}`);
    card.dataset.commentId=comment.id;
    const heading=node('div',undefined,'heading');heading.append(node('h4',comment.label));
    const meta=node('div',undefined,'subheading');
    if(comment.type){
      const kind=comment.type==='author_response'?'Author response':'Reviewer comment';
      heading.append(node('span',kind,`comment-kind ${comment.type}`));
      meta.append(node('span',`by ${comment.author}`,'signatures'),node('span',comment.created_at.replace('T',' '),'created-date'));
    }
    const body=node('div',undefined,'note-content');body.append(prose(comment.document.html));
    card.append(heading,meta,body);cards.set(comment.id,card);
  }
  for(const comment of review.comments){
    const parent=cards.get(comment.reply_to);
    if(!parent){article.append(cards.get(comment.id));continue;}
    let group=Array.from(parent.children).find(child=>child.classList.contains('note-replies'));
    if(!group){group=node('div',undefined,'note-replies');parent.append(group);}
    group.append(cards.get(comment.id));
  }
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
  const heading=node('div',undefined,'heading');heading.append(node('h4',`Official Review by ${review.label}`), originalToggle);
  const subheading=node('div',undefined,'subheading');subheading.append(node('span','Official Review','invitation highlight'),node('span',`by ${review.label}`,'signatures'));
  const container=node('div',undefined,'note-content-container');const body=node('div',undefined,'note-content');
  const reviewText=prose(review.document.html,'note-content-value markdown-rendered');
  body.append(reviewText);
  for (const concern of review.concerns) {
    const normalized=concern.question.replace(/\s+/g,' ').trim();
    const candidates=Array.from(reviewText.querySelectorAll('p, li'));
    const anchor=candidates.find(item=>item.textContent.replace(/\s+/g,' ').trim()===normalized);
    const drawer=concernDrawer(concern,review,concernId);
    if(anchor) anchor.append(drawer);
    else body.append(node('p',concern.question),drawer);
  }
  container.append(body);note.append(heading,subheading,container);article.append(note);
  renderConversation(review,article,note);
  content.replaceChildren(article,aggregate(review));
  applyOriginalView();
  if(concernId && !showOriginal)document.getElementById(concernId)?.scrollIntoView({block:'center'});
}
async function load(){try{const response=await fetch('/workspace.json');if(!response.ok)throw new Error('Workspace could not be loaded.');workspace=await response.json();document.querySelector('#workspace-title').textContent=workspace.title;render();}catch(error){content.replaceChildren(node('p',error.message));}}
window.addEventListener('hashchange',()=>{if(workspace)render();});load();
