const state = { page: "dashboard", projects: [], stats: {}, project: null, clip: null, settings: {}, sort: "score", brollResults: [], busy: false };
let projectPollTimer=null;
const $ = (sel, root=document) => root.querySelector(sel);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const iconPaths = {
  mark:'<path d="M4 12.5 10.5 5l1.8 5.2H20l-6.5 8  -1.8-5.7H4Z" fill="currentColor" stroke="none"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  film:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z" fill="currentColor" stroke="none"/>',
  folder:'<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h5l2 2h8A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/><path d="M3 9h18"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1a1.6 1.6 0 0 1-2.3 2.3l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.2a1.6 1.6 0 0 1-3.2 0v-.2a1.6 1.6 0 0 0-2.7-1.1l-.1.1a1.6 1.6 0 0 1-2.3-2.3l.1-.1a1.6 1.6 0 0 0-1.1-2.7H5a1.6 1.6 0 0 1 0-3.2h.2a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a1.6 1.6 0 0 1 2.3-2.3l.1.1a1.6 1.6 0 0 0 2.7-1.1V3a1.6 1.6 0 0 1 3.2 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a1.6 1.6 0 0 1 2.3 2.3l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.2a1.6 1.6 0 0 1 0 3.2h-.2a1.6 1.6 0 0 0-1.1 2.7Z"/>',
  upload:'<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  play:'<path d="m9 6 9 6-9 6z" fill="currentColor" stroke="none"/>',
  arrow:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  back:'<path d="m15 18-6-6 6-6M9 12h11"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  spark:'<path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  download:'<path d="M12 4v11m0 0 4-4m-4 4-4-4"/><path d="M5 19h14"/>',
  edit:'<path d="m14 5 5 5M4 20l4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10Z"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  trash:'<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  search:'<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4 4"/>',
  video:'<rect x="3" y="5" width="13" height="14" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  chart:'<path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 5-6"/>',
  sound:'<path d="M4 10v4m4-8v12m4-15v18m4-14v10m4-7v4"/>',
  pexels:'<path d="M6 4h7a5 5 0 0 1 0 10h-2v6H6z"/><path d="M11 9h2"/>',
};
const icon = (name, cls="") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.film}</svg>`;

async function api(path, options={}) {
  const response = await fetch(path, {headers:{...(options.body && !(options.body instanceof FormData) ? {"Content-Type":"application/json"}:{}), ...(options.headers||{})}, ...options});
  const content = response.headers.get("content-type") || "";
  const data = content.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.detail || data?.message || `Request failed (${response.status})`);
  return data;
}
const postJson = (path, body, method="POST") => api(path,{method,body:JSON.stringify(body)});
const fmtTime = seconds => { const s=Math.max(0,Math.floor(Number(seconds)||0)); return `${Math.floor(s/60)}:${String(s%60).padStart(2,"0")}`; };
const fmtSize = bytes => { if(bytes<1024*1024)return `${Math.round(bytes/1024)} KB`; return `${(bytes/1024/1024/1024>=1?bytes/1024/1024/1024:bytes/1024/1024).toFixed(1)} ${bytes/1024/1024/1024>=1?"GB":"MB"}`; };
const metaLine = p => `${fmtTime(p.duration)} · ${p.width} × ${p.height} · ${fmtSize(p.file_size)}`;
const toast = (message,type="") => { const el=document.createElement("div");el.className=`toast ${type}`;el.textContent=message;$("#toast-stack").appendChild(el);setTimeout(()=>el.remove(),4200); };
const projectStatus = p => p.status === "complete" ? "Ready" : p.status === "importing" ? "Downloading" : p.status === "processing" ? "Analyzing" : p.status === "failed" ? "Needs attention" : "Imported";

async function refreshProjects() {
  const data=await api("/api/projects");state.projects=data.projects;state.stats=data.stats;
}
async function loadSettings() { state.settings=await api("/api/settings"); }
async function openProject(id) { state.project=await api(`/api/projects/${id}`);state.clip=null;state.page="project";render(); }
function scheduleProjectPoll(id) {
  if(projectPollTimer)clearTimeout(projectPollTimer);
  if(state.page!=="project"||state.project?.id!==id||!["processing","importing"].includes(state.project.status))return;
  projectPollTimer=setTimeout(()=>pollProject(id),1400);
}
async function pollProject(id) {
  if(state.project?.id!==id||state.page!=="project")return;
  try { const p=await api(`/api/projects/${id}`);state.project=p;await refreshProjects();render(); }
  catch(e){if(state.project?.id===id&&state.page==="project")projectPollTimer=setTimeout(()=>pollProject(id),3000);}
}

function shell() {
  const nav=[['dashboard','grid','Dashboard'],['projects','folder','My projects'],['exports','download','Exports'],['settings','settings','Settings']];
  const apiReady=state.settings.gemini_configured;
  const heading=state.page==="project"?state.project?.name:state.page==="editor"?"Clip editor":state.page==="settings"?"Settings":state.page==="exports"?"Exports":"Dashboard";
  return `<div class="shell"><aside class="sidebar"><div class="brand"><div class="brand-mark">${icon("mark")}</div><div class="brand-name">ClipForge <span>AI</span></div></div><div class="nav-label">Workspace</div><nav class="nav-list">${nav.map(([id,ico,label])=>`<button class="nav-item ${state.page===id||((state.page==="project"||state.page==="editor")&&id==="projects")?"active":""}" data-page="${id}">${icon(ico)}<span>${label}</span></button>`).join("")}</nav><div class="nav-spacer"></div><div class="local-card"><div class="local-card-top"><span>Local editing & export</span><i class="local-dot"></i></div><p>YouTube links use Gemini cloud transcription. Local file uploads use Whisper on this computer.</p></div><div class="sidebar-foot">ClipForge AI · v1.1.2 · Windows edition</div></aside><main class="main"><header class="topbar"><div class="crumbs">ClipForge <span>›</span> <strong>${esc(heading||"Dashboard")}</strong></div><div class="top-actions"><span class="api-pill ${apiReady?"ready":""}"><i></i>${apiReady?"Gemini connected":"Gemini key not set"}</span><div class="avatar">CF</div></div><input class="hide" type="file" id="file-input" accept="video/mp4,video/quicktime,video/x-matroska,video/x-msvideo,video/webm,.mp4,.mov,.mkv,.avi,.webm" multiple /></header><section class="content">${pageContent()}</section></main></div>`;
}

function dashboardPage() {
  const recent=state.projects.slice(0,6);
  const queue=state.projects.filter(p=>["processing","importing"].includes(p.status));
  return `<div class="welcome"><div><div class="eyebrow">Your short-form studio</div><h1>Turn long videos into moments.</h1><p>Paste a YouTube link or upload a video, then shape and export your clips.</p></div>${importActions()}</div>
    ${uploadPanel()}<div class="stat-grid"><div class="stat-card"><div class="stat-info"><span>Videos in your library</span><strong>${state.stats.videos||0}</strong></div><div class="stat-icon">${icon("film")}</div></div><div class="stat-card"><div class="stat-info"><span>Clips created</span><strong>${state.stats.clips||0}</strong></div><div class="stat-icon">${icon("layers")}</div></div><div class="stat-card"><div class="stat-info"><span>Exports finished</span><strong>${state.stats.exports||0}</strong></div><div class="stat-icon">${icon("download")}</div></div></div>
    ${queue.length?`<div class="section-head"><div><h2>Processing queue</h2><p class="sub">Source imports and clip analysis</p></div></div><div class="queue-list">${queue.map(p=>`<div class="queue-item" data-action="open-project" data-id="${p.id}"><div class="queue-thumb">${icon("sound")}</div><div class="queue-meta"><strong>${esc(p.name)}</strong><span>${esc(p.stage)}</span></div><div class="queue-progress"><i style="width:${p.progress}%"></i></div><span class="muted" style="font-size:9px">${p.progress}%</span></div>`).join("")}</div>`:""}<div class="section-head"><div><h2>Recent projects</h2><p class="sub">Pick up where you left off</p></div><button class="button small" data-page="projects">View library ${icon("arrow")}</button></div>
    ${recent.length?`<div class="project-grid">${recent.map(projectCard).join("")}</div>`:emptyState("film","Your project library is ready","Add a video to start finding clip-worthy moments.")}`;
}
function uploadPanel() { return `<div class="upload-panel"><div class="youtube-import"><div class="upload-copy"><div class="upload-icon">${icon("video")}</div><div><strong>Start with a YouTube link</strong><p>Gemini transcribes the public video; ClipForge downloads the source to edit it locally.</p></div></div><div class="youtube-form-row"><div class="field"><label for="youtube-url">YouTube video URL</label><input id="youtube-url" type="url" inputmode="url" placeholder="https://www.youtube.com/watch?v=…" autocomplete="url" /></div><button id="youtube-import-button" class="button primary" data-action="import-youtube">${icon("spark")} Import link</button></div><label class="rights-consent"><input id="rights-confirmed" type="checkbox" /><span>I own this video or have permission to download and edit it, and its use follows YouTube’s terms and applicable law.</span></label><p class="setting-help">Gemini needs a key from <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">Google AI Studio</a>. You can add it in Settings.</p></div><div class="upload-divider"><span>OR</span></div><div class="local-upload-panel" id="drop-zone"><div class="upload-inner"><div class="upload-copy"><div class="upload-icon">${icon("upload")}</div><div><strong>Upload a video from this computer</strong><p>MP4, MOV, MKV, AVI or WEBM · up to 4 GB</p></div></div><div class="upload-actions"><button class="button" data-action="browse-upload">Browse files</button><button class="button primary" data-action="browse-upload">${icon("upload")} Add videos</button></div></div><div class="upload-note">Local uploads use Whisper on this computer. Your source video stays in this project folder.</div></div></div>`; }
function importActions() { return `<div class="welcome-actions"><button class="button primary" data-action="focus-youtube-import">${icon("video")} Paste YouTube link</button><button class="button" data-action="browse-upload">${icon("upload")} Import video file</button></div>`; }
function projectCard(p) { return `<article class="project-card" data-action="open-project" data-id="${esc(p.id)}"><div class="project-thumb"><img class="project-thumb-img" src="${p.thumbnail_url}" alt="Video thumbnail" loading="lazy" onerror="this.style.display='none'"/>${icon("film")}<span class="status-tag ${esc(p.status)}"><i></i>${esc(projectStatus(p))}</span><span class="duration-tag">${fmtTime(p.duration)}</span></div><div class="project-body"><div class="project-name" title="${esc(p.name)}">${esc(p.name)}</div><div class="project-desc"><span>${p.width} × ${p.height}</span><span>${esc(p.clip_count||0)} clips</span></div><div class="project-bottom"><span>${metaLine(p)}</span><span>${icon("arrow")}</span></div></div></article>`; }
function emptyState(ico,title,desc) { return `<div class="empty-state"><div class="empty-mark">${icon(ico)}</div><strong>${esc(title)}</strong><p>${esc(desc)}</p></div>`; }
function projectsPage() { return `<div class="welcome"><div><div class="eyebrow">Library</div><h1>My projects</h1><p>Your videos, clip selections, and saved edits.</p></div>${importActions()}</div>${uploadPanel()}${state.projects.length?`<div class="section-head"><div><h2>My projects</h2><p class="sub">Your videos, clip selections, and saved edits.</p></div></div><div class="project-grid">${state.projects.map(projectCard).join("")}</div>`:emptyState("folder","No projects yet","Paste a YouTube link above or upload a video from your computer.")}`; }

function processControls(p) {
  const cfg=p.settings||{};
  const whisper=cfg.whisper_model||state.settings.whisper_model||"small";
  const auto=Object.hasOwn(cfg,"auto_broll")?cfg.auto_broll:state.settings.auto_broll;
  const isYouTube=Boolean(p.youtube_url), importing=p.status==="importing", processing=p.status==="processing";
  const speechControl=isYouTube?`<div class="cloud-transcription"><strong>Gemini cloud transcription</strong><span>Timestamped speech is matched to the downloaded source video. Timestamps are AI generated and may need a quick edit.</span>${state.settings.gemini_configured?"":"<b>Add a Gemini API key in Settings before analyzing this source.</b>"}</div>`:`<div class="field"><label for="project-whisper">Local speech model</label><select id="project-whisper"><option value="tiny" ${whisper==="tiny"?"selected":""}>Tiny · fastest</option><option value="base" ${whisper==="base"?"selected":""}>Base · quick</option><option value="small" ${whisper==="small"?"selected":""}>Small · balanced</option><option value="medium" ${whisper==="medium"?"selected":""}>Medium · higher accuracy</option><option value="large-v3" ${whisper==="large-v3"?"selected":""}>Large v3 · best accuracy</option></select><span class="setting-help">The model downloads once, then transcribes on your computer.</span></div>`;
  const disabled=importing||processing||!p.source_ready||(isYouTube&&!state.settings.gemini_configured);
  return `<div class="analysis-settings"><div class="field"><label for="duration-preset">Clip length</label><select id="duration-preset"><option value="15-30">15–30 seconds</option><option value="30-45">30–45 seconds</option><option value="45-60">45–60 seconds</option><option value="60-90">60–90 seconds</option><option value="custom">Custom range</option></select></div><div class="field-inline hide" id="custom-duration"><div class="field"><label>Minimum · seconds</label><input id="minimum" type="number" min="3" max="179" value="20" /></div><div class="field"><label>Maximum · seconds</label><input id="maximum" type="number" min="4" max="180" value="40" /></div></div><div class="field"><label for="clip-count">Clips to generate</label><select id="clip-count"><option value="3">3 clips</option><option value="5" selected>5 clips</option><option value="8">8 clips</option><option value="12">12 clips</option><option value="20">20 clips</option></select></div>${speechControl}<div class="switch-line"><span>Find Pexels B-roll cutaways where useful${state.settings.pexels_configured?"":" · add a key in Settings"}</span><label class="toggle"><input id="auto-broll" type="checkbox" ${auto?"checked":""} ${state.settings.pexels_configured?"":"disabled"}/><i></i></label></div><div class="panel-actions">${processing?`<button class="button" data-action="cancel-analysis">Cancel analysis</button>`:""}<button class="button primary" data-action="analyze" ${disabled?"disabled":""}>${importing?'<span class="spinner"></span> Downloading…':processing?'<span class="spinner"></span> Analyzing…':icon("spark")} ${p.status==="complete"?"Generate again":"Find my clips"}</button></div></div>`;
}
function clipCard(c) {
  const selected=state.clip?.id===c.id;
  return `<article class="clip-card ${selected?"selected":""}"><div class="clip-card-head" data-action="preview-clip" data-id="${c.id}"><button class="clip-play" aria-label="Preview clip">${icon("play")}</button><div class="clip-card-info"><strong>${esc(c.title||"Untitled clip")}</strong><div class="clip-meta"><span>${fmtTime(c.start)}–${fmtTime(c.end)}</span><span>·</span><span>${fmtTime(c.end-c.start)}</span><span class="score">${icon("chart")}${c.score}</span></div></div></div><div class="clip-card-body"><p class="clip-excerpt">${esc(c.transcript||"")}</p><div class="clip-card-foot"><div class="clip-tag-row"><span class="chip">Hook ${c.hook_score||0}</span>${c.broll?.length?`<span class="chip">${c.broll.length} B-roll</span>`:""}<span class="chip">${esc(c.aspect_ratio||"9:16")}</span></div><div class="clip-card-actions"><button class="button small" data-action="edit-clip" data-id="${c.id}">${icon("edit")} Edit</button><button class="button small primary" data-action="export-clip" data-id="${c.id}">${icon("download")} Export</button></div></div></div></article>`;
}
function projectPage() {
  const p=state.project;
  const clips=[...(p.clips||[])];
  const sort=state.sort;
  if(sort==="duration")clips.sort((a,b)=>(b.end-b.start)-(a.end-a.start)); else if(sort==="hook")clips.sort((a,b)=>(b.hook_score||0)-(a.hook_score||0)); else if(sort==="created")clips.sort((a,b)=>a.start-b.start); else clips.sort((a,b)=>b.score-a.score);
  const workspace=`<div class="workspace-head"><button class="back-button" data-page="projects">${icon("back")}</button><div class="workspace-title"><h1>${esc(p.name)}</h1><p>${esc(p.source_name)} · ${metaLine(p)}</p></div><div class="workspace-tools"><button class="button small" data-action="rename-project">${icon("edit")} Rename</button><button class="button small danger" data-action="delete-project">${icon("trash")} Delete</button></div></div>
  <div class="workspace-grid"><div><div class="panel"><div class="panel-head"><div><h3>Source video</h3><span>${p.source_ready?"Local preview":p.status==="importing"?"Downloading source":"Source unavailable"}</span></div><span>${esc(p.width)} × ${esc(p.height)}</span></div><div class="video-frame">${p.source_ready?`<video id="source-preview" src="${p.source_url}" controls preload="metadata"></video><span class="video-overlay">Original footage · final crop applied on export</span>`:`<div class="source-pending">${icon("film")}<strong>${p.status==="importing"?"Preparing your source video":"Import a video to preview it"}</strong><span>${p.status==="importing"?"The authorized source is downloading to this computer.":"Return to the dashboard to add a source video."}</span></div>`}</div>${state.clip?`<div class="video-controls"><div class="clip-range"><span>${fmtTime(state.clip.start)}</span><input type="range" min="${state.clip.start}" max="${state.clip.end}" value="${state.clip.start}" step=".1" id="preview-seek"/><span>${fmtTime(state.clip.end)}</span></div></div>`:""}</div>
  ${p.status==="importing"||p.status==="processing"||p.status==="failed"?`<div class="progress-panel"><div class="progress-row"><strong>${esc(p.stage)}</strong><span>${p.progress||0}%</span></div><div class="progress-bar"><i style="width:${p.progress||0}%"></i></div><p class="progress-note">${p.status==="failed"?esc(p.error||"Something interrupted processing. Retry to try again."):p.status==="importing"?"The video is being saved locally so ClipForge can preview and render your clips.":p.youtube_url?"Gemini is transcribing the YouTube video in the cloud. Clip timestamps come from its transcript.":"Speech recognition is running locally. Larger models may take longer on CPU."}</p></div>`:""}
  <div class="panel mt-10"><div class="panel-head"><h3>Find clip moments</h3><span>${p.youtube_url?"Gemini cloud transcript":state.settings.gemini_configured?"Gemini ranking + local transcription":"Local ranking + transcription"}</span></div>${processControls(p)}</div></div>
  <div><div class="section-head" style="margin:2px 0 12px"><div><h2>Generated clips</h2><p class="sub">${clips.length?`${clips.length} selected moments · ranked by editorial promise`:"Clips will appear here after analysis"}</p></div><div class="clips-toolbar"><select id="clip-sort"><option value="score" ${sort==="score"?"selected":""}>Top score</option><option value="hook" ${sort==="hook"?"selected":""}>Hook strength</option><option value="duration" ${sort==="duration"?"selected":""}>Duration</option><option value="created" ${sort==="created"?"selected":""}>Timeline order</option></select>${clips.length?`<button class="button small" data-action="export-all">Export all</button>`:""}</div></div>
    ${clips.length?`<div class="clips-list">${clips.map(clipCard).join("")}</div>`:emptyState("spark",p.status==="processing"?"Finding the strongest moments":p.status==="importing"?"Preparing your video":"Ready for analysis",p.status==="processing"?"We’re transcribing speech, finding sentence boundaries, and ranking complete excerpts.":p.status==="importing"?"The source video is downloading locally before analysis can start.":"Set a clip length and start the analysis to create editable short-form clips.")}</div></div>`;
  if(state.clip) return `${workspace}${editorInline()}`;
  return workspace;
}

function editorFields(c) {
  return `<div class="editor-copy"><div class="field-inline"><div class="field"><label>Start · seconds</label><input type="number" id="edit-start" min="0" step=".1" value="${Number(c.start).toFixed(1)}" /></div><div class="field"><label>End · seconds</label><input type="number" id="edit-end" min="0" step=".1" value="${Number(c.end).toFixed(1)}" /></div></div><div class="field"><label>Clip title</label><input id="edit-title" maxlength="140" value="${esc(c.title)}" /></div><div class="field"><label>Transcript · edited text is used in subtitles</label><textarea id="edit-transcript" rows="5">${esc(c.transcript)}</textarea></div><div class="field"><label>Social caption</label><textarea id="edit-caption" rows="3">${esc(c.caption)}</textarea></div><div class="field-inline"><div class="field"><label>Frame layout</label><select id="edit-layout"><option value="smart" ${c.layout==="smart"?"selected":""}>Smart subject crop</option><option value="blur" ${c.layout==="blur"?"selected":""}>Blurred background</option><option value="center" ${c.layout==="center"?"selected":""}>Center crop</option></select></div><div class="field"><label>Aspect ratio</label><select id="edit-ratio"><option value="9:16" ${c.aspect_ratio==="9:16"?"selected":""}>9:16 · vertical</option><option value="1:1" ${c.aspect_ratio==="1:1"?"selected":""}>1:1 · square</option><option value="16:9" ${c.aspect_ratio==="16:9"?"selected":""}>16:9 · landscape</option></select></div></div><div class="field-inline"><div class="field"><label>Subtitles</label><select id="edit-style"><option value="modern">Modern bold</option><option value="classic">Classic</option><option value="hormozi">Hormozi-style · word highlight</option><option value="minimal">Minimal</option><option value="gaming">Gaming</option><option value="cinematic">Cinematic</option><option value="karaoke">Karaoke · word timing</option></select></div><div class="field"><label>Resolution</label><select id="edit-size"><option value="1080" ${c.output_size==="1080"?"selected":""}>1080p</option><option value="720" ${c.output_size==="720"?"selected":""}>720p</option></select></div></div><div class="field-inline"><div class="field"><label>Playback speed · <span id="speed-label">${Number(c.speed||1).toFixed(2)}×</span></label><input id="edit-speed" type="range" min="0.5" max="2" step="0.05" value="${c.speed||1}" /></div><div class="field"><label>Audio volume · <span id="volume-label">${Math.round((c.volume||1)*100)}%</span></label><input id="edit-volume" type="range" min="0" max="2" step="0.05" value="${c.volume||1}" /></div></div><div class="switch-line"><span>Burn subtitles into export</span><label class="toggle"><input id="edit-subtitles" type="checkbox" ${c.subtitle_enabled?"checked":""}/><i></i></label></div><div class="panel-actions"><button class="button" data-action="close-editor">Close</button><button class="button primary" data-action="save-clip">${icon("check")} Save clip edits</button></div></div>`;
}
function editorInline() {
  const c=state.clip;const p=state.project;const duration=Math.max(.1,c.end-c.start);
  const brollTimeline=(c.broll||[]).map(item=>`<i class="timeline-broll" style="left:${Math.max(0,item.start_offset/duration*100)}%;width:${Math.min(100, item.duration/duration*100)}%"></i>`).join("");
  const clipLeft=Math.max(0,c.start/p.duration*100),clipWidth=Math.min(100,(c.end-c.start)/p.duration*100);
  return `<div class="section-head"><div><h2>Edit clip</h2><p class="sub">Adjust timing, framing, subtitles, and social copy</p></div></div><div class="editor-grid"><div class="panel editor-preview"><div class="panel-head"><h3>Clip preview</h3><span>source frame</span></div><div class="video-frame"><video id="editor-video" src="${p.source_url}" controls preload="metadata"></video></div><div class="timeline"><div class="timeline-head"><span>Source timeline</span><span>${fmtTime(c.start)} → ${fmtTime(c.end)}</span></div><div class="timeline-track"><i class="timeline-range" style="left:${clipLeft}%;width:${clipWidth}%"></i>${brollTimeline}</div></div></div><div class="panel"><div class="editor-tabs"><button class="editor-tab active" data-action="editor-tab" data-tab="edit">Edit</button><button class="editor-tab" data-action="editor-tab" data-tab="broll">B-roll${c.broll?.length?` (${c.broll.length})`:""}</button></div><div id="editor-edit-tab">${editorFields(c)}</div><div id="editor-broll-tab" class="editor-copy hide">${brollEditor(c)}</div></div></div>`;
}
function brollEditor(c) {
  const assets=c.broll||[];
  return `<div class="field"><label>Find a visual cutaway on Pexels</label><div class="broll-search"><input id="broll-query" value="${esc(c.broll_query||"")}" placeholder="e.g. city at night, hands building…"/><button class="button" data-action="search-broll">${icon("search")} Search</button></div><span class="setting-help">Search returns stock videos. ClipForge adds the cutaway over original speech and keeps the source audio.</span></div><div class="field-inline"><div class="field"><label>Insert at · seconds into clip</label><input id="broll-offset" type="number" min="0" step=".1" value="${Math.max(.2,(c.end-c.start)*.45).toFixed(1)}" /></div><div class="field"><label>Cutaway length · seconds</label><input id="broll-duration" type="number" min=".2" max="12" step=".1" value="4" /></div></div><div id="broll-results">${state.brollResults.length?renderBrollResults():""}</div>${assets.length?`<div class="field"><label>On this clip · adjust each cutaway’s timing</label><div class="broll-stack">${assets.map(a=>`<div class="broll-item"><video src="${a.media_url}" muted playsinline preload="metadata"></video><div class="broll-copy"><strong>${esc(a.query)}</strong><a href="${esc(a.pexels_url)}" target="_blank" rel="noreferrer">Video by ${esc(a.photographer)} on Pexels</a><div class="broll-timing"><input aria-label="B-roll start offset" id="broll-start-${a.id}" type="number" min="0" step=".1" value="${Number(a.start_offset).toFixed(1)}"/><input aria-label="B-roll duration" id="broll-length-${a.id}" type="number" min=".2" max="12" step=".1" value="${Number(a.duration).toFixed(1)}"/><button class="button small" data-action="save-broll" data-id="${a.id}">Save</button><button class="button small danger" data-action="remove-broll" data-id="${a.id}">${icon("trash")}</button></div></div></div>`).join("")}</div></div>`:""}<p class="broll-credit">Footage from <a href="https://www.pexels.com" target="_blank" rel="noreferrer">Pexels</a>. Source and contributor details stay with each cutaway.</p><div class="panel-actions"><button class="button" data-action="editor-tab" data-tab="edit">Back to edit</button></div>`;
}
function renderBrollResults() { return `<div class="broll-results">${state.brollResults.map(r=>`<div class="broll-result"><img src="${esc(r.thumbnail||"")}" alt="Pexels video preview"/><div class="broll-result-foot"><span>${esc(r.photographer)} · ${fmtTime(r.duration)}</span><button class="button small primary" data-action="add-broll" data-token="${r.selection_token}">Add cutaway</button></div></div>`).join("")}</div>`; }

function settingsPage() {
  const s=state.settings;
  return `<div class="welcome"><div><div class="eyebrow">Local preferences</div><h1>Settings</h1><p>Connect optional services and tune processing quality.</p></div></div><div class="settings-grid"><div class="panel settings-card"><h3>Gemini clip analysis</h3><p>Gemini transcribes public YouTube links and can rank transcript excerpts. Local file uploads use Whisper on this computer.</p><div class="settings-fields"><div class="field"><label>Gemini API key</label><div class="api-key-wrap"><input id="gemini-key" type="password" autocomplete="off" placeholder="${s.gemini_configured?"Saved on this computer · leave blank to keep":"Paste your API key"}" data-dirty="false"/><button class="button small ${s.gemini_configured?"danger":""}" data-action="clear-key" data-key="gemini-key">${s.gemini_configured?"Remove":""}</button></div><span class="setting-help">Key saved to this computer’s ClipForge data folder. Gemini API usage follows Google’s pricing and quota.</span></div><div class="field"><label>Gemini model</label><select id="gemini-model"><option value="gemini-3.8-flash" ${s.gemini_model==="gemini-3.8-flash"?"selected":""}>Gemini 3.8 Flash · recommended</option><option value="gemini-3.7-flash" ${s.gemini_model==="gemini-3.7-flash"?"selected":""}>Gemini 3.7 Flash</option><option value="gemini-3.6-flash" ${s.gemini_model==="gemini-3.6-flash"?"selected":""}>Gemini 3.6 Flash</option><option value="gemini-3.5-flash" ${s.gemini_model==="gemini-3.5-flash"?"selected":""}>Gemini 3.5 Flash</option><option value="custom">Custom model name</option></select><input class="hide" id="gemini-model-custom" placeholder="model name"/></div></div></div><div class="panel settings-card"><h3>Pexels B-roll</h3><p>Search the Pexels video library and add optional cutaways. Footage downloads into your project and stays on this computer.</p><div class="settings-fields"><div class="field"><label>Pexels API key</label><div class="api-key-wrap"><input id="pexels-key" type="password" autocomplete="off" placeholder="${s.pexels_configured?"Saved on this computer · leave blank to keep":"Paste your API key"}" data-dirty="false"/><button class="button small ${s.pexels_configured?"danger":""}" data-action="clear-key" data-key="pexels-key">${s.pexels_configured?"Remove":""}</button></div><span class="setting-help">Create a free key in your Pexels account. ClipForge links to Pexels and contributor pages.</span></div><div class="switch-line"><span>Suggest and add cutaways automatically when useful</span><label class="toggle"><input type="checkbox" id="settings-auto-broll" ${s.auto_broll?"checked":""}/><i></i></label></div></div></div><div class="panel settings-card"><h3>Local transcription</h3><p>Whisper runs on your CPU and downloads its model the first time it is selected.</p><div class="settings-fields"><div class="field"><label>Default speech model</label><select id="settings-whisper"><option value="tiny">Tiny · fastest, lowest accuracy</option><option value="base">Base · quick</option><option value="small">Small · balanced</option><option value="medium">Medium · higher accuracy</option><option value="large-v3">Large v3 · best accuracy, slowest</option></select></div><span class="setting-help">Models are stored in your local Hugging Face cache. Use Tiny or Base for a first run, Small for a balance of speed and accuracy.</span></div></div><div class="panel settings-card"><h3>Video processing</h3><p>FFmpeg handles crop, subtitles, audio, and MP4 encoding locally.</p><div class="settings-fields"><div class="field"><label>Default output size</label><select disabled><option>1080p · H.264 MP4</option></select></div><span class="setting-help">Available output sizes and aspect ratios are chosen per clip in the editor. Your source file is preserved alongside the project.</span></div></div></div><div class="panel-actions" style="margin-top:15px"><button class="button primary" data-action="save-settings">${icon("check")} Save settings</button></div>`;
}

async function exportsPage() {
  try { const data=await api("/api/exports");state.exports=data.exports; } catch(e){state.exports=[];}
  const rows=state.exports||[];
  return `<div class="welcome"><div><div class="eyebrow">Your renders</div><h1>Exports</h1><p>Finished MP4 files are saved in your local exports folder.</p></div></div>${rows.length?`<div class="clips-list">${rows.map(e=>`<div class="clip-card"><div class="clip-card-head"><div class="clip-play">${icon("video")}</div><div class="clip-card-info"><strong>${esc(e.title)}</strong><div class="clip-meta"><span>${esc(e.project_name)}</span><span>·</span><span>${new Date(e.finished_at).toLocaleString()}</span></div></div><a class="button small primary" href="${e.download_url}">${icon("download")} Download MP4</a></div></div>`).join("")}</div>`:emptyState("download","No exports yet","Open a project and export any clip to see it here.")}`;
}
function pageContent() {
  if(state.page==="dashboard")return dashboardPage();
  if(state.page==="projects")return projectsPage();
  if(state.page==="project")return state.project?projectPage():emptyState("film","Loading project","Please wait…");
  if(state.page==="editor")return state.project&&state.clip?`<div class="workspace-head"><button class="back-button" data-action="close-editor">${icon("back")}</button><div class="workspace-title"><h1>${esc(state.clip.title)}</h1><p>${esc(state.project.name)} · ${fmtTime(state.clip.end-state.clip.start)}</p></div><button class="button primary" data-action="export-clip" data-id="${state.clip.id}">${icon("download")} Export MP4</button></div>${editorInline()}`:"";
  if(state.page==="settings")return settingsPage();
  if(state.page==="exports")return exportsPageShell();
  return dashboardPage();
}
function exportsPageShell() { return state.exportsHtml || emptyState("download","Loading exports","Checking finished renders…"); }
function render() {
  document.querySelector("#app").innerHTML=shell();
  addTitleSuggestions();
  if(state.page==="exports"&&!state.exportsLoaded)loadExportsHtml();
  if(state.page==="settings")setTimeout(()=>{
    const whisper=$("#settings-whisper");if(whisper)whisper.value=state.settings.whisper_model||"small";
    const model=$("#gemini-model");const known=["gemini-3.8-flash","gemini-3.7-flash","gemini-3.6-flash","gemini-3.5-flash"];
    if(model){const current=state.settings.gemini_model||"gemini-3.8-flash";model.value=known.includes(current)?current:"custom";const custom=$("#gemini-model-custom");if(custom){custom.value=known.includes(current)?"":current;custom.classList.toggle("hide",known.includes(current));}}
  },0);
  if(state.page==="project"||state.page==="editor")setTimeout(()=>setupVideoPreview(),30);
  if(state.project?.id)scheduleProjectPoll(state.project.id);
}
function addTitleSuggestions() {
  const input=$("#edit-title");
  if(!input||!state.clip?.titles?.length)return;
  const options=state.clip.titles.map(title=>`<option value="${esc(title)}">${esc(title)}</option>`).join("");
  const field=document.createElement("div");field.className="field";
  field.innerHTML=`<label for="title-suggestions">Generated title ideas</label><select id="title-suggestions"><option value="">Choose a suggested title</option>${options}</select>`;
  input.parentElement.after(field);
  if(state.clip.reason){const reason=document.createElement("p");reason.className="setting-help";reason.textContent=`Why selected: ${state.clip.reason}`;field.after(reason);}
  if(state.clip.hook){const hook=document.createElement("div");hook.className="field";hook.innerHTML=`<label for="edit-hook">Suggested opening hook</label><input id="edit-hook" maxlength="300" value="${esc(state.clip.hook)}"/>`;field.after(hook);}
  const caption=$("#edit-caption");
  if(caption){const description=document.createElement("div");description.className="field";description.innerHTML=`<label for="edit-description">Short description</label><textarea id="edit-description" rows="2">${esc(state.clip.description||"")}</textarea>`;caption.parentElement.after(description);}
  if(state.clip.hashtags?.length){const tags=document.createElement("div");tags.className="clip-tag-row";tags.setAttribute("aria-label","Suggested hashtags");tags.innerHTML=state.clip.hashtags.map(tag=>`<span class="chip">${esc(tag)}</span>`).join("");caption?.parentElement.after(tags);}
}
async function loadExportsHtml(){ const holder=document.querySelector(".content"); if(!holder)return;state.exportsHtml=await exportsPage();state.exportsLoaded=true;if(state.page==="exports")render(); }

function setupVideoPreview() {
  const video=$("#source-preview")||$("#editor-video");
  if(video&&state.clip){video.currentTime=state.clip.start;video.addEventListener("timeupdate",()=>{if(video.currentTime>=state.clip.end)video.pause();},{once:false});}
  const seek=$("#preview-seek");if(seek)seek.addEventListener("input",()=>{const v=$("#source-preview");if(v)v.currentTime=Number(seek.value);});
  const style=$("#edit-style");if(style&&state.clip)style.value=state.clip.subtitle_style||"modern";
}

async function uploadFiles(files) {
  const chosen=[...files].filter(f=>f);if(!chosen.length)return;
  const form=new FormData();chosen.forEach(file=>form.append("files",file));
  state.busy=true;toast(`Adding ${chosen.length} video${chosen.length===1?"":"s"}…`);
  try { const data=await api("/api/upload",{method:"POST",body:form});await refreshProjects();if(data.projects.length===1)await openProject(data.projects[0].id);else{state.page="projects";render();}toast(`${data.projects.length} project${data.projects.length===1?"":"s"} added`,"success"); }
  catch(e){toast(e.message,"error");}
  finally{state.busy=false;const input=$("#file-input");if(input)input.value="";}
}

async function importYouTube() {
  const url=$("#youtube-url")?.value.trim();
  const rights_confirmed=Boolean($("#rights-confirmed")?.checked);
  if(!url){toast("Paste a YouTube video link first","error");return;}
  if(!rights_confirmed){toast("Confirm you have permission to download and edit this video","error");return;}
  const button=$("#youtube-import-button");if(button)button.disabled=true;
  try {const data=await postJson("/api/import-youtube",{url,rights_confirmed});await refreshProjects();await openProject(data.project.id);toast("YouTube source import started · saving locally","success");}
  catch(e){toast(e.message,"error");}
  finally{if(button)button.disabled=false;}
}

function focusYouTubeImport() {
  let input=$("#youtube-url");
  if(!input){state.page="dashboard";state.clip=null;render();input=$("#youtube-url");}
  input?.scrollIntoView({behavior:"smooth",block:"center"});
  input?.focus({preventScroll:true});
}

async function analyze() {
  const preset=$("#duration-preset")?.value||"15-30";let [minimum,maximum]=preset==="custom"?[Number($("#minimum")?.value),Number($("#maximum")?.value)]:preset.split("-").map(Number);
  const count=Number($("#clip-count")?.value||5);const whisper_model=$("#project-whisper")?.value||state.settings.whisper_model||"small";
  const auto_broll=Boolean($("#auto-broll")?.checked);
  try { await postJson(`/api/projects/${state.project.id}/process`,{minimum,maximum,count,whisper_model,auto_broll});state.project=await api(`/api/projects/${state.project.id}`);render();toast(state.project.youtube_url?"Analysis started · Gemini cloud transcription":"Analysis started · speech stays local","success");pollProject(state.project.id); }
  catch(e){toast(e.message,"error");}
}
async function saveClip() {
  const c=state.clip;
  const body={start:Number($("#edit-start").value),end:Number($("#edit-end").value),title:$("#edit-title").value,
    transcript:$("#edit-transcript").value,caption:$("#edit-caption").value,description:$("#edit-description")?.value||"",hook:$("#edit-hook")?.value||"",layout:$("#edit-layout").value,
    aspect_ratio:$("#edit-ratio").value,subtitle_style:$("#edit-style").value,output_size:$("#edit-size").value,
    speed:Number($("#edit-speed").value),volume:Number($("#edit-volume").value),subtitle_enabled:$("#edit-subtitles").checked};
  try { await postJson(`/api/clips/${c.id}`,body,"PATCH");await reloadCurrentProject(c.id);toast("Clip edits saved","success"); }
  catch(e){toast(e.message,"error");}
}
async function reloadCurrentProject(clipId=state.clip?.id) { state.project=await api(`/api/projects/${state.project.id}`);state.clip=state.project.clips.find(c=>c.id===clipId)||null;render(); }

async function trackExport(jobId,clipId) {
  for(let i=0;i<360;i++) {
    await new Promise(r=>setTimeout(r,1400));
    try { const job=await api(`/api/jobs/${jobId}`);if(job.status==="complete"){toast("MP4 export finished","success");await refreshProjects();if(state.project?.id)await reloadCurrentProject(clipId);const a=document.createElement("a");a.href=job.download_url;a.download="";a.click();return;}if(job.status==="failed"){toast(job.error||"Export failed","error");return;} }
    catch(e){toast(e.message,"error");return;}
  }
  toast("Export is still running. You can find it in Exports when it finishes.");
}
async function exportClip(id) { try {const job=await api(`/api/clips/${id}/export`,{method:"POST"});toast("Export queued · rendering locally","success");trackExport(job.job_id,id);}catch(e){toast(e.message,"error");} }
async function exportAll() { try {const data=await api(`/api/projects/${state.project.id}/export-all`,{method:"POST"});toast(`${data.jobs.length} exports queued`);data.jobs.forEach(j=>trackExport(j.job_id,null));}catch(e){toast(e.message,"error");} }

async function saveSettings() {
  const payload={gemini_model:$("#gemini-model").value==="custom"?$("#gemini-model-custom").value:$("#gemini-model").value,
    whisper_model:$("#settings-whisper").value,auto_broll:$("#settings-auto-broll").checked};
  for(const [key,id] of [["gemini_api_key","gemini-key"],["pexels_api_key","pexels-key"]]) {const input=$("#"+id);if(input.dataset.dirty==="true"||input.dataset.clear==="true")payload[key]=input.value;}
  if(!payload.gemini_model){toast("Enter a Gemini model name","error");return;}
  try {state.settings=await postJson("/api/settings",payload,"PUT");toast("Settings saved on this computer","success");render();}
  catch(e){toast(e.message,"error");}
}
async function searchBroll() {
  const query=$("#broll-query").value.trim();if(!query){toast("Enter a visual search phrase","error");return;}
  try {const data=await api(`/api/clips/${state.clip.id}/broll/search?query=${encodeURIComponent(query)}&orientation=${state.clip.aspect_ratio==="9:16"?"portrait":"landscape"}`);state.brollResults=data.results;const target=$("#broll-results");if(target)target.innerHTML=renderBrollResults();if(!data.results.length)toast("No matching videos found. Try a broader phrase.");}
  catch(e){toast(e.message,"error");}
}
async function addBroll(token) {
  try {await postJson(`/api/clips/${state.clip.id}/broll/add`,{selection_token:token,start_offset:Number($("#broll-offset").value),duration:Number($("#broll-duration").value)});state.brollResults=[];await reloadCurrentProject(state.clip.id);document.querySelector('[data-action="editor-tab"][data-tab="broll"]')?.click();toast("Pexels cutaway added","success");}
  catch(e){toast(e.message,"error");}
}
document.addEventListener("click",async event=>{
  const el=event.target.closest("[data-action],[data-page]");if(!el)return;
  if(el.hasAttribute("data-page")){state.page=el.dataset.page;state.clip=null;if(state.page==="exports")state.exportsLoaded=false;render();return;}
  const action=el.dataset.action;
  if(action==="browse-upload")$("#file-input")?.click();
  if(action==="focus-youtube-import")focusYouTubeImport();
  if(action==="import-youtube")importYouTube();
  if(action==="open-project")openProject(el.dataset.id);
  if(action==="analyze")analyze();
  if(action==="cancel-analysis")try{await api(`/api/projects/${state.project.id}/cancel`,{method:"POST"});toast("Cancellation requested");}catch(e){toast(e.message,"error");}
  if(action==="preview-clip"){const c=state.project.clips.find(x=>x.id===el.dataset.id);state.clip=c;render();const v=$("#source-preview");if(v){v.currentTime=c.start;v.play().catch(()=>{});}}
  if(action==="edit-clip"){state.clip=state.project.clips.find(x=>x.id===el.dataset.id);state.page="editor";render();}
  if(action==="close-editor"){state.page="project";state.brollResults=[];render();}
  if(action==="save-clip")saveClip();
  if(action==="export-clip")exportClip(el.dataset.id);
  if(action==="export-all")exportAll();
  if(action==="rename-project"){const name=prompt("Project name",state.project.name);if(name?.trim())try{await postJson(`/api/projects/${state.project.id}`,{name:name.trim()},"PATCH");await openProject(state.project.id);toast("Project renamed","success");}catch(e){toast(e.message,"error");}}
  if(action==="delete-project"){if(confirm(`Delete “${state.project.name}” and its local source and exports?`))try{await api(`/api/projects/${state.project.id}`,{method:"DELETE"});state.project=null;await refreshProjects();state.page="projects";render();toast("Project deleted","success");}catch(e){toast(e.message,"error");}}
  if(action==="editor-tab"){const tab=el.dataset.tab;$("#editor-edit-tab")?.classList.toggle("hide",tab!=="edit");$("#editor-broll-tab")?.classList.toggle("hide",tab!=="broll");document.querySelectorAll(".editor-tab").forEach(x=>x.classList.toggle("active",x.dataset.tab===tab));}
  if(action==="search-broll")searchBroll();
  if(action==="add-broll")addBroll(el.dataset.token);
  if(action==="save-broll")try{await postJson(`/api/broll/${el.dataset.id}`,{start_offset:Number($(`#broll-start-${el.dataset.id}`).value),duration:Number($(`#broll-length-${el.dataset.id}`).value)},"PATCH");await reloadCurrentProject(state.clip.id);document.querySelector('[data-action="editor-tab"][data-tab="broll"]')?.click();toast("B-roll placement saved","success");}catch(e){toast(e.message,"error");}
  if(action==="remove-broll")try{await api(`/api/broll/${el.dataset.id}`,{method:"DELETE"});await reloadCurrentProject(state.clip.id);toast("Cutaway removed");}catch(e){toast(e.message,"error");}
  if(action==="save-settings")saveSettings();
  if(action==="clear-key"){const input=$("#"+el.dataset.key);input.value="";input.dataset.dirty="true";input.dataset.clear="true";el.textContent="Will remove";}
});

document.addEventListener("change",event=>{
  const el=event.target;
  if(el.matches("#file-input"))uploadFiles(el.files);
  if(el.matches("#clip-sort")){state.sort=el.value;render();}
  if(el.matches("#duration-preset"))$("#custom-duration")?.classList.toggle("hide",el.value!=="custom");
  if(el.matches("#gemini-key,#pexels-key"))el.dataset.dirty="true";
  if(el.matches("#gemini-model"))$("#gemini-model-custom")?.classList.toggle("hide",el.value!=="custom");
  if(el.matches("#title-suggestions")&&el.value){$("#edit-title").value=el.value;}
});
document.addEventListener("input",event=>{
  const el=event.target;
  if(el.matches("#edit-speed"))$("#speed-label").textContent=`${Number(el.value).toFixed(2)}×`;
  if(el.matches("#edit-volume"))$("#volume-label").textContent=`${Math.round(Number(el.value)*100)}%`;
});
document.addEventListener("dragover",event=>{if(event.target.closest("#drop-zone")){event.preventDefault();$("#drop-zone")?.classList.add("dragging");}});
document.addEventListener("dragleave",event=>{if(event.target.closest("#drop-zone"))$("#drop-zone")?.classList.remove("dragging");});
document.addEventListener("drop",event=>{const zone=event.target.closest("#drop-zone");if(zone){event.preventDefault();zone.classList.remove("dragging");uploadFiles(event.dataTransfer.files);}});

async function boot(){try{await Promise.all([refreshProjects(),loadSettings()]);render();}catch(e){document.querySelector("#app").innerHTML=`<div class="content"><div class="empty-state"><strong>ClipForge could not start</strong><p>${esc(e.message)}<br/>Please close and reopen the local app.</p></div></div>`;}}
boot();
