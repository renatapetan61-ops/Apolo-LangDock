"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const EVENTS = ["api_key.created", "api_key.revoked", "usage.recorded", "mcp.tool.called", "test.ping"];
type Hook = {id:string;name:string;url:string;events:string[];active:boolean;created_at:string};
type Delivery = {id:string;event_type:string;status_code:number|null;response_excerpt:string|null;attempts:number;next_attempt_at:string|null;delivered_at:string|null;created_at:string};

export default function WebhooksPage(){
 const [token,setToken]=useState("");const [workspaceId,setWorkspaceId]=useState("");
 const [hooks,setHooks]=useState<Hook[]>([]);const [selected,setSelected]=useState("");
 const [deliveries,setDeliveries]=useState<Delivery[]>([]);
 const [name,setName]=useState("");const [url,setUrl]=useState("");const [secret,setSecret]=useState("");
 const [events,setEvents]=useState<string[]>(["usage.recorded"]);
 const [notice,setNotice]=useState("Carregando webhooks...");const [busy,setBusy]=useState(false);
 function headers(json=false){return {...(json?{"Content-Type":"application/json"}:{}),Authorization:"Bearer "+token,"X-Workspace-ID":workspaceId};}
 async function load(t=token,w=workspaceId){
  if(!t||!w)return;
  const r=await fetch(API+"/api/v1/webhooks",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}});
  const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao carregar webhooks.");
  setHooks(d.webhooks||[]);
 }
 async function loadDeliveries(id=selected){
  if(!id)return;
  const r=await fetch(API+"/api/v1/webhooks/"+id+"/deliveries",{headers:headers()});
  const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao carregar entregas.");
  setDeliveries(d.deliveries||[]);
 }
 useEffect(()=>{
  const t=window.sessionStorage.getItem("apolo_access_token")||"";
  if(!t){setNotice("Entre pela página inicial para gerenciar webhooks.");return;}
  setToken(t);
  fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+t}}).then(r=>r.json()).then(async d=>{
   const w=d.workspaces?.[0]?.id;if(!w){setNotice("Crie um workspace na página inicial.");return;}
   setWorkspaceId(w);await load(t,w);setNotice("Webhooks do workspace carregados.");
  }).catch(e=>setNotice(e.message||"Falha ao inicializar."));
 },[]);
 function toggleEvent(event:string,checked:boolean){setEvents(current=>checked?[...current,event]:current.filter(item=>item!==event));}
 async function create(){
  setBusy(true);
  try{
   const r=await fetch(API+"/api/v1/webhooks",{method:"POST",headers:headers(true),body:JSON.stringify({name,url,secret,events})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao criar webhook.");
   setName("");setUrl("");setSecret("");setEvents(["usage.recorded"]);setSelected(d.id);
   await load();await loadDeliveries(d.id);setNotice("Webhook criado. O segredo não será exibido novamente.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao criar webhook.");}
  finally{setBusy(false);}
 }
 async function test(id=selected){
  if(!id)return;setBusy(true);
  try{
   const r=await fetch(API+"/api/v1/webhooks/"+id+"/test",{method:"POST",headers:headers()});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha no teste.");
   setSelected(id);await loadDeliveries(id);setNotice(d.delivered?"Entrega de teste confirmada.":"Teste enfileirado para retentativa; consulte o histórico.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha no teste.");}
  finally{setBusy(false);}
 }
 async function remove(id:string){
  if(!window.confirm("Excluir este webhook e seu histórico de entregas?"))return;
  setBusy(true);
  try{
   const r=await fetch(API+"/api/v1/webhooks/"+id,{method:"DELETE",headers:headers()});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao excluir.");
   if(selected===id){setSelected("");setDeliveries([]);}
   await load();setNotice("Webhook e histórico removidos.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao excluir.");}
  finally{setBusy(false);}
 }
 const active=hooks.find(h=>h.id===selected);
 return <main className="tool-page">
  <header className="tool-header"><div><div className="eyebrow">APOLO LANGDOCK / INTEGRAÇÕES</div><h1>Webhooks</h1><p className="sub">Receba eventos assinados do workspace e acompanhe as entregas e retentativas.</p></div><Link href="/">Voltar ao chat</Link></header>
  {!token?<section className="card"><p>{notice}</p><Link href="/">Ir para login</Link></section>:<div className="mcp-layout">
   <section className="card mcp-card"><h2>Novo endpoint</h2><div className="tool-form">
    <label>Nome<input value={name} onChange={e=>setName(e.target.value)} maxLength={100} placeholder="Ex.: automação de deploy"/></label>
    <label>URL HTTPS<input type="url" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://hooks.example.com/apolo"/></label>
    <label>Segredo HMAC<input type="password" autoComplete="new-password" value={secret} onChange={e=>setSecret(e.target.value)} minLength={24} placeholder="Use um segredo aleatório com pelo menos 24 caracteres"/></label>
    <div><strong>Eventos</strong>{EVENTS.map(event=><label className="approval" key={event}><input type="checkbox" checked={events.includes(event)} onChange={e=>toggleEvent(event,e.target.checked)}/>{event}</label>)}</div>
    <p className="note">O destino deve usar HTTPS na porta 443 e hostname presente em WEBHOOK_ALLOWED_HOSTS. O segredo é criptografado e nunca retornado pela API.</p>
    <button disabled={busy||!name.trim()||!url.trim()||secret.length<24||!events.length} onClick={create}>Criar webhook</button>
   </div><h2>Endpoints deste workspace</h2><div className="mcp-server-list">{hooks.map(h=><div className={selected===h.id?"active":""} key={h.id}><button className="server-select" onClick={()=>{setSelected(h.id);loadDeliveries(h.id).catch(e=>setNotice(e.message));}}><strong>{h.name}</strong><small>{h.url} · {h.events.join(", ")}</small></button><button className="danger-link" disabled={busy} onClick={()=>remove(h.id)}>Excluir</button></div>)}</div></section>
   <section className="card mcp-card"><div className="mcp-toolbar"><h2>Entregas</h2><div><button disabled={busy||!selected} onClick={()=>test()}>Enviar teste</button><button className="secondary-button" disabled={busy||!selected} onClick={()=>loadDeliveries().then(()=>setNotice("Histórico atualizado.")).catch(e=>setNotice(e.message))}>Atualizar</button></div></div>
    <p className="note">{notice}</p>{!selected?<p className="note">Selecione um webhook para ver o histórico.</p>:<><p className="note">{active?.events.join(" · ")}</p><div className="mcp-tool-list">{deliveries.map(d=><article key={d.id}><div><strong>{d.event_type}</strong><small>ID {d.id} · tentativas: {d.attempts} · HTTP {d.status_code??"sem resposta"}</small><small>{d.delivered_at?"Entregue em "+d.delivered_at:d.next_attempt_at?"Próxima tentativa: "+d.next_attempt_at:"Sem próxima tentativa — revisar ou reprocessar"}</small>{d.response_excerpt&&<small>{d.response_excerpt}</small>}</div><span className="approval">{d.delivered_at?"Entregue":d.next_attempt_at?"Pendente":"Esgotada"}</span></article>)}</div></>}
   </section>
  </div>}
 </main>;
}
