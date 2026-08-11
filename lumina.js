// ============================================================
// LUMINA — CORE
// ============================================================
const API = `/chat`;
const JAMENDO = "127d581d";

const MODELS = [
  {id:"lumina-flash",    label:"Lumina Flash",   desc:"Ultra rapide · Groq",       model:"llama-3.1-8b-instant"},
  {id:"lumina-prime",   label:"Lumina Prime",    desc:"Puissant · Llama 70B",       model:"llama-3.3-70b-versatile"},
  {id:"lumina-create",  label:"Lumina Create",   desc:"Créatif · Mixtral",          model:"mixtral-8x7b-32768"},
  {id:"lumina-precise", label:"Lumina Precise",  desc:"Précis · Gemma",             model:"gemma2-9b-it"},
];

let lastReply = "";

const CMD_ITEMS = [
  {cat:"Actions",icon:"🎨",label:"Générer une image",desc:"Créer une image avec l'IA",action:()=>quickSend("Génère un paysage futuriste au coucher du soleil")},
  {cat:"Actions",icon:"📈",label:"Tracer un graphique",desc:"Graphique interactif y = f(x)",action:()=>{setInput("y = A*sin(k*x)");closePlus();}},
  {cat:"Actions",icon:"💻",label:"Écrire du code",desc:"Générer un script",action:()=>quickSend("Écris un script Python de tri rapide")},
  {cat:"Actions",icon:"🎵",label:"Jouer de la musique",desc:"Rechercher et jouer",action:()=>quickSend("Joue une musique jazz relaxante")},
  {cat:"Actions",icon:"📝",label:"Résumer la conversation",desc:"Résumé de l'historique",action:()=>quickSend("Résume notre conversation")},
  {cat:"Navigation",icon:"⚙️",label:"Ouvrir les paramètres",desc:"Thème, modèle, voix...",action:()=>openSettings()},
  {cat:"Navigation",icon:"➕",label:"Nouvelle discussion",desc:"Commencer une nouvelle conversation",action:()=>newConversation()},
  {cat:"Navigation",icon:"🔍",label:"Rechercher",desc:"Rechercher dans la conversation",action:()=>openSearch()},
  {cat:"IA",icon:"🧠",label:"Changer de modèle",desc:"Sélectionner un autre modèle",action:()=>openSettings()},
  {cat:"IA",icon:"🌐",label:"Activer la recherche web",desc:"Naviguer sur internet",action:()=>{toggleSetting('webSearch');toast("🌐 Recherche web "+(settings.webSearch?"activée":"désactivée"));}},
  {cat:"Exporter",icon:"📋",label:"Copier la dernière réponse",desc:"Copier dans le presse-papier",action:()=>{if(lastReply)navigator.clipboard?.writeText(lastReply).then(()=>toast("✅ Copié !"));}},
];

let state = {
  currentModel: "lumina-flash",
  conversations: JSON.parse(localStorage.getItem("lv4_convs")||"null") || {current:null,list:[]},
  messageHistory: JSON.parse(localStorage.getItem("lv4_msgs")||"{}"),
  pinnedConvs: JSON.parse(localStorage.getItem("lv4_pins")||"[]"),
  userName: localStorage.getItem("lv4_user")||"",
};

let settings = {
  theme: localStorage.getItem("lv4_theme")||"dark",
  autoTTS: localStorage.getItem("lv4_autoTTS")==="true",
  webSearch: localStorage.getItem("lv4_web")==="true",
  vision: true,
  memory: false,
  fontSize: parseInt(localStorage.getItem("lv4_fs")||"100"),
  accent: localStorage.getItem("lv4_accent")||"#8a5cf6,#c084fc",
};

let runtime = {
  isStreaming: false,
  stopRequested: false,
  currentSpeech: null,
  currentAudio: null,
  lastReply: "",
  lastAiGroup: null,
  renameTargetId: null,
  ctxMenu: null,
  cmdFocused: 0,
  pendingOffline: null,
  ttsQueue: [],
  ttsSpeaking: false,
};

function save(){
  localStorage.setItem("lv4_convs", JSON.stringify(state.conversations));
  localStorage.setItem("lv4_msgs",  JSON.stringify(state.messageHistory));
  localStorage.setItem("lv4_pins",  JSON.stringify(state.pinnedConvs));
}
function saveSetting(k,v){localStorage.setItem("lv4_"+k,v);}

function toast(msg, dur=2800){
  document.querySelectorAll(".toast").forEach(t=>t.remove());
  const t=document.createElement("div");t.className="toast";t.textContent=msg;
  document.body.appendChild(t);setTimeout(()=>t.remove(),dur+300);
}

function applySettings(){
  document.body.classList.remove("theme-amoled","theme-light");
  if(settings.theme==="amoled")document.body.classList.add("theme-amoled");
  if(settings.theme==="light")document.body.classList.add("theme-light");
  document.body.style.fontSize = settings.fontSize/100+"rem";
  const fsVal=document.getElementById("fsVal");if(fsVal)fsVal.textContent=settings.fontSize+"%";
  const [a1,a2]=settings.accent.split(",");
  document.documentElement.style.setProperty("--acc",a1);
  document.documentElement.style.setProperty("--acc2",a2);
  const tglAutoTTS=document.getElementById("tglAutoTTS");
  if(tglAutoTTS)tglAutoTTS.className="tgl"+(settings.autoTTS?" on":"");
  const tglWeb=document.getElementById("tglWeb");
  if(tglWeb)tglWeb.className="tgl"+(settings.webSearch?" on":"");
  const pmTTSTgl=document.getElementById("pmTTSTgl");
  if(pmTTSTgl)pmTTSTgl.className="toggle"+(settings.autoTTS?" on":"");
  const pmWebTgl=document.getElementById("pmWebTgl");
  if(pmWebTgl)pmWebTgl.className="toggle"+(settings.webSearch?" on":"");
  const themeVal=document.getElementById("themeVal");
  if(themeVal)themeVal.textContent={"dark":"Sombre","amoled":"AMOLED","light":"Clair"}[settings.theme]||"Sombre";
  document.querySelectorAll(".accent-dot").forEach(d=>{
    d.classList.toggle("active",d.dataset.color===settings.accent);
  });
}

// ============================================================
// STOP — arrête TOUT immédiatement
// ============================================================
function stopAll(){
  runtime.stopRequested = true;
  if(window.speechSynthesis){window.speechSynthesis.cancel();}
  runtime.currentSpeech = null;
  runtime.ttsSpeaking = false;
  runtime.ttsQueue = [];
  document.getElementById("ttsBtn").classList.remove("tts-on");
  if(runtime.currentAudio){runtime.currentAudio.pause();runtime.currentAudio.src="";runtime.currentAudio=null;}
  document.getElementById("audioBar")?.remove();
  runtime.isStreaming = false;
  const sendBtn=document.getElementById("sendBtn");
  sendBtn.classList.remove("stop-active");
  sendBtn.innerHTML=`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
  toast("⏹ Tout arrêté");
}

document.getElementById("sendBtn").onclick=()=>{
  if(runtime.isStreaming){stopAll();}
  else{sendMessage();}
};

// ENTER = nouvelle ligne (jamais d'envoi automatique)
document.getElementById("userInput").addEventListener("input",autoResize);

function setInput(v){const f=document.getElementById("userInput");f.value=v;autoResize();}
function autoResize(){const f=document.getElementById("userInput");f.style.height="auto";f.style.height=Math.min(f.scrollHeight,130)+"px";}

// ============================================================
// CONVERSATIONS
// ============================================================
function newConversation(){
  const id=Date.now().toString();
  state.conversations.list.unshift({id,title:"Nouvelle discussion",date:new Date().toLocaleDateString("fr-FR")});
  state.conversations.current=id;state.messageHistory[id]=[];
  save();renderConvList();renderMessages();closeBar();closePlus();
}
document.getElementById("newConvBtn").onclick=newConversation;

function loadConv(id){state.conversations.current=id;save();renderConvList();renderMessages();closeBar();}

function deleteConv(id){
  state.conversations.list=state.conversations.list.filter(c=>c.id!==id);
  delete state.messageHistory[id];state.pinnedConvs=state.pinnedConvs.filter(p=>p!==id);
  if(!state.conversations.list.length)newConversation();
  else if(state.conversations.current===id)state.conversations.current=state.conversations.list[0].id;
  save();renderConvList();renderMessages();
}

function renameConv(id,title){
  const c=state.conversations.list.find(c=>c.id===id);if(c){c.title=title;save();renderConvList();
  if(state.conversations.current===id)document.getElementById("convNameDisplay").textContent=title;}
}

function pinConv(id){
  state.pinnedConvs.includes(id)?state.pinnedConvs=state.pinnedConvs.filter(p=>p!==id):state.pinnedConvs.unshift(id);
  save();renderConvList();
}

function duplicateConv(id){
  const src=state.conversations.list.find(c=>c.id===id);if(!src)return;
  const nid=Date.now().toString();
  state.conversations.list.unshift({id:nid,title:"Copie — "+src.title,date:new Date().toLocaleDateString("fr-FR")});
  state.messageHistory[nid]=JSON.parse(JSON.stringify(state.messageHistory[id]||[]));
  save();renderConvList();toast("📋 Conversation dupliquée");
}

function exportConv(id){
  const msgs=state.messageHistory[id]||[];
  const conv=state.conversations.list.find(c=>c.id===id);
  let md=`# ${conv?.title||"Conversation"}\n_Exporté le ${new Date().toLocaleString("fr-FR")}_\n\n`;
  msgs.forEach(m=>{md+=`**${m.role==="user"?"Vous":"Lumina"}**\n${m.content||""}\n\n---\n\n`;});
  const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([md],{type:"text/markdown"}));
  a.download=(conv?.title||"conversation")+".md";a.click();toast("📥 Exporté en Markdown");
}

function renderConvList(){
  const cl=document.getElementById("convList");cl.innerHTML="";
  const q=(document.getElementById("sbSearch")?.value||"").toLowerCase();
  let list=[...state.conversations.list];
  if(q)list=list.filter(c=>c.title.toLowerCase().includes(q)||(state.messageHistory[c.id]||[]).some(m=>(m.content||"").toLowerCase().includes(q)));
  list.sort((a,b)=>state.pinnedConvs.includes(b.id)-state.pinnedConvs.includes(a.id));
  for(const c of list){
    const isPinned=state.pinnedConvs.includes(c.id),isActive=c.id===state.conversations.current;
    const msgs=state.messageHistory[c.id]||[];
    const preview=msgs.length?(msgs[msgs.length-1].content||"").slice(0,40)+"…":"";
    const div=document.createElement("div");div.className="conv-item"+(isActive?" active":"");
    div.innerHTML=`<div class="conv-ico">${isPinned?"📌":"💬"}</div><div class="conv-info"><div class="conv-title">${c.title}</div><div class="conv-preview">${preview}</div></div><div class="conv-date">${c.date||""}</div><button class="conv-more-btn">···</button>`;
    div.querySelector(".conv-info").onclick=()=>loadConv(c.id);
    div.querySelector(".conv-ico").onclick=()=>loadConv(c.id);
    div.querySelector(".conv-more-btn").onclick=e=>{e.stopPropagation();showCtx(c.id,e);};
    cl.appendChild(div);
  }
}
document.getElementById("sbSearch").oninput=renderConvList;

// ============================================================
// CONTEXT MENU
// ============================================================
function showCtx(id,e){
  closeCtx();const isPinned=state.pinnedConvs.includes(id);
  const m=document.createElement("div");m.className="ctx";
  const items=[
    {ico:"✏️",lbl:"Renommer",bg:"rgba(138,92,246,.12)",action:()=>{closeCtx();openRename(id);}},
    {ico:"📌",lbl:isPinned?"Désépingler":"Épingler",bg:"rgba(251,191,36,.12)",action:()=>{pinConv(id);toast(state.pinnedConvs.includes(id)?"📌 Épinglé":"Désépinglé");closeCtx();}},
    {ico:"📋",lbl:"Dupliquer",bg:"rgba(56,189,248,.12)",action:()=>{duplicateConv(id);closeCtx();}},
    {ico:"📥",lbl:"Exporter",bg:"rgba(52,211,153,.12)",action:()=>{exportConv(id);closeCtx();}},
    {div:true},
    {ico:"🗑️",lbl:"Supprimer",bg:"rgba(248,113,113,.12)",danger:true,action:()=>{deleteConv(id);toast("🗑️ Supprimé");closeCtx();}},
  ];
  items.forEach(item=>{
    if(item.div){const d=document.createElement("div");d.className="ctx-div";m.appendChild(d);return;}
    const b=document.createElement("button");b.className="ctx-item"+(item.danger?" danger":"");
    b.innerHTML=`<div class="ctx-ico" style="background:${item.bg}">${item.ico}</div>${item.lbl}`;
    b.onclick=item.action;m.appendChild(b);
  });
  document.body.appendChild(m);
  const x=Math.min(e.clientX,window.innerWidth-200),y=Math.min(e.clientY,window.innerHeight-210);
  m.style.left=x+"px";m.style.top=y+"px";
  runtime.ctxMenu=m;setTimeout(()=>document.addEventListener("click",closeCtx,{once:true}),50);
}
function closeCtx(){if(runtime.ctxMenu){runtime.ctxMenu.remove();runtime.ctxMenu=null;}}

function openRename(id){
  runtime.renameTargetId=id;
  const c=state.conversations.list.find(c=>c.id===id);
  document.getElementById("renameInput").value=c?.title||"";
  document.getElementById("renameModal").classList.add("show");
  setTimeout(()=>document.getElementById("renameInput").focus(),200);
}
document.getElementById("cancelRename").onclick=()=>document.getElementById("renameModal").classList.remove("show");
document.getElementById("confirmRename").onclick=()=>{
  const v=document.getElementById("renameInput").value.trim();
  if(runtime.renameTargetId&&v)renameConv(runtime.renameTargetId,v);
  document.getElementById("renameModal").classList.remove("show");
};
document.getElementById("renameInput").onkeydown=e=>{if(e.key==="Enter")document.getElementById("confirmRename").click();};

// ============================================================
// SIDEBAR / OVERLAY
// ============================================================
document.getElementById("menuBtn").onclick=()=>{document.getElementById("sidebar").classList.add("open");document.getElementById("overlay").classList.add("show");};
document.getElementById("closeSidebar").onclick=closeBar;
document.getElementById("overlay").onclick=()=>{closeBar();closePlus();closeCmd();};
function closeBar(){document.getElementById("sidebar").classList.remove("open");document.getElementById("overlay").classList.remove("show");}
// ============================================================
// SETTINGS
// ============================================================
function openSettings(){
  const g=document.getElementById("modelGrid");g.innerHTML="";
  MODELS.forEach(m=>{
    const c=document.createElement("div");c.className="model-card"+(state.currentModel===m.id?" active":"");
    c.innerHTML=`<div class="mc-name">${m.label}</div><div class="mc-desc">${m.desc}</div>`;
    c.onclick=()=>{state.currentModel=m.id;g.querySelectorAll(".model-card").forEach(x=>x.classList.remove("active"));c.classList.add("active");document.getElementById("modelPillLabel").textContent=m.label.replace("Lumina ","");toast(`Modèle : ${m.label}`);};
    g.appendChild(c);
  });
  document.getElementById("sName").textContent=state.userName||"Utilisateur";
  applySettings();
  document.getElementById("settingsModal").classList.add("show");
}
document.getElementById("closeSettings").onclick=()=>document.getElementById("settingsModal").classList.remove("show");
document.getElementById("settingsBg").onclick=()=>document.getElementById("settingsModal").classList.remove("show");
document.getElementById("navSettings").onclick=()=>{closeBar();openSettings();};
document.getElementById("modelPill").onclick=()=>openSettings();

function makeTgl(id,key){
  document.getElementById(id).onclick=()=>{settings[key]=!settings[key];saveSetting(key,settings[key]);applySettings();};
}
makeTgl("tglAutoTTS","autoTTS");makeTgl("tglWeb","webSearch");
makeTgl("tglVision","vision");makeTgl("tglMemory","memory");
document.getElementById("pmToggleWeb").onclick=()=>{settings.webSearch=!settings.webSearch;saveSetting("webSearch",settings.webSearch);applySettings();toast(settings.webSearch?"🌐 Web ON":"Web OFF");};
document.getElementById("pmToggleTTS").onclick=()=>{settings.autoTTS=!settings.autoTTS;saveSetting("autoTTS",settings.autoTTS);applySettings();toast(settings.autoTTS?"🔊 Lecture auto ON":"Lecture auto OFF");};

function toggleSetting(k){settings[k]=!settings[k];saveSetting(k,settings[k]);applySettings();}

document.getElementById("themeItem").onclick=()=>{
  const t=["dark","amoled","light"];const i=t.indexOf(settings.theme);
  settings.theme=t[(i+1)%t.length];saveSetting("theme",settings.theme);applySettings();toast("Thème : "+document.getElementById("themeVal").textContent);
};

document.querySelectorAll(".accent-dot").forEach(d=>{
  d.onclick=()=>{settings.accent=d.dataset.color;saveSetting("accent",settings.accent);applySettings();};
});

document.getElementById("fsMinus").onclick=()=>{if(settings.fontSize>70){settings.fontSize-=10;saveSetting("fs",settings.fontSize);applySettings();}};
document.getElementById("fsPlus").onclick=()=>{if(settings.fontSize<150){settings.fontSize+=10;saveSetting("fs",settings.fontSize);applySettings();}};

document.getElementById("editProfile").onclick=()=>{
  document.getElementById("settingsModal").classList.remove("show");
  const n=prompt("Votre prénom :",state.userName)||state.userName;
  state.userName=(n||"").trim()||state.userName;localStorage.setItem("lv4_user",state.userName);
  updateWelcomeName();toast("✅ Profil mis à jour");
};

document.getElementById("clearAllBtn").onclick=()=>{
  if(!confirm("Effacer toutes les conversations ?"))return;
  state.conversations={current:null,list:[]};state.messageHistory={};state.pinnedConvs=[];
  save();newConversation();document.getElementById("settingsModal").classList.remove("show");toast("🗑️ Conversations effacées");
};

function updateWelcomeName(){
  const t=document.getElementById("welcomeTitle");if(t&&state.userName&&state.userName!=="vous")t.innerHTML=`Bonjour ${state.userName},<br>je suis Lumina`;
  const sb=document.getElementById("sbUserName");if(sb)sb.textContent=state.userName||"Utilisateur";
  const sn=document.getElementById("sName");if(sn)sn.textContent=state.userName||"Utilisateur";
}

// ============================================================
// COMMAND PALETTE
// ============================================================
let filteredCmds=[];
function openCmd(){document.getElementById("cmdOverlay").classList.add("show");document.getElementById("cmdInput").value="";filterCmds("");setTimeout(()=>document.getElementById("cmdInput").focus(),100);}
function closeCmd(){document.getElementById("cmdOverlay").classList.remove("show");}
document.getElementById("cmdBtn").onclick=openCmd;
document.getElementById("cmdOverlay").onclick=e=>{if(e.target===document.getElementById("cmdOverlay"))closeCmd();};
document.getElementById("cmdInput").oninput=e=>filterCmds(e.target.value);
document.getElementById("cmdInput").onkeydown=e=>{
  if(e.key==="Escape")closeCmd();
  if(e.key==="ArrowDown"){runtime.cmdFocused=Math.min(runtime.cmdFocused+1,filteredCmds.length-1);renderCmdResults();}
  if(e.key==="ArrowUp"){runtime.cmdFocused=Math.max(runtime.cmdFocused-1,0);renderCmdResults();}
  if(e.key==="Enter"){if(filteredCmds[runtime.cmdFocused]){closeCmd();filteredCmds[runtime.cmdFocused].action();}}
};
function filterCmds(q){
  filteredCmds=q?CMD_ITEMS.filter(c=>c.label.toLowerCase().includes(q.toLowerCase())||c.desc.toLowerCase().includes(q.toLowerCase())):CMD_ITEMS;
  runtime.cmdFocused=0;renderCmdResults();
}
function renderCmdResults(){
  const r=document.getElementById("cmdResults");r.innerHTML="";
  const cats=[...new Set(filteredCmds.map(c=>c.cat))];
  cats.forEach(cat=>{
    const items=filteredCmds.filter(c=>c.cat===cat);
    const cDiv=document.createElement("div");cDiv.className="cmd-cat";cDiv.textContent=cat;r.appendChild(cDiv);
    items.forEach(item=>{
      const gIdx=filteredCmds.indexOf(item);
      const d=document.createElement("div");d.className="cmd-item"+(gIdx===runtime.cmdFocused?" focused":"");
      d.innerHTML=`<div class="cmd-item-icon" style="background:var(--surf3)">${item.icon}</div><div class="cmd-item-text"><div class="cmd-item-label">${item.label}</div><div class="cmd-item-desc">${item.desc}</div></div>`;
      d.onclick=()=>{closeCmd();item.action();};r.appendChild(d);
    });
  });
}

// ============================================================
// SEARCH IN CONVERSATION
// ============================================================
function openSearch(){document.getElementById("searchBar").classList.add("show");document.getElementById("searchInput").focus();}
document.getElementById("searchBtn").onclick=openSearch;
document.getElementById("searchClose").onclick=()=>{document.getElementById("searchBar").classList.remove("show");clearSearch();};
document.getElementById("searchInput").oninput=e=>searchInChat(e.target.value);
function searchInChat(q){
  clearSearch();
  if(!q){document.getElementById("searchCount").textContent="";return;}
  let count=0;
  document.querySelectorAll(".ai-text p,.msg-user").forEach(el=>{
    const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const nodes=[];let node;
    while(node=walker.nextNode())nodes.push(node);
    nodes.forEach(n=>{
      const idx=n.textContent.toLowerCase().indexOf(q.toLowerCase());
      if(idx>=0){
        count++;
        const after=n.splitText(idx);after.splitText(q.length);
        const span=document.createElement("span");span.className="search-highlight";
        span.textContent=after.textContent;
        after.parentNode.replaceChild(span,after);
        if(count===1)span.scrollIntoView({behavior:"smooth",block:"center"});
      }
    });
  });
  document.getElementById("searchCount").textContent=count?count+" résultat(s)":"Aucun résultat";
}
function clearSearch(){
  document.querySelectorAll(".search-highlight").forEach(el=>{
    const p=el.parentNode;if(p){p.replaceChild(document.createTextNode(el.textContent),el);p.normalize();}
  });
}
// ============================================================
// GRAPH — Canvas pur, robuste, corrigé
// ============================================================
function parseExpr(rawExpr, paramValues){
  let e = rawExpr;
  Object.keys(paramValues).forEach(k=>{
    e=e.replace(new RegExp("\\b"+k+"\\b","g"), paramValues[k]);
  });
  e = e
    .replace(/\^/g,"**")
    .replace(/(\d)(x)/g,"$1*x")
    .replace(/\bsin\b/g,"Math.sin")
    .replace(/\bcos\b/g,"Math.cos")
    .replace(/\btan\b/g,"Math.tan")
    .replace(/\bexp\b/g,"Math.exp")
    .replace(/\bln\b/g,"Math.log")
    .replace(/\blog\b/g,"Math.log10")
    .replace(/\bsqrt\b/g,"Math.sqrt")
    .replace(/\babs\b/g,"Math.abs")
    .replace(/\bPI\b/g,"Math.PI");
  try{
    const fn=new Function("x","try{return "+e+";}catch(e){return NaN;}");
    return fn;
  }catch(err){return ()=>NaN;}
}

function detectGraphParams(expr){
  const defs=[
    {name:"A",min:0.1,max:10,step:0.1,default:1},
    {name:"k",min:0.01,max:3,step:0.01,default:0.5},
    {name:"B",min:-5,max:5,step:0.1,default:0},
    {name:"n",min:1,max:5,step:0.5,default:2},
    {name:"C",min:-10,max:10,step:0.5,default:0},
  ];
  return defs.filter(p=>new RegExp("\\b"+p.name+"\\b").test(expr));
}

function buildGraph(expr, params){
  params = params || [];
  const card=document.createElement("div");card.className="graph-card";
  const paramVals={};params.forEach(p=>paramVals[p.name]=p.default);

  const top=document.createElement("div");top.className="graph-top";
  top.innerHTML=`<span class="graph-label">📈 Graphique interactif</span>`;

  const wrap=document.createElement("div");wrap.className="graph-canvas-wrap";
  const cv=document.createElement("canvas");cv.className="graph-canvas";
  wrap.appendChild(cv);

  const eq=document.createElement("div");eq.className="graph-eq";
  eq.textContent="y = "+expr;

  card.appendChild(top);card.appendChild(wrap);card.appendChild(eq);

  if(params.length>0){
    const slWrap=document.createElement("div");slWrap.className="graph-sliders";
    params.forEach(p=>{
      const row=document.createElement("div");row.className="sl-row";
      const lbl=document.createElement("span");lbl.className="sl-lbl";lbl.textContent=p.name;
      const sl=document.createElement("input");sl.type="range";sl.className="sl-inp";
      sl.min=p.min;sl.max=p.max;sl.step=p.step;sl.value=p.default;
      const valEl=document.createElement("span");valEl.className="sl-val";valEl.textContent=p.default;
      sl.oninput=()=>{paramVals[p.name]=parseFloat(sl.value);valEl.textContent=parseFloat(sl.value).toFixed(2);draw();};
      row.appendChild(lbl);row.appendChild(sl);row.appendChild(valEl);slWrap.appendChild(row);
    });
    card.appendChild(slWrap);
  }

  function draw(){
    if(!cv.isConnected)return;
    const dpr=window.devicePixelRatio||1;
    const W=cv.parentElement.clientWidth||300, H=190;
    cv.width=Math.max(W*dpr,1);cv.height=Math.max(H*dpr,1);
    cv.style.width=W+"px";cv.style.height=H+"px";
    const ctx=cv.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);

    const bgColor=getComputedStyle(document.documentElement).getPropertyValue("--bg3").trim()||"#141426";
    ctx.fillStyle=bgColor;ctx.fillRect(0,0,W,H);

    const fn=parseExpr(expr,paramVals);
    const N=Math.max(Math.floor(W*1.5),100);
    const xs=[],ys=[];
    for(let i=0;i<=N;i++){
      const x=(i/N)*24-12;
      let y;
      try{y=fn(x);}catch(e){y=NaN;}
      xs.push(x);ys.push(y);
    }

    const validY=ys.filter(y=>typeof y==="number"&&isFinite(y)&&Math.abs(y)<1e5);
    if(validY.length<2){
      ctx.fillStyle="#f87171";ctx.font="12px Inter,sans-serif";ctx.textAlign="center";
      ctx.fillText("Expression invalide",W/2,H/2);return;
    }

    let yMin=Math.min(...validY),yMax=Math.max(...validY);
    if(yMax-yMin<0.01){const mid=(yMax+yMin)/2;yMin=mid-1;yMax=mid+1;}
    const yRange=yMax-yMin;

    const pad={t:14,b:26,l:36,r:10};
    const cW=W-pad.l-pad.r, cH=H-pad.t-pad.b;
    const toX=x=>pad.l+(x+12)/24*cW;
    const toY=y=>pad.t+cH-(y-yMin)/yRange*cH;

    // grille horizontale
    ctx.strokeStyle="rgba(138,92,246,.08)";ctx.lineWidth=1;
    for(let i=0;i<=4;i++){
      const gy=pad.t+i/4*cH;
      ctx.beginPath();ctx.moveTo(pad.l,gy);ctx.lineTo(W-pad.r,gy);ctx.stroke();
      const v=yMax-i/4*yRange;
      ctx.fillStyle="rgba(148,148,184,.55)";ctx.font="9px Inter,sans-serif";ctx.textAlign="right";
      ctx.fillText(v.toFixed(1),pad.l-4,gy+3);
    }
    // grille verticale
    for(let i=0;i<=4;i++){
      const gx=pad.l+i/4*cW;
      ctx.beginPath();ctx.moveTo(gx,pad.t);ctx.lineTo(gx,H-pad.b);ctx.stroke();
      const v=(i/4)*24-12;
      ctx.fillStyle="rgba(148,148,184,.55)";ctx.font="9px Inter,sans-serif";ctx.textAlign="center";
      ctx.fillText(v.toFixed(0),gx,H-pad.b+12);
    }

    // axes
    if(yMin<=0&&yMax>=0){
      const y0=toY(0);
      ctx.strokeStyle="rgba(192,132,252,.4)";ctx.lineWidth=1.4;
      ctx.beginPath();ctx.moveTo(pad.l,y0);ctx.lineTo(W-pad.r,y0);ctx.stroke();
    }
    const x0=toX(0);
    if(x0>=pad.l&&x0<=W-pad.r){
      ctx.strokeStyle="rgba(192,132,252,.4)";ctx.lineWidth=1.4;
      ctx.beginPath();ctx.moveTo(x0,pad.t);ctx.lineTo(x0,H-pad.b);ctx.stroke();
    }

    // glow
    ctx.save();ctx.strokeStyle="rgba(138,92,246,.18)";ctx.lineWidth=7;ctx.lineJoin="round";ctx.lineCap="round";
    drawCurve(ctx,xs,ys,toX,toY);ctx.restore();

    // courbe principale avec gradient
    const grad=ctx.createLinearGradient(pad.l,0,W-pad.r,0);
    grad.addColorStop(0,"#f472b6");grad.addColorStop(.5,"#8a5cf6");grad.addColorStop(1,"#38bdf8");
    ctx.strokeStyle=grad;ctx.lineWidth=2.5;ctx.lineJoin="round";ctx.lineCap="round";
    drawCurve(ctx,xs,ys,toX,toY);
  }

  function drawCurve(ctx,xs,ys,toX,toY){
    ctx.beginPath();let first=true;
    for(let i=0;i<xs.length;i++){
      const y=ys[i];
      if(typeof y!=="number"||!isFinite(y)||Math.abs(y)>1e5){first=true;continue;}
      const px=toX(xs[i]),py=toY(y);
      if(first){ctx.moveTo(px,py);first=false;}else ctx.lineTo(px,py);
    }
    ctx.stroke();
  }

  // dessiner après insertion dans le DOM (sinon clientWidth = 0)
  requestAnimationFrame(()=>requestAnimationFrame(draw));
  const ro=new ResizeObserver(()=>draw());
  setTimeout(()=>{if(cv.isConnected)ro.observe(cv.parentElement);},100);

  return card;
}

// ============================================================
// ARTEFACTS — l'utilisateur ne voit jamais le code brut par défaut
// ============================================================
const LANG_META={
  html:{icon:"🌐",label:"Page web",color:"#f97316",ext:"html"},
  css:{icon:"🎨",label:"Feuille de style",color:"#38bdf8",ext:"css"},
  js:{icon:"⚡",label:"Script JavaScript",color:"#fbbf24",ext:"js"},
  javascript:{icon:"⚡",label:"Script JavaScript",color:"#fbbf24",ext:"js"},
  python:{icon:"🐍",label:"Script Python",color:"#34d399",ext:"py"},
  py:{icon:"🐍",label:"Script Python",color:"#34d399",ext:"py"},
  bash:{icon:"⚙️",label:"Script Shell",color:"#a78bfa",ext:"sh"},
  sh:{icon:"⚙️",label:"Script Shell",color:"#a78bfa",ext:"sh"},
  json:{icon:"{}",label:"Données JSON",color:"#38bdf8",ext:"json"},
  sql:{icon:"🗄️",label:"Requête SQL",color:"#f472b6",ext:"sql"},
  java:{icon:"☕",label:"Programme Java",color:"#f97316",ext:"java"},
  cpp:{icon:"⚡",label:"Programme C++",color:"#8a5cf6",ext:"cpp"},
  ts:{icon:"🔷",label:"Script TypeScript",color:"#38bdf8",ext:"ts"},
  typescript:{icon:"🔷",label:"Script TypeScript",color:"#38bdf8",ext:"ts"},
  rust:{icon:"🦀",label:"Programme Rust",color:"#f97316",ext:"rs"},
  go:{icon:"🔵",label:"Programme Go",color:"#38bdf8",ext:"go"},
  md:{icon:"📝",label:"Document",color:"#9494b8",ext:"md"},
  markdown:{icon:"📝",label:"Document",color:"#9494b8",ext:"md"},
};

function escHtml(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}

// Stockage des artefacts générés (par id) pour réouverture depuis l'historique
const artifactStore = {};

function buildArtifactCard(lang,code,titleHint){
  const meta=LANG_META[lang]||{icon:"📄",label:"Document",color:"#a78bfa",ext:"txt"};
  const id="art_"+Math.random().toString(36).slice(2,9);
  artifactStore[id]={lang,code,meta};

  const card=document.createElement("div");card.className="artifact-card";card.dataset.artId=id;
  const lines=code.split("\n").length;
  const title=titleHint||meta.label;
  card.innerHTML=`
    <div class="artifact-card-icon" style="background:${meta.color}22;color:${meta.color}">${meta.icon}</div>
    <div class="artifact-card-info">
      <div class="artifact-card-title">${escHtml(title)}</div>
      <div class="artifact-card-sub">${meta.label} · ${lines} ligne${lines>1?"s":""} · Prêt</div>
    </div>
    <div class="artifact-card-arrow">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
    </div>`;
  card.onclick=()=>openArtifactPanel(id);
  return card;
}

function openArtifactPanel(id){
  const art=artifactStore[id];if(!art)return;
  closeArtifactPanel();

  const overlay=document.createElement("div");overlay.className="artifact-overlay";overlay.id="artifactOverlay";
  const panel=document.createElement("div");panel.className="artifact-panel";

  const head=document.createElement("div");head.className="artifact-panel-head";
  head.innerHTML=`
    <div class="artifact-panel-title"><span style="color:${art.meta.color}">${art.meta.icon}</span> ${art.meta.label}</div>
    <button class="artifact-panel-close" id="artClose">✕</button>`;

  const body=document.createElement("div");body.className="artifact-panel-body";
  const previewWrap=document.createElement("div");previewWrap.className="artifact-preview-wrap";

  if(["html",""].includes(art.lang)){
    const iframe=document.createElement("iframe");iframe.className="artifact-iframe";
    iframe.sandbox="allow-scripts allow-same-origin";iframe.srcdoc=art.code;
    previewWrap.appendChild(iframe);
  } else {
    const pre=document.createElement("div");pre.className="artifact-text-preview";
    pre.textContent=art.code;previewWrap.appendChild(pre);
  }
  body.appendChild(previewWrap);

  // Section code cachée (toggle)
  const codeSection=document.createElement("div");codeSection.className="artifact-code-section";
  codeSection.innerHTML=`<pre class="artifact-raw-code">${escHtml(art.code)}</pre>`;
  codeSection.style.display="none";
  body.appendChild(codeSection);

  const actions=document.createElement("div");actions.className="artifact-panel-actions";
  actions.innerHTML=`
    <button class="art-action-btn" id="artCopy">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      Copier
    </button>
    <button class="art-action-btn" id="artDownload">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      Télécharger
    </button>
    <button class="art-action-btn" id="artPdf">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      Imprimer PDF
    </button>
    <button class="art-action-btn ghost" id="artToggleCode">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      Voir le code
    </button>`;

  panel.appendChild(head);panel.appendChild(body);panel.appendChild(actions);
  overlay.appendChild(panel);document.body.appendChild(overlay);
  requestAnimationFrame(()=>overlay.classList.add("show"));

  document.getElementById("artClose").onclick=closeArtifactPanel;
  overlay.onclick=e=>{if(e.target===overlay)closeArtifactPanel();};

  document.getElementById("artCopy").onclick=()=>{
    navigator.clipboard?.writeText(art.code).then(()=>toast("✅ Copié !"));
  };
  document.getElementById("artDownload").onclick=()=>{
    const a=document.createElement("a");
    a.href=URL.createObjectURL(new Blob([art.code],{type:"text/plain"}));
    a.download="lumina-artefact."+art.meta.ext;a.click();
    toast("⬇️ Téléchargement...");
  };
  document.getElementById("artPdf").onclick=()=>exportArtifactToPdf(art);
  document.getElementById("artToggleCode").onclick=()=>{
    const showing=codeSection.style.display!=="none";
    codeSection.style.display=showing?"none":"block";
    previewWrap.style.display=showing?"":"none";
    document.getElementById("artToggleCode").classList.toggle("active",!showing);
  };
}

function closeArtifactPanel(){
  const o=document.getElementById("artifactOverlay");
  if(o){o.classList.remove("show");setTimeout(()=>o.remove(),250);}
}

// Génération PDF réelle via jsPDF (chargé dynamiquement, une seule fois)
let jsPDFLoaded=false;
function ensureJsPDF(){
  return new Promise(resolve=>{
    if(jsPDFLoaded&&window.jspdf){resolve();return;}
    const s=document.createElement("script");
    s.src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
    s.onload=()=>{jsPDFLoaded=true;resolve();};
    s.onerror=()=>{toast("❌ Impossible de charger le générateur PDF");resolve();};
    document.head.appendChild(s);
  });
}

async function exportArtifactToPdf(art){
  toast("📄 Génération du PDF...");
  await ensureJsPDF();
  if(!window.jspdf){toast("❌ Erreur PDF");return;}
  const {jsPDF}=window.jspdf;
  const doc=new jsPDF({unit:"pt",format:"a4"});
  const margin=40;const pageW=doc.internal.pageSize.getWidth();
  const maxWidth=pageW-margin*2;

  doc.setFont("courier","normal");doc.setFontSize(9);
  doc.setTextColor(20,20,20);
  doc.text(art.meta.label+" — Lumina AI",margin,margin);
  doc.setDrawColor(180,150,255);doc.line(margin,margin+8,pageW-margin,margin+8);

  const lines=doc.splitTextToSize(art.code,maxWidth);
  let y=margin+28;const lineHeight=12;const pageH=doc.internal.pageSize.getHeight();
  lines.forEach(line=>{
    if(y>pageH-margin){doc.addPage();y=margin;}
    doc.text(line,margin,y);y+=lineHeight;
  });
  doc.save("lumina-artefact.pdf");
  toast("✅ PDF généré !");
}

// ============================================================
// PARSING DU MESSAGE — code devient artefact, texte reste visible
// ============================================================
function parseCode(text){
  const parts=[];const re=/```(\w*)\n?([\s\S]*?)```/g;let li=0,m;
  while((m=re.exec(text))!==null){
    if(m.index>li)parts.push({t:"text",c:text.slice(li,m.index)});
    parts.push({t:"code",lang:(m[1]||"").toLowerCase(),c:m[2].trim()});
    li=m.index+m[0].length;
  }
  if(li<text.length)parts.push({t:"text",c:text.slice(li)});
  return parts;
}

function renderContent(text,container){
  parseCode(text).forEach(p=>{
    if(p.t==="text"){
      if(p.c.trim()){
        const d=document.createElement("p");
        d.style.cssText="white-space:pre-wrap;margin-bottom:4px;line-height:1.75;";
        d.textContent=p.c;container.appendChild(d);
      }
    } else {
      // Le code ne s'affiche JAMAIS brut dans le fil — uniquement comme carte artefact
      container.appendChild(buildArtifactCard(p.lang,p.c));
    }
  });
}

// ============================================================
// MESSAGES RENDER
// ============================================================
function renderMessages(){
  const ca=document.getElementById("chatArea");ca.innerHTML="";
  const msgs=state.messageHistory[state.conversations.current]||[];
  const we=document.getElementById("welcome");
  if(!msgs.length){ca.appendChild(we||mkWelcome());updateConvDisplay();return;}
  for(const msg of msgs)appendStoredMsg(msg);
  ca.scrollTop=ca.scrollHeight;
  updateConvDisplay();
}

function updateConvDisplay(){
  const c=state.conversations.list.find(c=>c.id===state.conversations.current);
  if(c)document.getElementById("convNameDisplay").textContent=c.title;
}

function appendStoredMsg(msg){
  const ca=document.getElementById("chatArea");
  if(msg.role==="user"){
    const w=document.createElement("div");w.className="msg-user-wrap";
    const b=document.createElement("div");b.className="msg-user";
    if(msg.type==="image")b.innerHTML=`<img src="${msg.content}" style="max-width:180px;border-radius:10px;display:block;">`;
    else b.textContent=msg.content||"";
    w.appendChild(b);ca.appendChild(w);return;
  }
  if(msg.type==="plot"){const g=buildGraph(msg.expr,msg.params||[]);const w=wrapAiMsg(g);ca.appendChild(w);return;}
  if(msg.type==="image_gen"){
    const wrap=document.createElement("div");
    const lbl=document.createElement("div");lbl.style.cssText="font-size:.72rem;color:var(--txt3);font-weight:600;margin-bottom:4px;";lbl.textContent="✦ Image générée";
    const img=document.createElement("img");img.className="img-revealed";img.src=msg.content;img.onclick=()=>window.open(msg.content);
    wrap.appendChild(lbl);wrap.appendChild(img);
    const group=wrapAiMsg(wrap);ca.appendChild(group);return;
  }
  const body=document.createElement("div");body.className="ai-body";
  const name=document.createElement("div");name.className="ai-name";name.textContent="Lumina";
  const td=document.createElement("div");td.className="ai-text";
  renderContent(msg.content||"",td);
  body.appendChild(name);body.appendChild(td);
  body.appendChild(buildMsgActions(msg.content||""));
  const group=document.createElement("div");group.className="msg-group";
  const row=document.createElement("div");row.className="msg-ai-wrap";
  const av=mkAv(false);row.appendChild(av);row.appendChild(body);
  group.appendChild(row);ca.appendChild(group);
  runtime.lastAiGroup=group;
}

function wrapAiMsg(content){
  const group=document.createElement("div");group.className="msg-group";
  const row=document.createElement("div");row.className="msg-ai-wrap";
  const av=mkAv(false);const body=document.createElement("div");body.className="ai-body";
  body.appendChild(content);row.appendChild(av);row.appendChild(body);group.appendChild(row);
  return group;
}

function mkAv(spinning){
  const av=document.createElement("div");av.className="ai-av"+(spinning?" spin":"");
  av.innerHTML=`<svg width="16" height="16" viewBox="0 0 100 100" fill="none"><line x1="50" y1="10" x2="50" y2="90" stroke="#fff" stroke-width="8" stroke-linecap="round"/><line x1="10" y1="50" x2="90" y2="50" stroke="#fff" stroke-width="8" stroke-linecap="round"/><line x1="22" y1="22" x2="78" y2="78" stroke="#fff" stroke-width="6" stroke-linecap="round"/><line x1="78" y1="22" x2="22" y2="78" stroke="#fff" stroke-width="6" stroke-linecap="round"/><circle cx="50" cy="50" r="10" fill="#fff" opacity=".9"/></svg>`;
  return av;
}

function mkWelcome(){return document.getElementById("welcome");}
// ============================================================
// MESSAGE ACTIONS
// ============================================================
function buildMsgActions(txt){
  const bar=document.createElement("div");bar.className="msg-actions";

  const pb=document.createElement("button");pb.className="m-btn";
  pb.innerHTML=`<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="5 3 19 12 5 21 5 3"/></svg> Lire`;
  pb.onclick=()=>{
    if(runtime.ttsSpeaking){stopTTS();pb.classList.remove("active");pb.innerHTML=`<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="5 3 19 12 5 21 5 3"/></svg> Lire`;return;}
    speakFull(txt,()=>{pb.classList.remove("active");pb.innerHTML=`<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><polygon points="5 3 19 12 5 21 5 3"/></svg> Lire`;});
    pb.classList.add("active");pb.innerHTML=`<svg viewBox="0 0 24 24" fill="currentColor" width="12" height="12"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Stop`;
  };

  const cb=document.createElement("button");cb.className="m-btn";
  cb.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copier`;
  cb.onclick=()=>navigator.clipboard?.writeText(txt).then(()=>toast("✅ Copié !"));

  const rb=document.createElement("button");rb.className="m-btn";
  rb.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg> Réessayer`;
  rb.onclick=async()=>{
    if(runtime.isStreaming)return;
    const msgs=state.messageHistory[state.conversations.current]||[];
    let lastUser=null;for(let i=msgs.length-1;i>=0;i--){if(msgs[i].role==="user"){lastUser=msgs[i].content;break;}}
    if(!lastUser)return;
    let lastAi=-1;for(let i=msgs.length-1;i>=0;i--){if(msgs[i].role==="assistant"){lastAi=i;break;}}
    if(lastAi>=0)msgs.splice(lastAi,1);
    if(runtime.lastAiGroup)runtime.lastAiGroup.remove();
    save();await sendMessage(lastUser,true);
  };

  const sb=document.createElement("button");sb.className="m-btn";
  sb.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`;
  sb.onclick=()=>{if(navigator.share)navigator.share({text:txt});else navigator.clipboard?.writeText(txt).then(()=>toast("✅ Copié !"));};

  const lb=document.createElement("button");lb.className="m-btn";lb.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/></svg>`;
  lb.onclick=()=>{lb.classList.toggle("liked");db.classList.remove("disliked");};
  const db=document.createElement("button");db.className="m-btn";db.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/></svg>`;
  db.onclick=()=>{db.classList.toggle("disliked");lb.classList.remove("liked");};

  [pb,cb,rb,sb,lb,db].forEach(b=>bar.appendChild(b));

  const reactions=document.createElement("div");reactions.className="reactions";
  ["❤️","😂","👏","🔥","💡"].forEach(emoji=>{
    const r=document.createElement("span");r.className="reaction";r.textContent=emoji;
    r.onclick=()=>{r.style.background="rgba(138,92,246,.2)";r.style.borderColor="rgba(138,92,246,.4)";};
    reactions.appendChild(r);
  });
  bar.appendChild(reactions);

  return bar;
}

// ============================================================
// STREAMING — corrigé pour respecter Stop
// ============================================================
async function streamResponse(text){
  if(!state.messageHistory[state.conversations.current])state.messageHistory[state.conversations.current]=[];
  const ca=document.getElementById("chatArea");
  const we=document.getElementById("welcome");if(we&&we.parentNode===ca)we.remove();

  const group=document.createElement("div");group.className="msg-group";
  const row=document.createElement("div");row.className="msg-ai-wrap";
  const av=mkAv(true);
  const body=document.createElement("div");body.className="ai-body";
  const name=document.createElement("div");name.className="ai-name";name.textContent="Lumina";

  const status=document.createElement("div");status.className="ai-status";
  status.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Analyse en cours...`;
  body.appendChild(name);body.appendChild(status);
  row.appendChild(av);row.appendChild(body);group.appendChild(row);ca.appendChild(group);
  ca.scrollTop=ca.scrollHeight;

  await new Promise(r=>setTimeout(r,450));
  if(runtime.stopRequested){group.remove();return;}
  status.remove();

  const td=document.createElement("div");td.className="ai-text";
  const cur=document.createElement("span");cur.className="stream-cur";
  body.appendChild(td);td.appendChild(cur);
  av.classList.remove("spin");

  const delay=Math.max(5,Math.min(16,900/Math.max(text.length,1)));
  let acc="";
  for(let i=0;i<text.length;i++){
    if(runtime.stopRequested)break;
    acc+=text[i];cur.textContent=acc;
    if(i%6===0)ca.scrollTop=ca.scrollHeight;
    await new Promise(r=>setTimeout(r,delay));
  }
  cur.remove();td.innerHTML="";
  renderContent(acc,td);
  body.appendChild(buildMsgActions(acc));

  const mo={role:"assistant",content:acc,type:"text"};
  state.messageHistory[state.conversations.current].push(mo);
  runtime.lastReply=acc;runtime.lastAiGroup=group;
  lastReply=acc;
  save();

  // Lecture auto SEULEMENT si activée ET pas stoppé
  if(settings.autoTTS&&!runtime.stopRequested)speakFull(acc);
}

// ============================================================
// TTS — corrigé : ne coupe plus, voix française fiable
// ============================================================
function stopTTS(){
  if(window.speechSynthesis){window.speechSynthesis.cancel();}
  runtime.ttsQueue=[];runtime.ttsSpeaking=false;runtime.currentSpeech=null;
  const btn=document.getElementById("ttsBtn");if(btn)btn.classList.remove("tts-on");
}

function cleanForSpeech(text){
  return text
    .replace(/```[\s\S]*?```/g," bloc de code.")
    .replace(/\*\*([^*]+)\*\*/g,"$1")
    .replace(/\*([^*]+)\*/g,"$1")
    .replace(/#+\s/g,"")
    .replace(/`([^`]+)`/g,"$1")
    .replace(/https?:\/\/\S+/g," lien.")
    .replace(/_{1,2}([^_]+)_{1,2}/g,"$1")
    .replace(/\n{2,}/g,". ")
    .replace(/\n/g," ")
    .replace(/\s{2,}/g," ")
    .trim();
}

function speakFull(text, onDone=null){
  stopTTS();
  if(!window.speechSynthesis){if(onDone)onDone();return;}

  const clean=cleanForSpeech(text);
  if(!clean){if(onDone)onDone();return;}

  // Découpage en phrases courtes — évite le bug "coupe avant la fin"
  const rawSentences=clean.match(/[^.!?]+[.!?]*/g)||[clean];
  // Re-découper les phrases trop longues (>200 caractères) au niveau des virgules
  const sentences=[];
  rawSentences.forEach(s=>{
    s=s.trim();if(!s)return;
    if(s.length<=200){sentences.push(s);return;}
    const subParts=s.split(/,\s*/);
    let buf="";
    subParts.forEach(part=>{
      if((buf+part).length>180){if(buf)sentences.push(buf.trim());buf=part;}
      else buf+=(buf?", ":"")+part;
    });
    if(buf)sentences.push(buf.trim());
  });

  runtime.ttsQueue=sentences.length?sentences:[clean];
  runtime.ttsSpeaking=true;
  const btn=document.getElementById("ttsBtn");if(btn)btn.classList.add("tts-on");

  function next(){
    if(!runtime.ttsSpeaking||runtime.ttsQueue.length===0){
      runtime.ttsSpeaking=false;
      if(btn)btn.classList.remove("tts-on");
      if(onDone)onDone();
      return;
    }
    const chunk=runtime.ttsQueue.shift();
    const utt=new SpeechSynthesisUtterance(chunk);
    utt.lang="fr-FR";utt.rate=0.95;utt.pitch=1.0;utt.volume=1;

    const voices=window.speechSynthesis.getVoices();
    const frVoice=
      voices.find(v=>v.lang.toLowerCase().startsWith("fr")&&/thomas|amelie|marie|denise|celine/i.test(v.name)) ||
      voices.find(v=>v.lang.toLowerCase()==="fr-fr") ||
      voices.find(v=>v.lang.toLowerCase().startsWith("fr"));
    if(frVoice)utt.voice=frVoice;

    let ended=false;
    // Hack Chrome/Android : la synthèse se met en pause après ~15s d'inactivité
    const keepAlive=setInterval(()=>{
      if(ended){clearInterval(keepAlive);return;}
      if(window.speechSynthesis.speaking&&!window.speechSynthesis.paused){
        window.speechSynthesis.pause();window.speechSynthesis.resume();
      }
    },4000);

    utt.onend=()=>{ended=true;clearInterval(keepAlive);if(runtime.ttsSpeaking)setTimeout(next,40);};
    utt.onerror=()=>{ended=true;clearInterval(keepAlive);if(runtime.ttsSpeaking)setTimeout(next,40);};

    runtime.currentSpeech=utt;
    window.speechSynthesis.speak(utt);
  }
  next();
}

document.getElementById("ttsBtn").onclick=()=>{
  if(runtime.ttsSpeaking){stopTTS();}
  else{if(runtime.lastReply)speakFull(runtime.lastReply);else toast("Aucune réponse à lire");}
};

if(window.speechSynthesis){
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged=()=>window.speechSynthesis.getVoices();
}
// ============================================================
// VOICE INPUT
// ============================================================
let recog=null;
if("SpeechRecognition" in window||"webkitSpeechRecognition" in window){
  recog=new(window.SpeechRecognition||window.webkitSpeechRecognition)();
  recog.lang="fr-FR";recog.continuous=false;recog.interimResults=true;
}
document.getElementById("voiceBtn").onclick=()=>{
  if(!recog){toast("🎤 Micro non supporté");return;}
  window.speechSynthesis?.cancel();
  const btn=document.getElementById("voiceBtn");
  btn.classList.add("on");
  const f=document.getElementById("userInput");f.placeholder="🎤 En écoute...";
  try{recog.start();}catch(e){}
  recog.onresult=e=>{
    const t=Array.from(e.results).map(r=>r[0].transcript).join("");
    f.value=t;autoResize();
    if(e.results[e.results.length-1].isFinal){btn.classList.remove("on");f.placeholder="Message à Lumina...";}
  };
  recog.onerror=()=>{btn.classList.remove("on");f.placeholder="Message à Lumina...";toast("Erreur micro");};
  recog.onend=()=>{btn.classList.remove("on");f.placeholder="Message à Lumina...";};
};

// ============================================================
// BACKEND
// ============================================================
async function callBackend(msg){
  const model=MODELS.find(m=>m.id===state.currentModel)||MODELS[0];
  try{
    const r=await fetch(API,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({message:msg,model:model.model,temperature:0.75})});
    if(!r.ok)return"Erreur serveur ("+r.status+"). Vérifie que Flask tourne sur le port 5005.";
    const d=await r.json();return d.reply||d.response||d.text||"Pas de réponse.";
  }catch(e){return"⚠️ Impossible de joindre Lumina. Vérifie la connexion au serveur.";}
}

// ============================================================
// SEND MESSAGE
// ============================================================
async function sendMessage(msgOverride, retry=false){
  const ca=document.getElementById("chatArea");
  const f=document.getElementById("userInput");
  const msg=(msgOverride||f.value).trim();
  if(!msg||runtime.isStreaming)return;
  if(!navigator.onLine&&!msgOverride){runtime.pendingOffline=msg;document.getElementById("offlineBanner").style.display="block";toast("⚡ Hors ligne");return;}

  runtime.isStreaming=true;runtime.stopRequested=false;

  const sendBtn=document.getElementById("sendBtn");
  sendBtn.classList.add("stop-active");
  sendBtn.innerHTML=`<svg width="12" height="12" viewBox="0 0 24 24" fill="white"><rect x="3" y="3" width="18" height="18" rx="3"/></svg>`;

  if(!retry){f.value="";autoResize();}
  const we=document.getElementById("welcome");if(we&&we.parentNode===ca)we.remove();

  if(!retry){
    const uw=document.createElement("div");uw.className="msg-user-wrap";
    const ub=document.createElement("div");ub.className="msg-user";ub.textContent=msg;
    uw.appendChild(ub);ca.appendChild(uw);ca.scrollTop=ca.scrollHeight;
    if(!state.messageHistory[state.conversations.current])state.messageHistory[state.conversations.current]=[];
    const conv=state.conversations.list.find(c=>c.id===state.conversations.current);
    if(conv&&conv.title==="Nouvelle discussion")conv.title=msg.slice(0,40)+(msg.length>40?"…":"");
    state.messageHistory[state.conversations.current].push({role:"user",content:msg,type:"text"});
    save();renderConvList();updateConvDisplay();
  }

  if(!retry){
    if(tryPlot(msg)){finishStreaming();return;}
    if(/^(génère|genere|dessine|crée une image|génère une image)\s+/i.test(msg)){
      await generateImage(msg.replace(/^(génère|genere|dessine|crée une image|génère une image)\s+/i,"").trim());
      finishStreaming();return;
    }
    if(/^joue\s+/i.test(msg)){await playMusic(msg.replace(/^joue\s+/i,"").trim());finishStreaming();return;}
  }

  const reply=await callBackend(msg);
  if(!runtime.stopRequested)await streamResponse(reply);
  finishStreaming();
}

function finishStreaming(){
  runtime.isStreaming=false;runtime.stopRequested=false;
  const sendBtn=document.getElementById("sendBtn");
  sendBtn.classList.remove("stop-active");
  sendBtn.innerHTML=`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
}

function quickSend(m){sendMessage(m);}

// ============================================================
// PLOT
// ============================================================
function tryPlot(msg){
  const ca=document.getElementById("chatArea");
  const m=msg.match(/^(?:y|f\(x\)|f)\s*=\s*(.+)/i);if(!m)return false;
  const expr=m[1].trim();
  const we=document.getElementById("welcome");if(we&&we.parentNode===ca)we.remove();
  const params=detectGraphParams(expr);
  const g=buildGraph(expr,params);
  const group=wrapAiMsg(g);ca.appendChild(group);
  ca.scrollTop=ca.scrollHeight;
  if(!state.messageHistory[state.conversations.current])state.messageHistory[state.conversations.current]=[];
  state.messageHistory[state.conversations.current].push({role:"assistant",content:expr,type:"plot",expr,params});
  save();return true;
}

// ============================================================
// IMAGE GENERATION
// ============================================================
async function generateImage(prompt){
  const ca=document.getElementById("chatArea");
  const we=document.getElementById("welcome");if(we&&we.parentNode===ca)we.remove();

  const ph=document.createElement("div");ph.className="img-ph";
  ph.innerHTML=`<svg width="40" height="40" viewBox="0 0 100 100" fill="none"><line x1="50" y1="10" x2="50" y2="90" stroke="#8a5cf6" stroke-width="6" stroke-linecap="round"/><line x1="10" y1="50" x2="90" y2="50" stroke="#8a5cf6" stroke-width="6" stroke-linecap="round"/><line x1="22" y1="22" x2="78" y2="78" stroke="#8a5cf6" stroke-width="5" stroke-linecap="round"/><line x1="78" y1="22" x2="22" y2="78" stroke="#8a5cf6" stroke-width="5" stroke-linecap="round"/><circle cx="50" cy="50" r="10" stroke="#8a5cf6" stroke-width="3" fill="#080810"/><circle cx="50" cy="50" r="5" fill="#fff"/></svg><div style="font-size:.8rem;color:var(--acc2);margin-top:6px;">Génération en cours...</div>`;
  const group=wrapAiMsg(ph);ca.appendChild(group);ca.scrollTop=ca.scrollHeight;

  const seed=Math.floor(Math.random()*99999);
  const urls=[
    `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt+" ultra detailed 4k")}?width=512&height=512&nologo=true&model=flux&seed=${seed}`,
    `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=512&height=512&nologo=true&model=turbo&seed=${seed}`,
    `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}?width=512&height=512&nologo=true&seed=${seed}`,
  ];

  let url=null;
  for(const u of urls){
    if(runtime.stopRequested)break;
    try{await new Promise((res,rej)=>{const img=new Image();img.onload=()=>{url=u;res();};img.onerror=rej;img.src=u;setTimeout(res,22000);});if(url)break;}catch(e){}
  }

  ph.style.opacity="0";ph.style.transition="opacity .35s";
  await new Promise(r=>setTimeout(r,350));

  if(url&&!runtime.stopRequested){
    const lbl=document.createElement("div");lbl.style.cssText="font-size:.72rem;color:var(--txt3);font-weight:600;margin-bottom:4px;";lbl.textContent="✦ Image générée";
    const img=document.createElement("img");img.className="img-revealed";img.src=url;img.alt=prompt;img.onclick=()=>window.open(url);
    ph.replaceWith(lbl);
    group.querySelector(".ai-body").appendChild(img);
    group.querySelector(".ai-body").appendChild(buildMsgActions("Image générée pour : "+prompt));
    if(!state.messageHistory[state.conversations.current])state.messageHistory[state.conversations.current]=[];
    state.messageHistory[state.conversations.current].push({role:"assistant",content:url,type:"image_gen"});
    save();
  }else{
    const errDiv=document.createElement("div");errDiv.style.cssText="color:var(--err);font-size:.8rem;";errDiv.textContent="❌ Génération échouée.";
    ph.replaceWith(errDiv);
  }
  ca.scrollTop=ca.scrollHeight;
}

// ============================================================
// MUSIC — Jamendo + Génération IA Hugging Face MusicGen
// ============================================================
let musicFiles=[];

function getHFToken(){return localStorage.getItem("lv4_hf_token")||"";}
function setHFToken(t){localStorage.setItem("lv4_hf_token",t);}

async function promptHFToken(){
  return new Promise(resolve=>{
    const overlay=document.createElement("div");
    overlay.style.cssText="position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.85);backdrop-filter:blur(10px);display:flex;align-items:center;justify-content:center;padding:24px;";
    overlay.innerHTML=`<div style="background:var(--bg3);border:1px solid var(--border2);border-radius:20px;padding:24px;width:100%;max-width:340px;"><div style="font-family:var(--fd);font-size:1rem;font-weight:700;margin-bottom:8px;">🎵 Génération musicale IA</div><div style="font-size:.82rem;color:var(--txt2);margin-bottom:16px;line-height:1.6;">Pour générer de la musique, Lumina utilise <b>Hugging Face MusicGen</b> (gratuit).<br><br>Crée un compte sur <b>huggingface.co</b> → Settings → Access Tokens → New token (Read).</div><input id="hfTokenInput" type="text" placeholder="hf_xxxxxxxxxxxxxxxxxxxx" style="width:100%;background:var(--surf2);border:1px solid var(--border);border-radius:11px;padding:11px 13px;color:var(--txt);font-size:.88rem;font-family:var(--fb);outline:none;margin-bottom:14px;-webkit-appearance:none;"><div style="display:flex;gap:8px;"><button id="hfCancel" style="flex:1;padding:10px;border-radius:11px;background:var(--surf2);border:1px solid var(--border);color:var(--txt2);font-size:.85rem;cursor:pointer;font-family:var(--fb);">Annuler</button><button id="hfConfirm" style="flex:1;padding:10px;border-radius:11px;background:linear-gradient(135deg,var(--acc),var(--acc2));border:none;color:#fff;font-size:.85rem;cursor:pointer;font-family:var(--fd);font-weight:700;">Confirmer</button></div></div>`;
    document.body.appendChild(overlay);
    document.getElementById("hfConfirm").onclick=()=>{
      const v=document.getElementById("hfTokenInput").value.trim();
      if(v){setHFToken(v);overlay.remove();resolve(v);}
      else document.getElementById("hfTokenInput").style.borderColor="var(--err)";
    };
    document.getElementById("hfCancel").onclick=()=>{overlay.remove();resolve(null);};
    setTimeout(()=>document.getElementById("hfTokenInput")?.focus(),100);
  });
}

async function generateMusicAI(prompt){
  let token=getHFToken();
  if(!token){token=await promptHFToken();if(!token){await streamResponse("🎵 Token Hugging Face requis pour générer de la musique. Réessaie.");return;}}
  const ca=document.getElementById("chatArea");
  const statusDiv=document.createElement("div");statusDiv.className="ai-status";statusDiv.id="musicGenStatus";
  statusDiv.style.cssText="padding:8px 12px;background:var(--surf2);border-radius:12px;margin:6px 0;font-size:.8rem;";
  statusDiv.innerHTML=`<svg style="animation:spin 1s linear infinite" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> Composition musicale en cours... (peut prendre 30-60s)`;
  ca.appendChild(statusDiv);ca.scrollTop=ca.scrollHeight;
  try{
    const response=await fetch("https://api-inference.huggingface.co/models/facebook/musicgen-small",
      {method:"POST",headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},
       body:JSON.stringify({inputs:prompt,parameters:{max_new_tokens:256}})});
    if(response.status===503){
      const j=await response.json().catch(()=>({}));
      const wait=Math.min((j.estimated_time||30)*1000,60000);
      statusDiv.innerHTML=`⏳ Modèle en démarrage, attente ${Math.ceil(wait/1000)}s...`;
      await new Promise(r=>setTimeout(r,wait));
      statusDiv.remove();await generateMusicAI(prompt);return;
    }
    if(response.status===401||response.status===403){setHFToken("");statusDiv.remove();await streamResponse("❌ Token Hugging Face invalide ou expiré. Retente — tu seras invité à le ressaisir.");return;}
    if(!response.ok){const e=await response.json().catch(()=>({}));throw new Error(e.error||"Erreur "+response.status);}
    const blob=await response.blob();
    const url=URL.createObjectURL(blob);
    statusDiv.remove();
    playAudio(url,`🎵 Musique IA — "${prompt.slice(0,40)}"`);
    await streamResponse(`🎵 Musique composée avec succès !\n\nGénérée par Lumina IA (MusicGen · Meta) pour :\n_${prompt}_`);
  }catch(e){
    statusDiv.remove();
    await streamResponse(`❌ Erreur de génération musicale : ${e.message}\n\nVérifie ta connexion et ton token Hugging Face.`);
  }
}

async function playMusic(q){
  const local=musicFiles.find(f=>f.name.toLowerCase().includes(q.toLowerCase()));
  if(local){playAudio(URL.createObjectURL(local.file),local.name);await streamResponse("🎵 Lecture de : "+local.name);return;}
  if(/génère|compose|cr[ée]{1,2}|produis|fais.*(morceau|chanson|musique|beat|mélodie|son)/i.test(q)){
    await generateMusicAI(q);return;
  }
  await searchJamendo(q);
}

async function searchJamendo(q){
  try{
    const r=await fetch(`https://api.jamendo.com/v3.0/tracks/?client_id=${JAMENDO}&format=json&limit=5&search=${encodeURIComponent(q)}&audiodownload=1&order=relevance`);
    const d=await r.json();
    if(d.results&&d.results.length&&d.results[0].audio){
      const t=d.results[0];playAudio(t.audio,`${t.name} — ${t.artist_name}`);
      await streamResponse(`🎵 **${t.name}** par ${t.artist_name}\n\nJamendo · Musique libre`);return;
    }
  }catch(e){}
  await streamResponse(`🎵 Aucun résultat pour "${q}" sur Jamendo.\n\nDis-moi "Génère une musique relaxante" pour que je compose quelque chose avec l'IA.`);
}
function playAudio(url,name){
  document.getElementById("audioBar")?.remove();
  if(runtime.currentAudio){runtime.currentAudio.pause();}
  runtime.currentAudio=new Audio(url);runtime.currentAudio.play().catch(()=>{});
  const bar=document.createElement("div");bar.id="audioBar";bar.className="audio-player";
  bar.innerHTML=`<button class="aud-play" id="audPlay">⏸</button><div class="aud-info"><div class="aud-title">${name}</div><div class="aud-bar"><div class="aud-fill" id="audFill"></div></div></div><button class="aud-stop" id="audStop">■</button>`;
  document.getElementById("chatArea").appendChild(bar);
  document.getElementById("audPlay").onclick=()=>{if(runtime.currentAudio.paused){runtime.currentAudio.play();document.getElementById("audPlay").textContent="⏸";}else{runtime.currentAudio.pause();document.getElementById("audPlay").textContent="▶";}};
  document.getElementById("audStop").onclick=()=>{runtime.currentAudio.pause();runtime.currentAudio=null;bar.remove();};
  runtime.currentAudio.ontimeupdate=()=>{if(!runtime.currentAudio||!runtime.currentAudio.duration)return;document.getElementById("audFill").style.width=(runtime.currentAudio.currentTime/runtime.currentAudio.duration*100)+"%";};
  runtime.currentAudio.onended=()=>bar.remove();
}

// ============================================================
// IMAGE ANALYSIS / FILES
// ============================================================
document.getElementById("imgInput").onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  const reader=new FileReader();
  reader.onload=async ev=>{
    const ca=document.getElementById("chatArea");
    const we=document.getElementById("welcome");if(we&&we.parentNode===ca)we.remove();
    const uw=document.createElement("div");uw.className="msg-user-wrap";
    const ub=document.createElement("div");ub.className="msg-user";
    ub.innerHTML=`<img src="${ev.target.result}" style="max-width:180px;border-radius:10px;display:block;">`;
    uw.appendChild(ub);ca.appendChild(uw);ca.scrollTop=ca.scrollHeight;
    if(!state.messageHistory[state.conversations.current])state.messageHistory[state.conversations.current]=[];
    state.messageHistory[state.conversations.current].push({role:"user",content:ev.target.result,type:"image"});save();
    runtime.isStreaming=true;
    const reply=await callBackend("Analyse cette image en détail. Décris ce que tu vois, les couleurs, les éléments, le contexte. Réponds en français.");
    if(!runtime.stopRequested)await streamResponse(reply);finishStreaming();
  };reader.readAsDataURL(file);e.target.value="";
};

document.getElementById("audioInput").onchange=async e=>{
  const files=Array.from(e.target.files);if(!files.length)return;
  musicFiles=files.map(f=>({name:f.name.replace(/\.[^.]+$/,""),file:f}));
  toast(`✅ ${files.length} fichier(s) audio chargé(s)`);
};

document.getElementById("fileInput").onchange=async e=>{
  const file=e.target.files[0];if(!file)return;
  const reader=new FileReader();reader.onload=async ev=>{
    runtime.isStreaming=true;
    const reply=await callBackend(`Analyse ce fichier "${file.name}" :\n${ev.target.result.slice(0,3000)}`);
    if(!runtime.stopRequested)await streamResponse(reply);finishStreaming();
  };reader.readAsText(file);e.target.value="";
};

// ============================================================
// PLUS MENU
// ============================================================
function closePlus(){document.getElementById("plusMenu").classList.remove("show");document.getElementById("plusBtn").classList.remove("open");}
document.getElementById("plusBtn").onclick=e=>{
  e.stopPropagation();
  const s=document.getElementById("plusMenu").classList.toggle("show");
  document.getElementById("plusBtn").classList.toggle("open",s);
};
document.addEventListener("click",e=>{
  const pm=document.getElementById("plusMenu");
  if(!pm.contains(e.target)&&e.target!==document.getElementById("plusBtn"))closePlus();
  if(runtime.ctxMenu&&!runtime.ctxMenu.contains(e.target))closeCtx();
});
document.getElementById("pmPhoto").onclick=()=>{document.getElementById("imgInput").click();closePlus();};
document.getElementById("pmImage").onclick=()=>{document.getElementById("imgInput").click();closePlus();};
document.getElementById("pmAudio").onclick=()=>{document.getElementById("audioInput").click();closePlus();};
document.getElementById("pmDoc").onclick=()=>{document.getElementById("fileInput").click();closePlus();};
document.getElementById("pmCode").onclick=()=>{setInput("Génère un exemple de code Python avec une classe et ses méthodes");closePlus();};
document.getElementById("pmGraph").onclick=()=>{setInput("y = A*sin(k*x)*exp(-0.1*x)");closePlus();};
document.getElementById("pmWeb").onclick=()=>{settings.webSearch=!settings.webSearch;saveSetting("webSearch",settings.webSearch);applySettings();toast(settings.webSearch?"🌐 Recherche web activée":"Recherche web désactivée");};
document.getElementById("pmVideo").onclick=()=>toast("🎬 Génération vidéo — bientôt disponible");

// ============================================================
// OFFLINE
// ============================================================
window.addEventListener("offline",()=>document.getElementById("offlineBanner").style.display="block");
window.addEventListener("online",()=>{
  document.getElementById("offlineBanner").style.display="none";
  if(runtime.pendingOffline){const m=runtime.pendingOffline;runtime.pendingOffline=null;sendMessage(m);}
});

// ============================================================
// INIT
// ============================================================
(function init(){
  applySettings();
  if(!state.conversations.list.length)newConversation();
  else{
    if(!state.conversations.current)state.conversations.current=state.conversations.list[0].id;
    renderConvList();renderMessages();
  }
  const msgs=state.messageHistory[state.conversations.current]||[];
  if(!msgs.length){
    setTimeout(async()=>{
      const name=state.userName&&state.userName!=="vous"?state.userName:null;
      const greet=name
        ?`Bonjour ${name} ! Je suis **Lumina**, ton assistant IA multimodal.\n\nJe peux générer des images, tracer des graphiques interactifs, écrire du code, jouer de la musique, analyser tes fichiers et bien plus encore.\n\nPar quoi veux-tu commencer ?`
        :`Bonjour ! Je suis **Lumina**, votre assistant IA multimodal.\n\nImages, graphiques, code, musique, analyse de fichiers — tout est accessible. Que souhaitez-vous créer ?`;
      runtime.isStreaming=true;
      await streamResponse(greet);
      finishStreaming();
    },800);
  }
  updateWelcomeName();
})();
