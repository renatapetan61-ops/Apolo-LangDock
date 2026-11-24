"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type KeyItem={id:string;name:string;key_prefix:string;scopes:string[];expires_at:string|null;revoked_at:string|null;created_at:string;last_used_at:string|null};
type Audit={id:string;action:string;resource_type:string;resource_id:string|null;details:Record<string,unknown>;created_at:string};

export default function APIKeysPage(){
 const [token,setToken]=useState("");const [workspaceId,setWorkspaceId]=useState("");
 const [keys,setKeys]=useState<KeyItem[]>([]);const [events,setEvents]=useState<Audit[]>([]);
 const [name,setName]=useState("");const [readScope,setReadScope]=useState(true);const [chatScope,setChatScope]=useState(true);
 const [expires,setExpires]=useState("90");const [createdKey,setCreatedKey]=useState("");
 const [notice,setNotice]=useState("Carregando chaves...");const [busy,setBusy]=useState(false);
 function headers(json=false){return {...(json?{"Content-Type":"application/json"}:{}),Authorization:"Bearer "+token,"X-Workspace-ID":workspaceId};}
 async function refresh(t=token,w=workspaceId){
  if(!t||!w)return;
  const [kr,ar]=await Promise.all([
   fetch(API+"/api/v1/api-keys",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}}),
   fetch(API+"/api/v1/audit-logs",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}})
  ]);
  if(!kr.ok||!ar.ok)throw new Error("Falha ao carregar chaves ou auditoria.");
  const kd=await kr.json(),ad=await ar.json();setKeys(kd.api_keys||[]);setEvents(ad.events||[]);
 }
 useEffect(()=>{
  const t=window.sessionStorage.getItem("apolo_access_token")||"";
  if(!t){setNotice("Entre pela página inicial para gerenciar as chaves.");return;}
  setToken(t);
  fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+t}}).then(r=>r.json()).then(async d=>{
   const first=d.workspaces?.[0]?.id;if(!first){setNotice("Crie um workspace na página inicial.");return;}
   setWorkspaceId(first);await refresh(t,first);setNotice("Gerenciamento de API keys pronto.");
  }).catch(e=>setNotice(e.message||"Falha ao inicializar."));
 },[]);
 async function createKey(){
  const scopes=[...(readScope?["models:read"]:[]),...(chatScope?["chat:completions"]:[])];
  if(!name.trim()||!scopes.length)return;setBusy(true);setCreatedKey("");
  try{
   const r=await fetch(API+"/api/v1/api-keys",{method:"POST",headers:headers(true),body:JSON.stringify({name,scopes,expires_in_days:Number(expires)})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao criar chave.");
   setCreatedKey(d.api_key);setName("");await refresh();setNotice("Chave criada. Copie agora: ela não será exibida novamente.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao criar chave.");}
  finally{setBusy(false);}
 }
 async function revoke(item:KeyItem){
  if(!window.confirm("Revogar a chave "+item.name+"? A integração deixará de funcionar."))return;
  setBusy(true);
  try{
   const r=await fetch(API+"/api/v1/api-keys/"+item.id,{method:"DELETE",headers:headers()});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao revogar.");
   await refresh();setNotice("Chave revogada.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao revogar.");}
  finally{setBusy(false);}
 }
 return <main className="tool-page">
  <header className="tool-header"><div><div className="eyebrow">APOLO LANGDOCK / DEVELOPER API</div><h1>Chaves e API pública</h1><p className="sub">Crie credenciais por workspace, limite escopos e revogue acessos sem expor segredos.</p></div><Link href="/">Voltar ao chat</Link></header>
  {!token?<section className="card"><p>{notice}</p><Link href="/">Ir para login</Link></section>:<div className="api-key-layout">
   <section className="card api-key-card"><h2>Criar chave de API</h2><div className="tool-form">
    <label>Nome da integração<input value={name} onChange={e=>setName(e.target.value)} maxLength={100} placeholder="Ex.: Meu aplicativo"/></label>
    <label>Validade<select value={expires} onChange={e=>setExpires(e.target.value)}><option value="30">30 dias</option><option value="90">90 dias</option><option value="180">180 dias</option><option value="365">365 dias</option></select></label>
    <label className="scope-check"><input type="checkbox" checked={readScope} onChange={e=>setReadScope(e.target.checked)}/> models:read — consultar catálogo de modelos</label>
    <label className="scope-check"><input type="checkbox" checked={chatScope} onChange={e=>setChatScope(e.target.checked)}/> chat:completions — gerar respostas</label>
    <button disabled={busy||!name.trim()||(!readScope&&!chatScope)} onClick={createKey}>Criar chave</button>
   </div>
   {createdKey&&<div className="new-api-key"><strong>Copie sua chave agora</strong><code>{createdKey}</code><button onClick={()=>navigator.clipboard.writeText(createdKey)}>Copiar chave</button><p className="note">Por segurança, a chave completa não será mostrada novamente. Guarde-a em um gerenciador de segredos.</p></div>}
   <h2>Uso da API</h2><pre className="api-example">curl https://SEU_HOST/api/v1/public/chat/completions \\n  -H "X-API-Key: apolo_sk_SUA_CHAVE" \\n  -H "Content-Type: application/json" \\n  -d '{"model":"ollama/llama3.2","messages":[{"role":"user","content":"Olá"}]}'</pre>
   <p className="note">Limite inicial: 60 chamadas por minuto por chave (configurável no servidor por APOLO_API_KEY_RPM, máximo 600). Custos e limites de inferência continuam pertencendo ao provedor do modelo.</p>
   </section>
   <section className="card api-key-card"><h2>Chaves deste workspace</h2><div className="api-key-list">{keys.map(k=><article key={k.id}><div><strong>{k.name}</strong><code>{k.key_prefix}••••••••</code><small>Escopos: {k.scopes.join(", ")}</small><small>Expira: {k.expires_at?new Date(k.expires_at).toLocaleString():"sem expiração"}</small><small>Último uso: {k.last_used_at?new Date(k.last_used_at).toLocaleString():"nunca"}</small></div>{k.revoked_at?<span className="revoked">Revogada</span>:<button className="revoke-key" disabled={busy} onClick={()=>revoke(k)}>Revogar</button>}</article>)}</div>
   </section>
   <section className="card api-key-card audit-card"><h2>Auditoria recente</h2><div className="audit-list">{events.slice(0,30).map(e=><article key={e.id}><strong>{e.action}</strong><small>{e.resource_type}{e.resource_id?" · "+e.resource_id.slice(0,8):""}</small><time>{new Date(e.created_at).toLocaleString()}</time></article>)}</div><p className="note">{notice}</p></section>
  </div>}
 </main>;
}
