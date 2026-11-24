"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type Server={id:string;name:string;transport:string;endpoint?:string;config_key?:string};
type Tool={name:string;description:string;input_schema:Record<string,unknown>;approved:boolean};

export default function MCPPage(){
 const [token,setToken]=useState("");const [workspaceId,setWorkspaceId]=useState("");
 const [servers,setServers]=useState<Server[]>([]);const [tools,setTools]=useState<Tool[]>([]);
 const [name,setName]=useState("");const [transport,setTransport]=useState("streamable-http");
 const [endpoint,setEndpoint]=useState("");const [configKey,setConfigKey]=useState("");
 const [selected,setSelected]=useState("");const [selectedTool,setSelectedTool]=useState("");
 const [args,setArgs]=useState("{}");const [result,setResult]=useState("");
 const [notice,setNotice]=useState("Carregando integração MCP...");const [busy,setBusy]=useState(false);
 function headers(json=false){return {...(json?{"Content-Type":"application/json"}:{}),Authorization:"Bearer "+token,"X-Workspace-ID":workspaceId};}
 async function refreshServers(t=token,w=workspaceId){
  if(!t||!w)return;
  const r=await fetch(API+"/api/v1/mcp/servers",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}});
  if(!r.ok)throw new Error("Falha ao carregar servidores MCP.");
  const d=await r.json();setServers(d.servers||[]);
 }
 async function refreshTools(serverId=selected){
  if(!serverId)return;
  const r=await fetch(API+"/api/v1/mcp/servers/"+serverId+"/tools",{headers:headers()});
  if(!r.ok)throw new Error("Falha ao carregar ferramentas.");
  const d=await r.json();setTools(d.tools||[]);
 }
 useEffect(()=>{
  const t=window.sessionStorage.getItem("apolo_access_token")||"";
  if(!t){setNotice("Entre pela página inicial para gerenciar servidores MCP.");return;}
  setToken(t);
  fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+t}}).then(r=>r.json()).then(async d=>{
   const first=d.workspaces?.[0]?.id;if(!first){setNotice("Crie um workspace na página inicial.");return;}
   setWorkspaceId(first);await refreshServers(t,first);setNotice("MCP pronto. Servidores e ferramentas pertencem ao workspace.");
  }).catch(e=>setNotice(e.message||"Falha ao inicializar."));
 },[]);
 async function register(){
  if(!name.trim())return;setBusy(true);
  try{
   const body=transport==="streamable-http"?{name,transport,endpoint}:{name,transport,config_key:configKey};
   const r=await fetch(API+"/api/v1/mcp/servers",{method:"POST",headers:headers(true),body:JSON.stringify(body)});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao registrar servidor.");
   setName("");setEndpoint("");setConfigKey("");setSelected(d.id);await refreshServers();setTools([]);setNotice("Servidor registrado. Faça a descoberta de ferramentas.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao registrar.");}
  finally{setBusy(false);}
 }
 async function discover(serverId=selected){
  if(!serverId)return;setBusy(true);setResult("");
  try{
   const r=await fetch(API+"/api/v1/mcp/servers/"+serverId+"/discover",{method:"POST",headers:headers()});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha na descoberta.");
   setSelected(serverId);setTools(d.tools||[]);setSelectedTool("");setNotice("Descoberta concluída. Todas as ferramentas começam sem aprovação.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha na descoberta.");}
  finally{setBusy(false);}
 }
 async function approval(tool:Tool,approved:boolean){
  setBusy(true);
  try{
   const r=await fetch(API+"/api/v1/mcp/servers/"+selected+"/tools/"+encodeURIComponent(tool.name)+"/approval",{method:"POST",headers:headers(true),body:JSON.stringify({approved})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao atualizar aprovação.");
   setTools(current=>current.map(t=>t.name===tool.name?{...t,approved}:t));
   setNotice(approved?"Ferramenta aprovada neste workspace.":"Aprovação revogada.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha na aprovação.");}
  finally{setBusy(false);}
 }
 async function callTool(){
  if(!selected||!selectedTool)return;setBusy(true);setResult("");
  try{
   const parsed=JSON.parse(args);if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))throw new Error("Argumentos precisam ser um objeto JSON.");
   const r=await fetch(API+"/api/v1/mcp/servers/"+selected+"/tools/"+encodeURIComponent(selectedTool)+"/call",{method:"POST",headers:headers(true),body:JSON.stringify({arguments:parsed})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao chamar ferramenta.");
   setResult(JSON.stringify(d,null,2));setNotice(d.is_error?"A ferramenta retornou erro.":"Chamada MCP concluída.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha na chamada.");}
  finally{setBusy(false);}
 }
 async function removeServer(serverId:string){
  if(!window.confirm("Remover este servidor e suas aprovações?"))return;
  const r=await fetch(API+"/api/v1/mcp/servers/"+serverId,{method:"DELETE",headers:headers()});
  if(!r.ok){setNotice("Não foi possível remover o servidor.");return;}
  if(selected===serverId){setSelected("");setTools([]);setSelectedTool("");}
  await refreshServers();setNotice("Servidor removido e aprovações excluídas.");
 }
 const activeTool=tools.find(t=>t.name===selectedTool);
 return <main className="tool-page">
  <header className="tool-header"><div><div className="eyebrow">APOLO LANGDOCK / MCP</div><h1>Cliente MCP</h1><p className="sub">Registre servidores, descubra ferramentas e aprove cada ferramenta antes de executar.</p></div><Link href="/">Voltar ao chat</Link></header>
  {!token?<section className="card"><p>{notice}</p><Link href="/">Ir para login</Link></section>:<div className="mcp-layout">
   <section className="card mcp-card"><h2>Adicionar servidor</h2><div className="tool-form">
    <label>Nome<input value={name} onChange={e=>setName(e.target.value)} maxLength={100}/></label>
    <label>Transporte<select value={transport} onChange={e=>setTransport(e.target.value)}><option value="streamable-http">Streamable HTTP (remoto)</option><option value="stdio">stdio (alias do administrador)</option></select></label>
    {transport==="streamable-http"?<label>Endpoint HTTPS<input value={endpoint} onChange={e=>setEndpoint(e.target.value)} placeholder="https://servidor-autorizado.example/mcp"/></label>:<label>Alias configurado pelo administrador<input value={configKey} onChange={e=>setConfigKey(e.target.value)} placeholder="ex.: apolo-local-tools"/></label>}
    <p className="note">Hosts HTTP precisam estar em MCP_ALLOWED_HOSTS. Processos stdio só podem usar aliases definidos no servidor; o navegador não envia comandos.</p>
    <button disabled={busy||!name.trim()||(transport==="streamable-http"?!endpoint.trim():!configKey.trim())} onClick={register}>Registrar servidor</button>
   </div><h2>Servidores deste workspace</h2><div className="mcp-server-list">{servers.map(s=><div className={selected===s.id?"active":""} key={s.id}><button className="server-select" onClick={()=>{setSelected(s.id);refreshTools(s.id).catch(e=>setNotice(e.message));}}><strong>{s.name}</strong><small>{s.transport} · {s.endpoint||s.config_key}</small></button><button className="danger-link" onClick={()=>removeServer(s.id)}>Remover</button></div>)}</div></section>
   <section className="card mcp-card"><div className="mcp-toolbar"><h2>Ferramentas descobertas</h2><button disabled={busy||!selected} onClick={()=>discover()}>Descobrir ferramentas</button></div>
    {!selected?<p className="note">Selecione um servidor para ver as ferramentas.</p>:!tools.length?<p className="note">Nenhuma ferramenta carregada. Execute a descoberta.</p>:<div className="mcp-tool-list">{tools.map(t=><article key={t.name} className={selectedTool===t.name?"active":""}><button className="tool-select" onClick={()=>{setSelectedTool(t.name);setArgs("{}");}}><strong>{t.name}</strong><small>{t.description||"Sem descrição"}</small></button><label className="approval"><input type="checkbox" checked={t.approved} disabled={busy} onChange={e=>approval(t,e.target.checked)}/> Aprovada</label></article>)}</div>}
    <div className="mcp-call"><h3>Executar ferramenta aprovada</h3><p className="note">{activeTool?activeTool.description:"Selecione uma ferramenta na lista."}</p><label>Argumentos JSON<textarea rows={6} value={args} onChange={e=>setArgs(e.target.value)} spellCheck={false}/></label><button disabled={busy||!activeTool||!activeTool.approved} onClick={callTool}>Executar chamada MCP</button></div>
   </section>
   <section className="card mcp-result"><h2>Resultado</h2><p className="note">{notice}</p>{result&&<pre>{result}</pre>}</section>
  </div>}
 </main>;
}
