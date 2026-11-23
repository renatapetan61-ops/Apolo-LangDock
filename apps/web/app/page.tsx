"use client";

import { useState } from "react";

const modules = [
  ["Modelos de IA", "Catálogo unificado de provedores, seleção de modelos e cotas gratuitas."],
  ["Agentes", "Agentes configuráveis com instruções, ferramentas e permissões explícitas."],
  ["Workflows", "Automação visual com etapas, condições e execução rastreável."],
  ["MCP", "Conexão com servidores e ferramentas pelo Model Context Protocol."],
  ["API", "Endpoints compatíveis com padrões conhecidos para integrar aplicações."],
  ["Conhecimento", "Preparação para documentos, busca semântica e RAG."]
];

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [notice, setNotice] = useState("O chat real será habilitado após a integração dos provedores no backend.");

  async function send() {
    if (!prompt.trim()) return;
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(base + "/api/v1/models");
      if (!response.ok) throw new Error("API indisponível");
      setNotice("API conectada. O adaptador de inferência ainda está em implementação; nenhuma resposta fictícia será exibida.");
    } catch {
      setNotice("Não foi possível conectar à API. Verifique se o backend está em execução.");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">APOLO <span>LANGDOCK</span></div>
        <div className="nav">
          <div className="active">⌂ Visão geral</div>
          <div>◉ Chat</div><div>✧ Modelos</div><div>◈ Agentes</div>
          <div>⌘ Workflows</div><div>⌁ MCP & Ferramentas</div><div>⚙ Configurações</div>
        </div>
      </aside>
      <main>
        <div className="eyebrow">Open AI Workspace</div>
        <h1>Seu espaço de trabalho com IA.</h1>
        <p className="sub">Um único ambiente para conversar com diferentes modelos, criar agentes, automatizar tarefas e conectar ferramentas. Código aberto, sem assinatura APOLO.</p>
        <section className="grid">
          {modules.map(([title, description]) => <article className="card" key={title}><h3>{title}</h3><p>{description}</p><div className="status">● Fundação em construção</div></article>)}
        </section>
        <div className="composer">
          <input value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Descreva uma tarefa para sua IA..." onKeyDown={e => { if (e.key === "Enter") void send(); }} />
          <button onClick={() => void send()}>Testar API</button>
        </div>
        <p className="note">{notice}<br/>Modelos comerciais podem exigir chave própria e cobrança do provedor. Apenas cotas gratuitas oficiais ou modelos locais serão identificados como gratuitos.</p>
      </main>
    </div>
  );
}
