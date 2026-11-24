"use client";

import { FormEvent, useEffect, useState } from "react";

type Message = { role: "user" | "assistant"; content: string };
type Conversation = { id: string; title: string; model?: string };
type Model = { id: string; provider: string; label: string; free?: boolean | null; availability: string };
type Workspace = { id: string; name: string; role: string };
const fallbackModels: Model[] = [
  { id: "openrouter/openrouter/free", provider: "openrouter", label: "OpenRouter Free Router", availability: "quota-dependent" },
  { id: "ollama/llama3.2", provider: "ollama", label: "Llama 3.2 via Ollama", free: true, availability: "local" }
];
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [prompt,setPrompt]=useState("");
  const [model,setModel]=useState("openrouter/openrouter/free");
  const [models,setModels]=useState<Model[]>(fallbackModels);
  const [discovery,setDiscovery]=useState("Carregando catálogo...");
  const [messages,setMessages]=useState<Message[]>([]);
  const [conversations,setConversations]=useState<Conversation[]>([]);
  const [conversationId,setConversationId]=useState("");
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("Entre para acessar seu workspace.");
  const [token,setToken]=useState("");
  const [workspaces,setWorkspaces]=useState<Workspace[]>([]);
  const [workspaceId,setWorkspaceId]=useState("");
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [authMode,setAuthMode]=useState<"login"|"register">("login");
  const [authError,setAuthError]=useState("");
  const [authBusy,setAuthBusy]=useState(false);

  function headers(json=false) {
    return { ...(json?{"Content-Type":"application/json"}:{}), ...(token?{Authorization:"Bearer "+token}:{}), ...(workspaceId?{"X-Workspace-ID":workspaceId}:{}) };
  }
  async function loadWorkspaces(accessToken:string) {
    const h={Authorization:"Bearer "+accessToken};
    const response=await fetch(API+"/api/v1/workspaces",{headers:h});
    if(!response.ok)throw new Error("Não foi possível carregar seus workspaces.");
    let list:Workspace[]=(await response.json()).workspaces||[];
    if(!list.length){
      const created=await fetch(API+"/api/v1/workspaces",{method:"POST",headers:{...h,"Content-Type":"application/json"},body:JSON.stringify({name:"Meu workspace APOLO"})});
      if(!created.ok)throw new Error("Não foi possível criar seu primeiro workspace.");
      const workspace=await created.json();list=[workspace];
    }
    setWorkspaces(list);setWorkspaceId(list[0].id);
    return list[0].id;
  }
  async function refreshConversations(accessToken=token, activeWorkspace=workspaceId) {
    if(!accessToken||!activeWorkspace)return;
    try {
      const r=await fetch(API+"/api/v1/conversations",{headers:{Authorization:"Bearer "+accessToken,"X-Workspace-ID":activeWorkspace}});
      if(!r.ok)throw new Error("Falha ao carregar histórico.");
      const d=await r.json();setConversations(d.conversations||[]);
    } catch { setNotice("Não foi possível carregar o histórico."); }
  }
  useEffect(()=>{
    fetch(API+"/api/v1/models").then(r=>r.json()).then(d=>{
      const live:Model[]=d.models||[];
      if(live.length){setModels(live);setModel(live[0].id);setDiscovery(live.length+" modelos descobertos.");}
      else setDiscovery("Nenhum modelo detectado. Configure um provedor no servidor.");
    }).catch(()=>setDiscovery("Catálogo indisponível."));
    const saved=window.sessionStorage.getItem("apolo_access_token");
    if(saved){
      setToken(saved);
      fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+saved}}).then(async r=>{
        if(!r.ok)throw new Error("Sessão expirada.");
        let list:Workspace[]=(await r.json()).workspaces||[];
        if(!list.length){
          const cr=await fetch(API+"/api/v1/workspaces",{method:"POST",headers:{Authorization:"Bearer "+saved,"Content-Type":"application/json"},body:JSON.stringify({name:"Meu workspace APOLO"})});
          if(!cr.ok)throw new Error("Não foi possível criar workspace.");
          list=[await cr.json()];
        }
        setWorkspaces(list);setWorkspaceId(list[0].id);setNotice("Sessão autenticada.");
      }).catch(()=>{window.sessionStorage.removeItem("apolo_access_token");setToken("");});
    }
  },[]);
  useEffect(()=>{if(token&&workspaceId)refreshConversations(token,workspaceId);},[token,workspaceId]);

  async function authenticate(event:FormEvent) {
    event.preventDefault();setAuthBusy(true);setAuthError("");
    try {
      const endpoint=authMode==="register"?"register":"login";
      const r=await fetch(API+"/api/v1/auth/"+endpoint,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
      const d=await r.json();
      if(!r.ok)throw new Error(d.detail||"Falha na autenticação.");
      const accessToken=d.access_token;
      window.sessionStorage.setItem("apolo_access_token",accessToken);
      setToken(accessToken);
      await loadWorkspaces(accessToken);
      setPassword("");setNotice("Autenticado. Workspace pronto.");
    } catch(e) {setAuthError(e instanceof Error?e.message:"Não foi possível entrar.");}
    finally{setAuthBusy(false);}
  }
  async function logout() {
    try { await fetch(API+"/api/v1/auth/logout",{method:"POST",headers:{Authorization:"Bearer "+token}}); } catch {}
    window.sessionStorage.removeItem("apolo_access_token");setToken("");setWorkspaceId("");setWorkspaces([]);
    setConversations([]);setMessages([]);setConversationId("");setNotice("Você saiu da sua conta.");
  }
  async function openConversation(id:string) {
    setConversationId(id);
    const r=await fetch(API+"/api/v1/conversations/"+id+"/messages",{headers:headers()});
    const d=await r.json();
    if(!r.ok){setNotice(d.detail||"Falha ao abrir conversa.");return;}
    setMessages((d.messages||[]).filter((m:Message)=>m.role==="user"||m.role==="assistant"));
  }
  async function newConversation() {
    if(!token||!workspaceId)return;
    const r=await fetch(API+"/api/v1/conversations",{method:"POST",headers:headers(true),body:JSON.stringify({title:"Nova conversa",model})});
    const d=await r.json();if(!r.ok){setNotice(d.detail||"Falha ao criar conversa.");return;}
    setConversationId(d.id);setMessages([]);await refreshConversations();
  }
  async function saveMessage(id:string,message:Message) {
    const r=await fetch(API+"/api/v1/conversations/"+id+"/messages",{method:"POST",headers:headers(true),body:JSON.stringify(message)});
    if(!r.ok)throw new Error("Não foi possível salvar a mensagem.");
  }
  async function send(event?:FormEvent) {
    event?.preventDefault();
    const content=prompt.trim();if(!content||busy||!token||!workspaceId)return;
    setBusy(true);setPrompt("");setNotice("Recebendo resposta em tempo real...");
    let id=conversationId;
    try {
      if(!id){const r=await fetch(API+"/api/v1/conversations",{method:"POST",headers:headers(true),body:JSON.stringify({title:content.slice(0,70),model})});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao criar conversa.");id=d.id;setConversationId(id);}
      const user:Message={role:"user",content};const next=[...messages,user];
      setMessages([...next,{role:"assistant",content:""}]);await saveMessage(id,user);
      const response=await fetch(API+"/api/v1/chat/stream",{method:"POST",headers:headers(true),body:JSON.stringify({model,messages:next,temperature:0.7,max_tokens:1024})});
      if(!response.ok){const d=await response.json();throw new Error(typeof d.detail==="string"?d.detail:JSON.stringify(d.detail||d));}
      if(!response.body)throw new Error("O navegador não disponibilizou o fluxo de resposta.");
      const reader=response.body.getReader();const decoder=new TextDecoder();let buffer="";let answer="";
      while(true){
        const {value,done}=await reader.read();if(done)break;
        buffer+=decoder.decode(value,{stream:true});const frames=buffer.split("\n\n");buffer=frames.pop()||"";
        for(const frame of frames)for(const line of frame.split("\n")){
          if(!line.startsWith("data:"))continue;
          const raw=line.slice(5).trim();if(raw==="[DONE]")continue;
          const packet=JSON.parse(raw);if(packet.error)throw new Error(packet.error);
          if(typeof packet.delta==="string"){answer+=packet.delta;setMessages([...next,{role:"assistant",content:answer}]);}
        }
      }
      if(!answer)throw new Error("O provedor encerrou o fluxo sem texto.");
      await saveMessage(id,{role:"assistant",content:answer});setNotice("Resposta concluída e salva no histórico.");await refreshConversations();
    } catch(e) {setNotice(e instanceof Error?e.message:"Falha no chat.");}
    finally{setBusy(false);}
  }
  if(!token) return <div className="shell"><main className="auth-main"><div className="eyebrow">APOLO LANGDOCK</div><h1>Seu espaço de trabalho com IA.</h1><p className="sub">Entre ou crie sua conta para acessar conversas, agentes e workflows privados.</p><section className="card auth-card"><div className="chat-heading"><h2>{authMode==="login"?"Entrar":"Criar conta"}</h2><span>Workspace seguro</span></div><form className="auth-form" onSubmit={authenticate}><label htmlFor="email">E-mail</label><input id="email" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required/><label htmlFor="password">Senha {authMode==="register"?"(mínimo 12 caracteres)":""}</label><input id="password" type="password" autoComplete={authMode==="login"?"current-password":"new-password"} minLength={authMode==="register"?12:1} value={password} onChange={e=>setPassword(e.target.value)} required/><button type="submit" disabled={authBusy}>{authBusy?"Aguarde...":authMode==="login"?"Entrar":"Criar conta"}</button></form>{authError&&<p className="note error">{authError}</p>}<p className="note">{authMode==="login"?"Ainda não tem conta?":"Já possui conta?"} <button className="text-button" onClick={()=>{setAuthMode(authMode==="login"?"register":"login");setAuthError("");}}>{authMode==="login"?"Criar conta":"Entrar"}</button></p></section></main></div>;
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand">APOLO <span>LANGDOCK</span></div>
      <button className="new-chat" onClick={newConversation}>＋ Nova conversa</button>
      <div className="nav"><div className="active">◉ Chat multimodelo</div><div>✧ Modelos</div><div>◈ Agentes (API inicial)</div><div>⌘ Workflows (API inicial)</div><div>⌁ MCP & Ferramentas</div><div>⚙ Configurações</div></div>
      <label className="history-title" htmlFor="workspace">Workspace</label>
      <select id="workspace" value={workspaceId} onChange={e=>{setWorkspaceId(e.target.value);setConversationId("");setMessages([]);}}>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select>
      <h3 className="history-title">Histórico</h3>
      <div className="history">{conversations.map(c=><button key={c.id} className={conversationId===c.id?"selected":""} onClick={()=>openConversation(c.id)}>{c.title}</button>)}</div>
      <button className="logout" onClick={logout}>Sair da conta</button>
    </aside>
    <main>
      <div className="eyebrow">Open AI Workspace</div><h1>Seu espaço de trabalho com IA.</h1>
      <p className="sub">Converse com diferentes modelos e mantenha seu histórico separado por workspace. Sem assinatura APOLO; cotas e preços são definidos pelos provedores.</p>
      <section className="card chat-card">
        <div className="chat-heading"><h2>Chat multimodelo</h2><span>{conversationId?"Histórico salvo":"Nova sessão"}</span></div>
        <label htmlFor="model">Modelo descoberto automaticamente</label>
        <select id="model" value={model} onChange={e=>setModel(e.target.value)} disabled={busy}>{models.map(m=><option key={m.id} value={m.id}>{m.label} — {m.provider}{m.free===true?" · local/gratuito":""}</option>)}</select>
        <p className="note">{discovery}</p>
        <div className="messages" aria-live="polite">{messages.map((m,i)=><div key={i} className={"message "+m.role}><strong>{m.role==="user"?"Você":"APOLO"}</strong><p>{m.content||"…"}</p></div>)}</div>
        <form className="composer" onSubmit={send}><input value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Escreva uma mensagem..." disabled={busy}/><button type="submit" disabled={busy||!prompt.trim()}>{busy?"Gerando...":"Enviar"}</button></form>
        <p className="note">{notice} Streaming SSE para OpenAI, OpenRouter, Ollama, Gemini e Anthropic quando o provedor oferece suporte.</p>
      </section>
    </main>
  </div>;
}
