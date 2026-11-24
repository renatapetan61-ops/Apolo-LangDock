"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type Kind="input"|"prompt"|"model"|"output";
type Node={id:string;type:Kind;label:string;config:Record<string,string>};
type Workflow={id:string;name:string;description:string;definition:{nodes:Node[];edges:{source:string;target:string}[]}};
type Model={id:string;label:string;provider:string};
const initialNodes:Node[]=[
 {id:"input",type:"input",label:"Entrada",config:{}},
 {id:"prompt",type:"prompt",label:"Instruções",config:{instructions:"Analise a entrada e prepare uma resposta clara."}},
 {id:"model",type:"model",label:"Modelo de IA",config:{model:""}},
 {id:"output",type:"output",label:"Saída",config:{}}
];
const labels:Record<Kind,string>={input:"Entrada",prompt:"Prompt",model:"Modelo IA",output:"Saída"};

export default function WorkflowsPage(){
 const [token,setToken]=useState("");const [workspaceId,setWorkspaceId]=useState("");
 const [models,setModels]=useState<Model[]>([]);const [workflows,setWorkflows]=useState<Workflow[]>([]);
 const [nodes,setNodes]=useState<Node[]>(initialNodes);const [name,setName]=useState("Meu workflow");
 const [input,setInput]=useState("");const [workflowId,setWorkflowId]=useState("");
 const [output,setOutput]=useState("");const [trace,setTrace]=useState<{node_id:string;type:string;status:string}[]>([]);
 const [notice,setNotice]=useState("Carregando editor...");const [busy,setBusy]=useState(false);
 function headers(json=false){return {...(json?{"Content-Type":"application/json"}:{}),Authorization:"Bearer "+token,"X-Workspace-ID":workspaceId};}
 function edgesFor(list:Node[]){return list.slice(1).map((node,i)=>({source:list[i].id,target:node.id}));}
 async function refresh(t=token,w=workspaceId){
  const r=await fetch(API+"/api/v1/workflows",{headers:{Authorization:"Bearer "+t,"X-Workspace-ID":w}});
  if(!r.ok)throw new Error("Falha ao carregar workflows.");
  setWorkflows((await r.json()).workflows||[]);
 }
 useEffect(()=>{
  const t=window.sessionStorage.getItem("apolo_access_token")||"";
  if(!t){setNotice("Entre pela página inicial para abrir o editor.");return;}
  setToken(t);
  Promise.all([
   fetch(API+"/api/v1/workspaces",{headers:{Authorization:"Bearer "+t}}).then(r=>r.json()),
   fetch(API+"/api/v1/models").then(r=>r.json())
  ]).then(async([w,m])=>{
   const first=w.workspaces?.[0]?.id;if(!first){setNotice("Crie um workspace na página inicial.");return;}
   setWorkspaceId(first);const found:Model[]=m.models||[];setModels(found);
   if(found.length)setNodes(current=>current.map(n=>n.type==="model"?{...n,config:{...n.config,model:found[0].id}}:n));
   await refresh(t,first);setNotice("Editor visual pronto.");
  }).catch(e=>setNotice(e.message||"Falha ao inicializar."));
 },[]);
 function addNode(type:"prompt"|"model"){
  setNodes(current=>{
   const outputIndex=current.findIndex(n=>n.type==="output");
   const node:Node={id:window.crypto.randomUUID(),type,label:labels[type],config:type==="prompt"?{instructions:"Descreva a transformação desejada."}:{model:models[0]?.id||""}};
   return [...current.slice(0,outputIndex),node,...current.slice(outputIndex)];
  });
 }
 function removeNode(id:string){setNodes(current=>current.filter(n=>n.id!==id||n.type==="input"||n.type==="output"));}
 function updateNode(id:string,key:string,value:string){setNodes(current=>current.map(n=>n.id===id?{...n,config:{...n.config,[key]:value}}:n));}
 async function save(){
  if(!name.trim())return;setBusy(true);
  try{
   const definition={nodes,edges:edgesFor(nodes)};
   const r=await fetch(API+"/api/v1/workflows",{method:"POST",headers:headers(true),body:JSON.stringify({id:workflowId||undefined,name,description:"Workflow visual APOLO",definition})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha ao salvar workflow.");
   setWorkflowId(d.id);await refresh();setNotice("Workflow salvo no workspace.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha ao salvar.");}
  finally{setBusy(false);}
 }
 async function run(){
  if(!workflowId){setNotice("Salve o workflow antes de executar.");return;}
  if(!input.trim())return;setBusy(true);setOutput("");setTrace([]);
  try{
   const r=await fetch(API+"/api/v1/workflows/"+workflowId+"/run",{method:"POST",headers:headers(true),body:JSON.stringify({input})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Falha na execução.");
   setOutput(d.output||"");setTrace(d.trace||[]);setNotice("Workflow executado com sucesso.");
  }catch(e){setNotice(e instanceof Error?e.message:"Falha na execução.");}
  finally{setBusy(false);}
 }
 function load(item:Workflow){
  setWorkflowId(item.id);setName(item.name);setNodes(item.definition?.nodes||initialNodes);setOutput("");setTrace([]);setNotice("Workflow carregado para edição.");
 }
 return <main className="tool-page">
  <header className="tool-header"><div><div className="eyebrow">APOLO LANGDOCK / WORKFLOWS</div><h1>Editor visual de workflows</h1><p className="sub">Monte um fluxo linear com entrada, instruções, modelos de IA e saída. A execução valida o grafo e limita o tamanho.</p></div><Link href="/">Voltar ao chat</Link></header>
  {!token?<section className="card"><p>{notice}</p><Link href="/">Ir para login</Link></section>:<div className="workflow-layout">
   <section className="card workflow-editor">
    <div className="workflow-toolbar"><label>Nome do workflow<input value={name} onChange={e=>setName(e.target.value)} maxLength={120}/></label><div><button onClick={()=>addNode("prompt")} disabled={busy}>＋ Prompt</button><button onClick={()=>addNode("model")} disabled={busy}>＋ Modelo</button><button onClick={save} disabled={busy}>{busy?"Aguarde...":"Salvar fluxo"}</button></div></div>
    <div className="node-canvas">{nodes.map((node,index)=><div className="node-wrap" key={node.id}>
      <article className={"workflow-node "+node.type}><div className="node-top"><span>{index+1}. {labels[node.type]}</span>{node.type!=="input"&&node.type!=="output"&&<button onClick={()=>removeNode(node.id)} aria-label="Remover nó">×</button>}</div>
       {node.type==="input"&&<p>Recebe o texto enviado ao executar o workflow.</p>}
       {node.type==="prompt"&&<label>Instruções<textarea rows={3} value={node.config.instructions||""} onChange={e=>updateNode(node.id,"instructions",e.target.value)}/></label>}
       {node.type==="model"&&<label>Modelo<select value={node.config.model||""} onChange={e=>updateNode(node.id,"model",e.target.value)}><option value="">Selecione um modelo</option>{models.map(m=><option key={m.id} value={m.id}>{m.label} · {m.provider}</option>)}</select></label>}
       {node.type==="output"&&<p>Retorna o resultado produzido pelos nós anteriores.</p>}
      </article>{index<nodes.length-1&&<div className="node-connector">↓</div>}
    </div>)}</div>
    <p className="note">Conexões sequenciais automáticas. Tipos suportados: input, prompt, model e output. Ferramentas externas e ciclos são bloqueados.</p>
   </section>
   <aside className="card workflow-side"><h2>Workflows salvos</h2><div className="saved-workflows">{workflows.map(w=><button key={w.id} className={workflowId===w.id?"selected":""} onClick={()=>load(w)}><strong>{w.name}</strong><small>{w.definition?.nodes?.length||0} nós</small></button>)}</div><h2>Executar</h2><label>Entrada<textarea rows={5} value={input} onChange={e=>setInput(e.target.value)} placeholder="Texto de entrada..." /></label><button onClick={run} disabled={busy||!workflowId||!input.trim()}>Executar workflow</button><p className="note">{notice}</p></aside>
   <section className="card workflow-result"><h2>Execução e rastreamento</h2>{trace.map((t,i)=><div className="trace-row" key={t.node_id}><span>{i+1}. {t.type}</span><code>{t.node_id.slice(0,8)}</code><strong>{t.status}</strong></div>)}{output&&<pre>{output}</pre>}</section>
  </div>}
 </main>;
}
