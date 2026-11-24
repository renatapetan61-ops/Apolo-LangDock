"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type Model={id:string;label:string;provider:string;free?:boolean|null};
type Agent={id:string;name:string;description:string;instructions:string;model:string;tools:string[]};
type Trace={step:number;agent_id:string;model:string;status:string};

export default function AgentsPage(){
  const [token,setToken]=useState("");
  const [workspaceId,setWorkspaceId]=useState("");
  const [models,setModels]=useState<Model[]>([]);
  const [agents,setAgents]=useState<Agent[]>([]);
  const [name,setName]=useState("");
  const [description,setDescription]=useState("");
  const [instructions,setInstructions]=useState("Você é um assistente útil. Responda com precisão e clareza.");
  const [model,setModel]=useState("");
  const [prompt,setPrompt]=useState("");
  const [selected,setSelected]=useState("");
  const [output,setOutput]=useState("");
  const [trace,setTrace]=useState<Trace[]>([]);
  const [notice,setNotice]=useState("Carregando workspace...");
  const [busy,setBusy]=useState(false);
  function headers(json=false){return {...(json?{"Content-Type":"application/json"}:{}),Authorization:"Bearer "+token,"X-Workspace-ID":workspaceId};}
  async function refresh(t=token,w=workspaceId){
    if(!t||!w)return;
    const r=await fetch(API+"/api/v1/agents",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}});
    if(!r.ok)throw new Error("Não foi possível carregar agentes.");
    const d=await r.json();setAgents(d.agents||[]);
  }
  useEffect(()=>{
    const t=window.sessionStorage.getItem("apolo_access_token")||"";
    if(!t){setNotice("Entre na sua conta pela página inicial.");return;}
    setToken(t);
    Promise.all([
      fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+t}}).then(r=>r.json()),
      fetch(API+"/api/v1/models").then(r=>r.json())
    ]).then(async ([w,m])=>{
      const first=w.workspaces?.[0]?.id;
      if(!first){setNotice("Crie um workspace na página inicial.");return;}
      setWorkspaceId(first);setModels(m.models||[]);
      if(m.models?.length)setModel(m.models[0].id);
      await refresh(t,first);setNotice("Construtor de agentes pronto.");
    }).catch(e=>setNotice(e.message||"Falha ao inicializar."));
  },[]);
  async function save(e:FormEvent){
    e.preventDefault();if(!name.trim()||!model)return;
    setBusy(true);
    try{
      const r=await fetch(API+"/api/v1/agents",{method:"POST",headers:headers(true),body:JSON.stringify({name,description,instructions,model,tools:[]})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao salvar agente.");
      setName("");setDescription("");await refresh();setSelected(d.id);setNotice("Agente salvo no workspace.");
    }catch(e){setNotice(e instanceof Error?e.message:"Falha ao salvar.");}
    finally{setBusy(false);}
  }
  async function run(e:FormEvent){
    e.preventDefault();if(!selected||!prompt.trim())return;
    setBusy(true);setOutput("");setTrace([]);
    try{
      const r=await fetch(API+"/api/v1/agents/"+selected+"/run",{method:"POST",headers:headers(true),body:JSON.stringify({prompt})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha na execução.");
      setOutput(d.output||"");setTrace(d.trace||[]);setNotice("Execução concluída.");
    }catch(e){setNotice(e instanceof Error?e.message:"Falha na execução.");}
    finally{setBusy(false);}
  }
  async function orchestrate(){
    if(!prompt.trim()||agents.length<2)return;
    setBusy(true);setOutput("");setTrace([]);
    try{
      const ids=agents.slice(0,5).map(a=>a.id);
      const r=await fetch(API+"/api/v1/agents/orchestrate",{method:"POST",headers:headers(true),body:JSON.stringify({agent_ids:ids,prompt,max_steps:Math.min(ids.length,5)})});
      const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha na orquestração.");
      setOutput(d.output||"");setTrace(d.trace||[]);setNotice("Orquestração concluída.");
    }catch(e){setNotice(e instanceof Error?e.message:"Falha na orquestração.");}
    finally{setBusy(false);}
  }
  return <main className="tool-page">
    <header className="tool-header"><div><div className="eyebrow">APOLO LANGDOCK / AGENTS</div><h1>Construtor de agentes</h1><p className="sub">Configure instruções e modelos; execute agentes individualmente ou em uma cadeia limitada de até cinco etapas.</p></div><Link href="/">Voltar ao chat</Link></header>
    {!token?<section className="card"><p>{notice}</p><Link href="/">Ir para login</Link></section>:<div className="agent-grid">
      <section className="card tool-card"><h2>Novo agente</h2><form className="tool-form" onSubmit={save}>
        <label>Nome<input value={name} onChange={e=>setName(e.target.value)} required maxLength={100}/></label>
        <label>Descrição<input value={description} onChange={e=>setDescription(e.target.value)} maxLength={1000}/></label>
        <label>Instruções do sistema<textarea value={instructions} onChange={e=>setInstructions(e.target.value)} rows={7} maxLength={12000}/></label>
        <label>Modelo<select value={model} onChange={e=>setModel(e.target.value)} required><option value="">Selecione um modelo</option>{models.map(m=><option key={m.id} value={m.id}>{m.label} · {m.provider}{m.free===true?" · local/gratuito":""}</option>)}</select></label>
        <p className="note">Ferramentas externas ficam desativadas nesta versão até existir allowlist, aprovação e sandbox.</p>
        <button disabled={busy||!model}>{busy?"Salvando...":"Salvar agente"}</button>
      </form></section>
      <section className="card tool-card"><h2>Agentes do workspace</h2><div className="agent-list">{agents.map(a=><button key={a.id} className={selected===a.id?"selected":""} onClick={()=>setSelected(a.id)}><strong>{a.name}</strong><span>{a.model||"Sem modelo"}</span><small>{a.description}</small></button>)}</div>
        <form className="tool-form" onSubmit={run}><label>Agente selecionado<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Selecione</option>{agents.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>Tarefa<textarea rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Descreva a tarefa..." required/></label><button disabled={busy||!selected}>Executar agente</button><button type="button" className="secondary-button" disabled={busy||agents.length<2||!prompt.trim()} onClick={orchestrate}>Orquestrar até 5 agentes</button></form>
      </section>
      <section className="card tool-card output-card"><h2>Resultado e rastreamento</h2><p className="note">{notice}</p>{trace.map(t=><div className="trace-row" key={t.step}><span>Etapa {t.step}</span><code>{t.agent_id.slice(0,8)}</code><strong>{t.status}</strong></div>)}{output&&<pre>{output}</pre>}</section>
    </div>}
  </main>;
}
