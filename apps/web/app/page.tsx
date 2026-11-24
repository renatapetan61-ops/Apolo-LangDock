"use client";

import { FormEvent, useEffect, useState } from "react";

type Message = { role: "user" | "assistant"; content: string };
type Conversation = { id: string; title: string; model?: string };
type Model = { id: string; provider: string; label: string; free?: boolean | null; availability: string };
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
  const [notice,setNotice]=useState("Configure uma chave de provedor no servidor para conversar.");

  async function refreshConversations() {
    try { const r=await fetch(API+"/api/v1/conversations"); const d=await r.json(); setConversations(d.conversations||[]); }
    catch { setNotice("Não foi possível carregar o histórico."); }
  }
  useEffect(()=>{
    fetch(API+"/api/v1/models").then(r=>r.json()).then(d=>{
      const live:Model[]=d.models||[];
      if(live.length){setModels(live);setModel(live[0].id);setDiscovery(live.length+" modelos descobertos.");}
      else setDiscovery("Nenhum modelo detectado. Configure um provedor no servidor.");
    }).catch(()=>setDiscovery("Catálogo indisponível."));
    refreshConversations();
  },[]);
  async function openConversation(id:string) {
    setConversationId(id);
    const r=await fetch(API+"/api/v1/conversations/"+id+"/messages");
    const d=await r.json();
    setMessages((d.messages||[]).filter((m:Message)=>m.role==="user"||m.role==="assistant"));
  }
  async function newConversation() {
    const r=await fetch(API+"/api/v1/conversations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:"Nova conversa",model})});
    const d=await r.json(); setConversationId(d.id); setMessages([]); await refreshConversations();
  }
  async function saveMessage(id:string,message:Message) {
    await fetch(API+"/api/v1/conversations/"+id+"/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(message)});
  }
  async function send(event?:FormEvent) {
    event?.preventDefault();
    const content=prompt.trim(); if(!content||busy)return;
    setBusy(true);setPrompt("");setNotice("Recebendo resposta em tempo real...");
    let id=conversationId;
    try {
      if(!id){const r=await fetch(API+"/api/v1/conversations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:content.slice(0,70),model})});const d=await r.json();id=d.id;setConversationId(id);}
      const user:Message={role:"user",content};
      const next=[...messages,user];setMessages([...next,{role:"assistant",content:""}]);
      await saveMessage(id,user);
      const response=await fetch(API+"/api/v1/chat/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model,messages:next,temperature:0.7,max_tokens:1024})});
      if(!response.ok) { const d=await response.json(); throw new Error(typeof d.detail==="string"?d.detail:JSON.stringify(d.detail||d)); }
      if(!response.body)throw new Error("O navegador não disponibilizou o fluxo de resposta.");
      const reader=response.body.getReader();const decoder=new TextDecoder();let buffer="";let answer="";
      while(true){
        const {value,done}=await reader.read();if(done)break;
        buffer+=decoder.decode(value,{stream:true});
        const frames=buffer.split("\n\n");buffer=frames.pop()||"";
        for(const frame of frames){
          for(const line of frame.split("\n")){
            if(line.startsWith("event: error")){continue;}
            if(!line.startsWith("data:"))continue;
            const raw=line.slice(5).trim();if(raw==="[DONE]")continue;
            try{const packet=JSON.parse(raw);if(packet.error)throw new Error(packet.error);if(typeof packet.delta==="string"){answer+=packet.delta;setMessages([...next,{role:"assistant",content:answer}]);}}
            catch(e){if(e instanceof Error&&e.message!=="Unexpected end of JSON input")throw e;}
          }
        }
      }
      if(!answer)throw new Error("O provedor encerrou o fluxo sem texto.");
      await saveMessage(id,{role:"assistant",content:answer});
      setNotice("Resposta concluída e salva no histórico.");await refreshConversations();
    } catch(e) {setNotice(e instanceof Error?e.message:"Falha no chat.");}
    finally{setBusy(false);}
  }
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand">APOLO <span>LANGDOCK</span></div>
      <button className="new-chat" onClick={newConversation}>＋ Nova conversa</button>
      <div className="nav"><div className="active">◉ Chat multimodelo</div><div>✧ Modelos</div><div>◈ Agentes (API inicial)</div><div>⌘ Workflows (API inicial)</div><div>⌁ MCP & Ferramentas</div><div>⚙ Configurações</div></div>
      <h3 className="history-title">Histórico</h3>
      <div className="history">{conversations.map(c=><button key={c.id} className={conversationId===c.id?"selected":""} onClick={()=>openConversation(c.id)}>{c.title}</button>)}</div>
    </aside>
    <main>
      <div className="eyebrow">Open AI Workspace</div><h1>Seu espaço de trabalho com IA.</h1>
      <p className="sub">Converse com diferentes modelos e mantenha seu histórico salvo. Sem assinatura APOLO; cotas e preços são definidos pelos provedores.</p>
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
