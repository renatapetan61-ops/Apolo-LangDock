"use client";

import { FormEvent, useState } from "react";

type Message = { role: "user" | "assistant"; content: string };

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
  const [model, setModel] = useState("openrouter/openrouter/free");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Configure uma chave de provedor no servidor para começar a conversar.");

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const content = prompt.trim();
    if (!content || busy) return;
    const next: Message[] = [...messages, { role: "user", content }];
    setMessages(next);
    setPrompt("");
    setBusy(true);
    setNotice("Consultando o provedor selecionado...");
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(base + "/api/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages: next, temperature: 0.7, max_tokens: 1024 })
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : data.detail?.message || JSON.stringify(data.detail || data);
        throw new Error(detail);
      }
      const answer = data.choices?.[0]?.message?.content;
      if (typeof answer !== "string") throw new Error("O provedor não retornou uma resposta de texto.");
      setMessages([...next, { role: "assistant", content: answer }]);
      setNotice("Resposta recebida.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Falha ao consultar o provedor.");
    } finally {
      setBusy(false);
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
        <section className="card" style={{ marginTop: 24 }}>
          <h2 style={{ marginTop: 0 }}>Chat multimodelo</h2>
          <label htmlFor="model" style={{ color: "#9aa5bd", fontSize: 13 }}>Modelo</label>
          <select id="model" value={model} onChange={e => setModel(e.target.value)} disabled={busy} style={{ display: "block", marginTop: 8, padding: 10, background: "#090b14", color: "white", border: "1px solid #343b50", borderRadius: 8, width: "100%" }}>
            <option value="openrouter/openrouter/free">OpenRouter Free Router (cota sujeita ao provedor)</option>
            <option value="google/gemini-2.5-flash">Gemini 2.5 Flash (verifique a cota da conta)</option>
            <option value="ollama/llama3.2">Llama 3.2 via Ollama local</option>
            <option value="openai/gpt-4.1-mini">GPT-4.1 mini (chave e cobrança)</option>
            <option value="anthropic/claude-3-5-haiku-latest">Claude Haiku (chave e cobrança)</option>
          </select>
          <div aria-live="polite" style={{ display: "grid", gap: 12, marginTop: 18 }}>
            {messages.map((message, index) => <div key={index} style={{ background: message.role === "user" ? "#24203d" : "#0b0e17", border: "1px solid #242b3d", borderRadius: 12, padding: 14, whiteSpace: "pre-wrap" }}><strong style={{ display: "block", fontSize: 12, color: "#b7aaff", marginBottom: 6 }}>{message.role === "user" ? "Você" : "APOLO"}</strong>{message.content}</div>)}
          </div>
          <form className="composer" onSubmit={send}>
            <input value={prompt} onChange={e => setPrompt(e.target.value)} placeholder="Escreva uma mensagem..." disabled={busy} />
            <button type="submit" disabled={busy || !prompt.trim()}>{busy ? "Enviando..." : "Enviar"}</button>
          </form>
          <p className="note">{notice}<br/>O APOLO não cobra assinatura. Cotas gratuitas, disponibilidade e eventuais custos de inferência são definidos pelos provedores. Chaves permanecem no servidor.</p>
        </section>
      </main>
    </div>
  );
}
