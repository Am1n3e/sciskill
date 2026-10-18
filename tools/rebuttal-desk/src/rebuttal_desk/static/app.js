/* Original Rebuttal Desk layout, driven by workspace data. */
let workspace;
let activeView="analysis";
let taskReviewer="all";
const originalToggle = document.createElement('button');
originalToggle.type = 'button';
originalToggle.className = 'original-switch';
originalToggle.setAttribute('role', 'switch');
originalToggle.setAttribute('aria-checked', 'true');
originalToggle.setAttribute('aria-label', 'Annotations');
originalToggle.innerHTML = '<span>Annotations</span><span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>';
let showOriginal = false;
function applyOriginalView() {
  content.querySelectorAll('.workbench-drawer').forEach(item => { item.hidden = showOriginal || (item.classList.contains('annotation-pane') && item.dataset.open!=='true'); });
  content.querySelectorAll('.original-review').forEach(item=>{item.hidden=!showOriginal;});
  content.querySelectorAll('.annotated-review').forEach(item=>{item.hidden=showOriginal;});
}
originalToggle.addEventListener('click', () => { showOriginal = !showOriginal; originalToggle.setAttribute('aria-checked', String(!showOriginal)); applyOriginalView(); });
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
  item.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && followWorkspaceLink(link.getAttribute('href'))) event.preventDefault();
  });
  return item;
}
function followWorkspaceLink(href) {
  if (!href?.startsWith('#')) return false;
  const target = href.slice(1);
  const theme = workspace.analysis.themes.find(item => target === `theme-${item.id}`);
  if (theme) {
    setView('analysis');
    const section = document.getElementById(target);
    section.open = true;
    section.scrollIntoView({block:'start'});
    return true;
  }
  if (workspace.tasks.some(item => target === `task-${item.id}`)) {
    taskReviewer = 'all';
    renderTasks();
    setView('tasks');
    document.getElementById(target).scrollIntoView({block:'center'});
    return true;
  }
  const [reviewId, concernId, extra] = target.split('/');
  const review = workspace.reviews.find(item => item.id === reviewId);
  if (!review || extra !== undefined || (concernId && !review.concerns.some(item => item.id === concernId))) return false;
  showOriginal = false;
  originalToggle.setAttribute('aria-checked', 'true');
  setView('reviews');
  // Re-render even when revisiting the currently selected concern from another tab.
  history.pushState(null, '', href);
  render();
  if (!concernId) document.getElementById('reviews-panel').scrollIntoView({block:'start'});
  return true;
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

  const panels = node('div');
  function show(mode) {
    for (const panel of panels.children) panel.hidden = panel.dataset.mode !== mode;
    for (const button of tabs.querySelectorAll('[data-mode]')) {
      const active = button.dataset.mode === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    }
  }
  for (const mode of ['response']) {
    const button = node('button', mode === 'response' ? 'Response' : 'Analysis', 'workbench-tab');
    button.type='button'; button.dataset.mode=mode; button.id=`${concern.id}-${mode}-tab`;
    button.setAttribute('role','tab'); button.setAttribute('aria-controls',`${concern.id}-${mode}`);
    button.addEventListener('click',()=>show(mode));
    const panel = node('div', undefined, 'workbench-panel'); panel.dataset.mode=mode; panel.id=`${concern.id}-${mode}`;
    panel.setAttribute('aria-label','Response');
    if (mode==='response') {
      const section=node('section',undefined,'section-block');
      const response=node('div',undefined,'response-markdown response-main');
      const stats=count(concern.response.source);
      const overall = count(review.concerns.map(c => c.response.source).filter(drafted).map(source => source.trim()).join('\n\n'));
      const limit = workspace.presentation.character_limit;
      const total = `Overall: ${overall.characters.toLocaleString()}${limit ? ` / ${limit.toLocaleString()}` : ''} characters`;
      const textbox=node('textarea',undefined,'response-textbox');textbox.value=concern.response.source;textbox.rows=6;textbox.readOnly=true;textbox.setAttribute('aria-label',`${concern.id} response draft`);
      response.append(node('div',`${stats.words} words · ${stats.characters} characters · ${total}`,'response-metrics'),textbox);
      section.append(response); panel.append(section);
    } else panel.append(prose(concern.analysis.html,'external-markdown analysis-markdown markdown-rendered'));
    panels.append(panel);
  }
  for(const theme of workspace.analysis.themes.filter(item=>item.annotations.includes(concern.id))){const link=node('a',`Theme ${theme.number}: ${theme.title}`,'concern-theme-link');link.href=`#theme-${theme.id}`;link.addEventListener('click',event=>{event.preventDefault();setView('analysis');document.getElementById(`theme-${theme.id}`).scrollIntoView({block:'start'});});tabs.append(link);}
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
function attachAnnotations(reviewText,review,selected){
  const attached=new Set();
  for(const mark of reviewText.querySelectorAll('mark.review-annotation')){
    const identity=mark.dataset.annotationId;
    const concern=review.concerns.find(item=>item.id===identity);
    if(!concern)continue;
    attached.add(identity);
    const drawer=concernDrawer(concern,review,selected);
    const pane=node('div',undefined,'annotation-pane workbench-drawer');pane.id=identity;pane.dataset.open=String(selected===identity);pane.hidden=selected!==identity;
    const header=node('div',undefined,'annotation-pane-header');
    const headingBlock=node('div',undefined,'annotation-heading-block');
    const type=mark.dataset.annotationType==='change_request'?'Change request':'Clarification';
    const subtype={manuscript_change:'Manuscript change',additional_experiments:'Additional experiments'}[mark.dataset.annotationSubtype];
    headingBlock.append(drawer.querySelector('.drawer-heading'),node('span',subtype?`${type} / ${subtype}`:type,`annotation-kind-label kind-${mark.dataset.annotationType}`));
    const close=node('button',undefined,'annotation-close');close.type='button';close.setAttribute('aria-label',`Close ${identity} pane`);close.title='Close';
    close.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';
    close.addEventListener('click',()=>{pane.dataset.open='false';pane.hidden=true;mark.setAttribute('aria-expanded','false');mark.focus();});
    const chips=node('div',undefined,'annotation-chips');chips.append(headingBlock.querySelector('.annotation-kind-label'));drawer.querySelectorAll('.concern-theme-link').forEach(link=>chips.append(link));headingBlock.append(chips);
    header.append(headingBlock,drawer.querySelector('.response-metrics'),close);
    drawer.querySelector('.workbench-tabs').remove();
    pane.append(header,drawer.querySelector('.workbench-body'));
    const anchor=mark.closest('p,li')||mark;anchor.after(pane);
    mark.dataset.annotationLabel=identity.includes('-C')?'C'+identity.split('-C').pop():identity;
    mark.classList.add('annotation-link');mark.setAttribute('role','link');mark.tabIndex=0;mark.setAttribute('aria-expanded',pane.dataset.open);mark.setAttribute('aria-controls',identity);
    function toggle(event){
      if(event.target.closest('a'))return;
      event.preventDefault();const open=pane.dataset.open!=='true';pane.dataset.open=String(open);pane.hidden=!open;mark.setAttribute('aria-expanded',String(open));
    }
    mark.addEventListener('click',toggle);
    mark.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' ')toggle(event);});
  }
  return attached;
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
function setView(view){
  activeView=view;
  for(const name of ['analysis','reviews','tasks']){
    document.getElementById(`${name}-panel`).hidden=name!==view;
    document.getElementById(`${name}-tab`).setAttribute('aria-selected',String(name===view));
    document.getElementById(`${name}-tab`).tabIndex=name===view?0:-1;
  }
}
function renderTasks(){
  const selector=document.getElementById('task-reviewer');selector.replaceChildren();
  const all=node('option','All reviewers');all.value='all';selector.append(all);
  for(const review of workspace.reviews){const option=node('option',review.label);option.value=review.id;selector.append(option);}
  selector.value=taskReviewer;
  const selected=workspace.reviews.find(review=>review.id===taskReviewer);
  const ids=new Set(selected?.concerns.map(concern=>concern.id)||[]);
  const priority={high:0,medium:1,low:2};
  const tasks=(workspace.tasks||[]).filter(task=>!selected||task.annotations.some(id=>ids.has(id))).slice().sort((a,b)=>priority[a.priority]-priority[b.priority]);
  document.getElementById('task-count').textContent=`${tasks.length} ${tasks.length===1?'task':'tasks'}`;
  const list=document.getElementById('task-list');list.replaceChildren();
  const table=node('table',undefined,'task-table');const head=node('thead');const row=node('tr');
  for(const label of ['Task','Status','Priority','Effort']){const cell=node('th',label);cell.scope='col';row.append(cell);}head.append(row);table.append(head);
  const body=node('tbody');
  for(const task of tasks){
    const row=node('tr');row.id=`task-${task.id}`;const main=node('td');main.append(node('strong',`Task ${task.id}: ${task.title}`,'task-title'));
    const links=node('div',undefined,'task-sources');
    for(const identity of task.annotations){const link=relatedLink(identity);link.addEventListener('click',()=>setView('reviews'));links.append(link);}main.append(links);
    if(task.note)main.append(node('p',task.note,'task-note'));
    if(task.external_link){const external=node('a','External link','task-external');external.href=task.external_link;external.target='_blank';external.rel='noopener noreferrer';main.append(external);}
    const status={proposed:'Proposed',pending:'Pending',in_progress:'In progress',done:'Done',not_doing:'Not doing'}[task.status];
    row.append(main,node('td',status,'task-status'),node('td',task.priority,'task-priority'),node('td',task.effort,'task-effort'));body.append(row);
  }
  if(!tasks.length){const row=node('tr');const cell=node('td',workspace.tasks?.length?'No tasks match this reviewer.':'No tasks yet.');cell.colSpan=4;cell.className='task-empty';row.append(cell);body.append(row);}
  table.append(body);list.append(table);
}
function renderAnalysis(){
  const panel=document.getElementById('analysis-panel');panel.replaceChildren();
  if(workspace.analysis.overview){const overview=node('section',undefined,'analysis-overview');overview.append(node('h2','Overview'),prose(workspace.analysis.overview.html));panel.append(overview);}
  const themes = [...workspace.analysis.themes].sort((a,b)=>new Set(b.reviewers).size-new Set(a.reviewers).size || a.number-b.number);
  for(const theme of themes){
    const section=node('details',undefined,'analysis-theme');section.id=`theme-${theme.id}`;const header=node('summary',undefined,'theme-header');const identity=node('div',undefined,'theme-identity');identity.append(node('h2',`Theme ${theme.number}: ${theme.title}`));
    identity.append(node('p',`${theme.reviewers.length} ${theme.reviewers.length===1?'reviewer':'reviewers'} · ${theme.reviewers.join(', ')}`,'theme-reviewers'));
    const annotations=node('div',undefined,'theme-links');annotations.append(node('strong','Related reviews'));
    for(const id of theme.annotations){const link=relatedLink(id);link.addEventListener('click',()=>{showOriginal=false;originalToggle.setAttribute('aria-checked','true');setView('reviews');});annotations.append(link);}
    const tasks=node('div',undefined,'theme-links');tasks.append(node('strong','Related tasks'));
    for(const id of theme.tasks){const task=workspace.tasks.find(item=>item.id===id);const link=node('a',`Task ${task.id}: ${task.title}`);link.href=`#task-${id}`;link.addEventListener('click',event=>{event.preventDefault();taskReviewer='all';renderTasks();setView('tasks');document.getElementById(`task-${id}`).scrollIntoView({block:'center'});});tasks.append(link);}
    header.append(identity,annotations,tasks);section.append(header,prose(theme.content.html,'markdown-rendered theme-body'));panel.append(section);
  }
  if(!workspace.analysis.themes.length)panel.append(node('p','No analysis yet.'));
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
  const hasAnnotations=Boolean(review.document.annotated_html?.includes('data-annotation-id'));
  const reviewText=prose(hasAnnotations?review.document.annotated_html:review.document.html,'note-content-value markdown-rendered'+(hasAnnotations?' annotated-review':''));
  if(hasAnnotations){const original=prose(review.document.html,'note-content-value markdown-rendered original-review');original.hidden=true;body.append(original);}
  body.append(reviewText);
  const markedIds=hasAnnotations?attachAnnotations(reviewText,review,concernId):new Set();
  for (const concern of review.concerns) {
    if(markedIds.has(concern.id))continue;
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
  applyOriginalView();renderTasks();renderAnalysis();setView(activeView);
  if(concernId && !showOriginal)document.getElementById(concernId)?.scrollIntoView({block:'center'});
}
async function load(){try{const response=await fetch('/workspace.json');if(!response.ok)throw new Error('Workspace could not be loaded.');workspace=await response.json();document.querySelector('#workspace-title').textContent=workspace.title;render();}catch(error){content.replaceChildren(node('p',error.message));}}
for(const [index,name] of ['analysis','reviews','tasks'].entries()){
  const button=document.getElementById(`${name}-tab`);button.addEventListener('click',()=>setView(name));
  button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const names=['analysis','reviews','tasks'];const next=names[event.key==='Home'?0:event.key==='End'?2:(index+(event.key==='ArrowRight'?1:2))%3];setView(next);document.getElementById(`${next}-tab`).focus();}});
}
document.getElementById('task-reviewer').addEventListener('change',event=>{taskReviewer=event.target.value;if(workspace)renderTasks();});
window.addEventListener('hashchange',()=>{if(workspace)render();});load();

document.getElementById('reload-workspace').addEventListener('click',()=>load());
