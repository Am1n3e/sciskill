'use strict';
let state, detail, poll, requestPending=false, detailVersion=0, detailFocus=null;
const $=id=>document.getElementById(id);
const number=new Intl.NumberFormat();
const detailRoot=document.getElementById('reference-detail');
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
function badge(status,text=status){const cls=status==='Correct'||status==='Match'||status==='Found'?'good':status==='Invalid'||status==='Mismatch'||status==='Failed'?'bad':['Needs review','Partial match','Unresolved','Insufficient data'].includes(status)?'review':'info';return node('span',text,`chip ${cls}`);}
function message(text,error=false){const el=node('p',text,`notice${error?' error':''}`);$('messages').append(el);}
function json(value){return node('pre',JSON.stringify(value,null,2),'code');}
function safeLink(text,url){try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return node('span',text);const a=node('a',text,'external');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return node('span',text);}}
function params(){return new URLSearchParams(location.search);}
function route(changes){const p=params();for(const [key,value] of Object.entries(changes)){if(value===null||value==='')p.delete(key);else p.set(key,value);}history.pushState(null,'',`${location.pathname}${p.size?'?'+p:''}`);renderReferences();renderRoute();}
async function api(path,options){const response=await fetch(path,{cache:'no-store',...options});const data=await response.json();if(!response.ok)throw new Error(data.error||'Could not read the audit. Reload and try again.');return data;}
function table(headers,rows,render,className=''){const wrap=node('div',undefined,'table-scroll');const t=node('table',undefined,className);const head=node('tr');headers.forEach(text=>{const th=node('th',text);th.scope='col';head.append(th);});const thead=node('thead');thead.append(head);const body=node('tbody');rows.forEach(row=>{const tr=node('tr');render(tr,row);body.append(tr);});if(!rows.length){const td=node('td','No entries to show.','table-empty');td.colSpan=headers.length;const tr=node('tr');tr.append(td);body.append(tr);}t.append(thead,body);wrap.append(t);return wrap;}
function cell(tr,value,cls){const td=node('td',undefined,cls);td.append(value instanceof Node?value:node('span',String(value??'—')));tr.append(td);return td;}
function populateSetup(){const input=state.audit_input||{};if(!state.report_path){$('setup').open=true;return;}if(!state.summary||$('setup').dataset.path===state.report_path)return;$('setup').dataset.path=state.report_path;$('report').value=state.report_path;$('cache-dir').value=state.cache_dir;$('agent-path').value=state.agent_path;$('cache-dir').dataset.custom='';$('agent-path').dataset.custom='';$('bibliography').value=input.path||'';$('aux').value=input.aux||'';$('output').value=input.path?state.metadata.output_directory:'';}
function isPdfInput(){return /\.pdf$/i.test($('bibliography').value.trim());}
function updateInputOptions(){const pdf=isPdfInput();$('aux').disabled=pdf;$('pdf-input-help').hidden=!pdf;}
function renderExtractionCoverage(){
  const region=$('extraction-status'),extraction=state.summary?.extraction;
  region.replaceChildren();region.hidden=!extraction||extraction.state==='complete';if(region.hidden)return;
  region.className='notice extraction-coverage';
  region.append(node('strong','PDF reference coverage needs review'));
  region.append(node('p',`${extraction.unresolved_fragments} unresolved ${extraction.unresolved_fragments===1?'fragment':'fragments'} · reference pages ${extraction.reference_pages.join(', ')||'unknown'}. Finished source checks do not establish complete extraction.`));
  if(extraction.diagnostics.length){
    const details=node('details');details.append(node('summary','Extraction warnings'));const list=node('ul');
    for(const issue of extraction.diagnostics)list.append(node('li',`${issue.page?`Page ${issue.page}: `:''}${issue.message}`));
    details.append(list);region.append(details);
  }
}
function pdfPanel(panel){
  const evidence=detail.pdf;
  panel.append(node('h3','PDF extraction evidence'));
  panel.append(node('p',`Printed label: ${evidence.label??'unnumbered'} · extraction: ${(detail.extraction?.state||'needs_review').replace('_',' ')}`,'muted small'));
  if(evidence.diagnostics.length){const issues=node('ul',undefined,'notice');for(const issue of evidence.diagnostics)issues.append(node('li',`${issue.code}: ${issue.message}`));panel.append(issues);}
  panel.append(node('h3','Interpreted reference text'),node('pre',evidence.text,'code'));
  panel.append(node('h3','Original PDF fragments'),node('p','Page numbers refer to physical PDF pages. Boxes use PDF points from the top-left corner.','muted small'));
  for(const [index,fragment] of evidence.fragments.entries()){
    const section=node('section',undefined,'pdf-fragment');
    section.append(node('h4',`Fragment ${index+1} · page ${fragment.page}`),node('p',`Box: ${[fragment.x0,fragment.top,fragment.x1,fragment.bottom].map(v=>number.format(v)).join(', ')}`,'muted small'),node('pre',fragment.text,'code'));panel.append(section);
  }
  panel.append(node('h3','Field provenance'));
  const fields=[];
  for(const [field,mappings] of Object.entries(evidence.field_evidence))for(const mapping of mappings){
    if(mapping.uri!==undefined){const uri=evidence.uris[mapping.uri];fields.push({field,fragment:`URI ${mapping.uri+1}`,page:uri.page,text:uri.uri});}
    else{const fragment=evidence.fragments[mapping.fragment];fields.push({field,fragment:`Fragment ${mapping.fragment+1}`,page:fragment.page,text:fragment.text.slice(mapping.start,mapping.end)});}
  }
  panel.append(table(['Field','Evidence','Physical page','Original evidence'],fields,(tr,row)=>{cell(tr,row.field);cell(tr,row.fragment);cell(tr,row.page);cell(tr,row.text);},'comparison-table'));
  panel.append(node('h3','PDF URI targets'),node('p','These are hyperlink targets associated with this reference, separate from the printed text. Extraction does not follow them.','muted small'));
  panel.append(table(['Physical page','URI target'],evidence.uris,(tr,row)=>{cell(tr,row.page);cell(tr,safeLink(row.uri,row.uri));},'comparison-table'));
}
function renderHeader(){
  $('setup').hidden=Boolean(state.read_only);
  $('audit-summary').hidden=!state.summary;if(!state.summary)return;
  const m=state.metadata,s=state.summary,input=state.audit_input||{};
  $('summary-input').replaceChildren(node('code',typeof m.bibliography==='string'?m.bibliography:m.report_path));
  const options=[];
  if(input.aux)options.push(`AUX: ${input.aux}`);
  if(m.output_directory)options.push(`Output: ${m.output_directory}`);
  if(input.encoding)options.push(`Encoding: ${input.encoding}`);
  if(input.include_source)options.push('Include source');
  if(s.scope==='unknown')options.push('Citation scope unknown; counts reflect saved results');
  if(s.eligible!==s.total)options.push(`${number.format(s.eligible)} ${s.eligible===1?'reference':'references'} selected for checking`);
  if(s.skipped)options.push(`${number.format(s.skipped)} ${s.skipped===1?'reference':'references'} skipped`);
  $('summary-options-row').hidden=!options.length;
  $('summary-options').textContent=options.join(' · ');
  $('summary-total-label').textContent=m.input_kind==='pdf'?'Extracted references':'References';
  for(const [id,value] of Object.entries({total:s.total,processed:s.completed,correct:s.statuses.Correct||0,invalid:s.statuses.Invalid||0,review:s.statuses['Needs review']||0,partial:s.statuses['Partial match']||0,unresolved:s.statuses.Unresolved||0,pending:s.statuses.Pending||0})){
    $(`summary-${id}`).textContent=number.format(value);
  }
}
function renderReferences(){
  if(!state)return;
  const focused=document.activeElement;
  detailFocus=detailRoot.contains(focused)||focused?.matches('.reference-toggle')?focused:null;
  const p=params();$('search').value=p.get('q')||'';$('hide-unused').checked=p.get('hide_unused')==='1';$('attention').checked=p.get('attention')==='1';
  const query=(p.get('q')||'').toLowerCase();
  const rows=state.rows.filter(r=>(!$('hide-unused').checked||(r['Used in paper']!=='No'&&r.Status!=='Skipped'))&&(!$('attention').checked||r.needs_attention)&&[r['Citation key'],r.title,r.Note,r['Agent note']].join(' ').toLowerCase().includes(query));
  $('reference-filters').hidden=!state.summary;$('visible-count').hidden=!state.summary;
  $('visible-count').textContent=`${number.format(rows.length)} of ${number.format(state.rows.length)} references`;
  if(!state.summary){$('references-table').replaceChildren(node('p',state.loading?'Waiting for the first saved result…':'Choose an input or open a saved audit to see its references.','empty-state muted'));return;}
  $('references-table').replaceChildren(table(['Reference','Status','Finding','Source checks'],rows,(tr,row)=>{
    const ref=node('div'),button=node('button',row.title||row['Citation key'],'reference-title reference-toggle');button.type='button';button.dataset.key=row['Citation key'];
    const marker=node('span',p.get('key')===row['Citation key']?'−':'+','expand-marker');marker.setAttribute('aria-hidden','true');button.prepend(marker);
    button.setAttribute('aria-controls','reference-detail');button.setAttribute('aria-expanded',String(p.get('key')===row['Citation key']));
    button.addEventListener('click',()=>{
      route({key:params().get('key')===row['Citation key']?null:row['Citation key'],detail:null});
      [...document.querySelectorAll('.reference-toggle')].find(b=>b.dataset.key===row['Citation key'])?.focus();
    });
    ref.append(button,node('span',row['Citation key'],'citation-key'));cell(tr,ref);
    const statuses=node('div');statuses.append(badge(row.Status));
    if(row.Agent)statuses.append(node('p','Agent','small muted'),badge(row.Agent));cell(tr,statuses);
    const finding=node('div');finding.append(node('p',row.Status==='Correct'&&!row.source_failed?'—':row.Note,'finding-note'));
    if(row['Agent note'])finding.append(node('p',row['Agent note'],'muted small'));cell(tr,finding);
    const checked=node('div',undefined,'source-count');
    checked.append(node('span',`${row.records_found} ${row.records_found===1?'record':'records'} found`),node('span',`${row.sources_checked} ${row.sources_checked===1?'source check':'source checks'}`,'muted small'));cell(tr,checked);
  },'references-table'));
}
function renderJob(){const job=state.job,bar=$('job-status');bar.hidden=!job;if(!job)return;bar.replaceChildren();const head=node('div',undefined,'job-heading');head.append(node('strong',`Audit: ${job.result?.status||job.state}`));const b=node('button',['running','stopping'].includes(job.state)?'Stop':'Resume');b.type='button';b.dataset.action=['running','stopping'].includes(job.state)?'stop':'resume';b.disabled=job.state==='stopping'||requestPending;if(['running','stopping'].includes(job.state)||job.result?.complete!==true)head.append(b);bar.append(head);if(state.summary){const progress=node('progress');progress.max=state.summary.eligible||1;progress.value=state.summary.eligible?state.summary.completed:1;progress.setAttribute('aria-label','Verification progress');bar.append(progress,node('p',`${state.summary.completed}/${state.summary.eligible} eligible entries completed`,'muted small'));}if(job.error)bar.append(node('p',job.error,'notice error'));if(job.logs?.length){const d=node('details');d.append(node('summary','Verification diagnostics'),node('pre',job.logs.join(''),'code'));bar.append(d);}}
function controls(){updateInputOptions();const busy=requestPending||['running','stopping'].includes(state?.job?.state);$('audit-fields').disabled=busy;document.querySelectorAll('.key-action').forEach(b=>b.disabled=busy||!$('citation-key').value.trim());$('reload-workspace').disabled=requestPending;}
function accept(data){
  state=data;$('messages').replaceChildren();if(data.error)message(data.error,true);data.warnings.forEach(w=>message(w));
  populateSetup();renderHeader();renderReferences();renderJob();renderExtractionCoverage();controls();renderRoute();
  clearTimeout(poll);if(['running','stopping'].includes(data.job?.state))poll=setTimeout(()=>load(),1000);
}
async function load(force=false){if(force===true)delete detailRoot.dataset.signature;try{accept(await api('/api/state'));}catch(error){$('messages').replaceChildren();message(error.message,true);}}
async function action(name){if(requestPending)return;requestPending=true;clearTimeout(poll);controls();const payload={action:name,bibliography:$('bibliography').value.trim(),aux:isPdfInput()?'':$('aux').value.trim(),output:$('output').value.trim(),key:$('citation-key').value.trim(),report:$('report').value.trim(),cache_dir:$('cache-dir').dataset.custom?$('cache-dir').value.trim():'',agent_path:$('agent-path').dataset.custom?$('agent-path').value.trim():''};try{const data=await api('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify(payload)});if(name==='open'||name==='parse'||data.report_path!==state.report_path)history.replaceState(null,'','/');accept(data);$('setup').open=false;}catch(error){$('messages').replaceChildren();message(error.message,true);if(!payload.bibliography&&['verify','parse','refresh'].includes(name))$('bibliography').focus();if(['running','stopping'].includes(state?.job?.state))poll=setTimeout(()=>load(),1000);}finally{requestPending=false;controls();if(state)renderJob();}}
function restoreReferenceFocus(){
  const target=detailFocus?.isConnected?detailFocus:[...document.querySelectorAll('.reference-toggle')].find(b=>b.dataset.key===detailFocus?.dataset.key);
  target?.focus({preventScroll:true});detailFocus=null;
}
function renderRoute(){
  const key=params().get('key');
  const button=[...document.querySelectorAll('.reference-toggle')].find(b=>b.dataset.key===key);
  if(!key||!button){
    detailVersion++;delete detailRoot.dataset.signature;delete detailRoot.dataset.identity;detailRoot.hidden=true;$('workspace-content').append(detailRoot);restoreReferenceFocus();return;
  }
  const expanded=node('tr',undefined,'expanded-reference'),cell=node('td');cell.colSpan=4;
  detailRoot.hidden=false;cell.append(detailRoot);expanded.append(cell);button.closest('tr').after(expanded);
  const signature=JSON.stringify([state.report_path,state.rows.find(row=>row['Citation key']===key)]);
  // Unrelated progress updates must not rebuild the reference being read.
  if(detailRoot.dataset.signature!==signature){detailRoot.dataset.signature=signature;loadDetail(key);}
  restoreReferenceFocus();
}
async function loadDetail(key){
  const identity=JSON.stringify([state.report_path,key]);
  const opened=detailRoot.dataset.identity===identity?new Set([...detailRoot.querySelectorAll('details[open]')].map(el=>el.firstElementChild.textContent)):new Set();
  detailRoot.dataset.identity=identity;
  const version=++detailVersion;detailRoot.replaceChildren(node('p','Loading reference checks…','muted'));
  try{
    const result=await api(`/api/reference?key=${encodeURIComponent(key)}`);
    if(version!==detailVersion)return;detail=result;renderDetail(key,opened);
  }catch(error){if(version===detailVersion){delete detailRoot.dataset.signature;detailRoot.replaceChildren(node('p',error.message,'notice error'));}}
}
function renderDetail(key,opened){
  detailRoot.replaceChildren();
  const top=node('div',undefined,'detail-top'),close=node('button','Close');close.type='button';close.setAttribute('aria-label','Close reference details');
  close.addEventListener('click',()=>{
    route({key:null,detail:null});[...document.querySelectorAll('.reference-toggle')].find(b=>b.dataset.key===key)?.focus();
  });
  top.append(node('strong','Reference checks'),close);detailRoot.append(top,node('p',detail.authors,'detail-authors'),node('p',detail.reason,'evidence-note'));
  comparison(detailRoot);
  if(detail.pdf)evidenceSection('PDF evidence',panel=>pdfPanel(panel));
  evidenceSection('Cached responses',panel=>responses(panel,key,true));
  evidenceSection('Raw log',panel=>panel.append(json({sources:detail.methods,...(detail.agent_review?{agent:detail.agent_review}:{})})));
  if(detail.agent_review)evidenceSection('Agent evidence',panel=>agentPanel(panel));
  for(const section of detailRoot.querySelectorAll('details'))if(opened.has(section.firstElementChild.textContent))section.open=true;
}
function evidenceSection(name,render){
  const section=node('details',undefined,'evidence-section'),body=node('div');section.append(node('summary',name),body);
  function populate(){if(section.open&&!body.childNodes.length)render(body);}
  section.addEventListener('toggle',populate);detailRoot.append(section);
  if(params().get('detail')===name){section.open=true;populate();}
}
function comparison(panel){
  if(detail.agent_review&&detail.agent_review.status!==detail.row.Status)panel.append(node('p',`Agent assessment: ${detail.agent_review.status}; automated assessment: ${detail.row.Status}. Review both sets of evidence before accepting a correction.`,'notice'));
  if(detail.suggestions.length){
    panel.append(node('h3','Suggested corrections'),table(['Field','Current','Suggested','Source'],detail.suggestions,(tr,row)=>['Field','Current','Suggested','Source'].forEach(k=>cell(tr,row[k])),'comparison-table'),node('p','Proposals only. Check the source link before accepting a correction; the bibliography has not been modified.','muted small'));
  }
  panel.append(node('h3','Field comparison'));
  const label=node('label',undefined,'inline-switch'),toggle=node('input');toggle.type='checkbox';
  const issues=detail.comparisons.some(r=>!['Match','Not checked'].includes(r.Status));
  toggle.checked=params().has('matches')?params().get('matches')==='1':!issues;
  label.append(toggle,node('span','Include matching fields'));panel.append(label);
  const area=node('div');
  function show(){
    const rows=detail.comparisons.filter(r=>toggle.checked||!['Match','Not checked'].includes(r.Status));
    area.replaceChildren(table(['Field','Your value','Source’s value','Status','Source'],rows,(tr,row)=>{cell(tr,row.Field);cell(tr,row['Your value']);cell(tr,row["Source's value"]);cell(tr,badge(row.Status));cell(tr,row.Source);},'comparison-table'));
  }
  toggle.addEventListener('change',()=>{const p=params();p.set('matches',toggle.checked?'1':'0');history.replaceState(null,'',`/?${p}`);show();});show();panel.append(area);
  panel.append(node('h3','Sources checked'),node('p',detail.lookup_summary,'muted small'));
  const sources=[...detail.sources];
  if(detail.agent_review)sources.push({Source:'agent',Name:'Agent assessment',Lookup:'Separate review',Status:[detail.agent_review.status],URL:detail.agent_review.evidence[0].url});
  panel.append(table(['Source','Lookup','Result','Evidence'],sources,(tr,row)=>{
    cell(tr,row.Name||row.Source);cell(tr,row.Lookup);
    const result=node('div');result.append(badge(row.Status[0]));
    if(row.Error)result.append(node('p',row.Error,'muted small'));
    cell(tr,result);cell(tr,row.URL?safeLink(row.Lookup==='DOI resolution'?'Resolved destination ↗':'Open source ↗',row.URL):'—');
  },'comparison-table'));
  const raw=node('details',undefined,'advanced');raw.append(node('summary','Original entry'),json(detail.entry));panel.append(raw);
}
function responses(panel,key,active){if(detail.cache_error)panel.append(node('p',detail.cache_error,'muted small'));if(!detail.responses.length){panel.append(node('p','No raw cached responses for this reference.','muted'));return;}const label=node('label','Response','response-selector'),select=node('select');select.setAttribute('aria-label','Cached response');detail.responses.forEach((entry,index)=>{const option=node('option',`${entry.method} · HTTP ${entry.status_code} · ${entry.retrieved_at||entry.cached_at||''}`);option.value=index;select.append(option);});label.append(select);const content=node('div');panel.append(label,content);let responseVersion=0;async function show(){const version=++responseVersion;content.replaceChildren(node('p','Loading response…','muted'));try{const data=await api(`/api/response?key=${encodeURIComponent(key)}&index=${select.value}`);if(version!==responseVersion||!content.isConnected)return;content.replaceChildren(node('p',`${data.entry.path} · SHA-256 verified`,'muted small'),node('pre',data.text,'code'));}catch(error){if(version===responseVersion)content.replaceChildren(node('p',error.message,'notice error'));}}select.addEventListener('change',show);if(active)show();}
function agentPanel(panel){const review=detail.agent_review;panel.append(node('h3','Agent evidence'),node('p',review.summary),node('p',`Reviewed ${review.reviewed_at} · Checked: ${review.checked_fields.join(', ')}`,'muted small'));for(const evidence of review.evidence){panel.append(safeLink(evidence.title||'Primary evidence',evidence.url),node('p',evidence.supports,'evidence-note'));}if(review.limitations)panel.append(node('p',review.limitations,'muted small'));}
$('reload-workspace').addEventListener('click',()=>load(true));
$('audit-form').addEventListener('submit',event=>{event.preventDefault();action('verify');});
$('open-form').addEventListener('submit',event=>{event.preventDefault();action('open');});
document.addEventListener('click',event=>{const button=event.target.closest('button[data-action]');if(button)action(button.dataset.action);});
$('citation-key').addEventListener('input',controls);
$('bibliography').addEventListener('input',controls);
for(const id of ['cache-dir','agent-path'])$(id).addEventListener('input',()=>{$(id).dataset.custom='true';});
for(const [id,key] of [['hide-unused','hide_unused'],['attention','attention']])$(id).addEventListener('change',()=>{route({[key]:$(id).checked?'1':null});});
$('search').addEventListener('input',()=>{const p=params();if($('search').value)p.set('q',$('search').value);else p.delete('q');history.replaceState(null,'',`/?${p}`);renderReferences();renderRoute();});
window.addEventListener('popstate',()=>{renderReferences();renderRoute();});
load();
