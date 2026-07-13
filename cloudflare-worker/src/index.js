const jsonHeaders = {
  "content-type": "application/json; charset=utf-8",
};

function cors(env) {
  return {
    "access-control-allow-origin": env.ALLOWED_ORIGIN || "*",
    "access-control-allow-headers": "authorization, content-type, x-user-id",
    "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...jsonHeaders, ...cors(env) },
  });
}

function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  return Boolean(env.BRIDGE_API_KEY) && header === `Bearer ${env.BRIDGE_API_KEY}`;
}

function userId(request) {
  return (request.headers.get("x-user-id") || "default").slice(0, 128);
}

function uuid() {
  return crypto.randomUUID();
}

function now() {
  return new Date().toISOString();
}

async function bodyJson(request) {
  try {
    return await request.json();
  } catch {
    throw new Error("Request body must be valid JSON");
  }
}

function outputText(response) {
  if (typeof response.output_text === "string") return response.output_text;
  return (response.output || [])
    .flatMap((item) => item.content || [])
    .filter((item) => item.type === "output_text" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n");
}

async function callOpenAI(env, messages, useWebSearch) {
  if (!env.OPENAI_API_KEY) throw new Error("OPENAI_API_KEY is not configured");
  const payload = {
    model: env.OPENAI_MODEL || "gpt-5.4-mini",
    input: messages,
  };
  if (useWebSearch) payload.tools = [{ type: "web_search" }];

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.error?.message || `OpenAI returned ${response.status}`;
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return { text: outputText(data), raw: data };
}

async function proxyOpenAIResponses(request, env) {
  if (!env.OPENAI_API_KEY) throw new Error("OPENAI_API_KEY is not configured");
  const payload = await bodyJson(request);
  payload.model = env.OPENAI_MODEL || "gpt-5.4-mini";

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json; charset=utf-8",
      ...cors(env),
    },
  });
}

async function listMemories(request, env) {
  const result = await env.DB.prepare(
    "SELECT id, kind, content, metadata, created_at, updated_at FROM memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200",
  ).bind(userId(request)).all();
  return json({ memories: result.results || [] }, 200, env);
}

async function saveMemory(request, env) {
  const body = await bodyJson(request);
  if (!body.content || typeof body.content !== "string") {
    return json({ error: "content is required" }, 400, env);
  }
  const id = body.id || uuid();
  const timestamp = now();
  await env.DB.prepare(
    "INSERT INTO memories (id, user_id, kind, content, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, content = excluded.content, metadata = excluded.metadata, updated_at = excluded.updated_at",
  ).bind(
    id,
    userId(request),
    String(body.kind || "note").slice(0, 64),
    body.content,
    JSON.stringify(body.metadata || {}),
    timestamp,
    timestamp,
  ).run();
  return json({ ok: true, id, updated_at: timestamp }, 200, env);
}

async function deleteMemory(request, env, id) {
  await env.DB.prepare("DELETE FROM memories WHERE id = ? AND user_id = ?")
    .bind(id, userId(request)).run();
  return json({ ok: true, id }, 200, env);
}

async function listTasks(request, env) {
  const result = await env.DB.prepare(
    "SELECT id, title, details, status, priority, created_at, updated_at FROM tasks WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200",
  ).bind(userId(request)).all();
  return json({ tasks: result.results || [] }, 200, env);
}

async function saveTask(request, env) {
  const body = await bodyJson(request);
  if (!body.title || typeof body.title !== "string") {
    return json({ error: "title is required" }, 400, env);
  }
  const id = body.id || uuid();
  const timestamp = now();
  await env.DB.prepare(
    "INSERT INTO tasks (id, user_id, title, details, status, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET title = excluded.title, details = excluded.details, status = excluded.status, priority = excluded.priority, updated_at = excluded.updated_at",
  ).bind(
    id,
    userId(request),
    body.title,
    String(body.details || ""),
    String(body.status || "open").slice(0, 32),
    String(body.priority || "normal").slice(0, 32),
    timestamp,
    timestamp,
  ).run();
  return json({ ok: true, id, updated_at: timestamp }, 200, env);
}

async function chat(request, env, openAICompatible) {
  const body = await bodyJson(request);
  const messages = openAICompatible
    ? body.messages
    : [{ role: "user", content: body.query || body.message || "" }];
  if (!Array.isArray(messages) || messages.length === 0) {
    return json({ error: "messages or query is required" }, 400, env);
  }
  const result = await callOpenAI(env, messages, Boolean(body.web_search || body.use_web_search));
  if (openAICompatible) {
    return json({
      id: `chatcmpl_${uuid()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: env.OPENAI_MODEL || "gpt-5.4-mini",
      choices: [{ index: 0, message: { role: "assistant", content: result.text }, finish_reason: "stop" }],
    }, 200, env);
  }
  return json({ response: result.text, model: env.OPENAI_MODEL || "gpt-5.4-mini" }, 200, env);
}

function mcpResponse(id, result, env) {
  return json({ jsonrpc: "2.0", id, result }, 200, env);
}

function mcpText(value) {
  return { content: [{ type: "text", text: typeof value === "string" ? value : JSON.stringify(value) }] };
}

const mcpTools = [
  { name: "conductor_health", description: "Check the Ara conductor, memory, and provider status.", inputSchema: { type: "object", properties: {} } },
  { name: "list_memories", description: "List saved memories for the current user.", inputSchema: { type: "object", properties: { user_id: { type: "string" } } } },
  { name: "save_memory", description: "Save an important memory for later conversations.", inputSchema: { type: "object", required: ["content"], properties: { user_id: { type: "string" }, content: { type: "string" }, kind: { type: "string" }, metadata: { type: "object" } } } },
  { name: "list_tasks", description: "List the current user's tasks.", inputSchema: { type: "object", properties: { user_id: { type: "string" } } } },
  { name: "save_task", description: "Create or update a task.", inputSchema: { type: "object", required: ["title"], properties: { id: { type: "string" }, user_id: { type: "string" }, title: { type: "string" }, details: { type: "string" }, status: { type: "string" }, priority: { type: "string" } } } },
  { name: "web_search", description: "Search the live web and return a cited answer.", inputSchema: { type: "object", required: ["query"], properties: { query: { type: "string" } } } },
];

async function handleMcp(request, env) {
  const rpc = await bodyJson(request);
  if (rpc.method === "notifications/initialized") return new Response(null, { status: 202, headers: cors(env) });
  if (rpc.method === "initialize") {
    return mcpResponse(rpc.id, {
      protocolVersion: rpc.params?.protocolVersion || "2025-03-26",
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "ara-conductor", version: "1.0.0" },
    }, env);
  }
  if (rpc.method === "tools/list") return mcpResponse(rpc.id, { tools: mcpTools }, env);
  if (rpc.method !== "tools/call") {
    return json({ jsonrpc: "2.0", id: rpc.id ?? null, error: { code: -32601, message: "Method not found" } }, 200, env);
  }

  const name = rpc.params?.name;
  const args = rpc.params?.arguments || {};
  const uid = String(args.user_id || "default").slice(0, 128);
  if (name === "conductor_health") {
    return mcpResponse(rpc.id, mcpText({ status: "ok", openai: Boolean(env.OPENAI_API_KEY), memory: Boolean(env.DB) }), env);
  }
  if (name === "list_memories") {
    const rows = await env.DB.prepare("SELECT id, kind, content, metadata, created_at, updated_at FROM memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200").bind(uid).all();
    return mcpResponse(rpc.id, mcpText({ memories: rows.results || [] }), env);
  }
  if (name === "save_memory") {
    if (!args.content) throw new Error("content is required");
    const id = args.id || uuid();
    const timestamp = now();
    await env.DB.prepare("INSERT INTO memories (id, user_id, kind, content, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, content = excluded.content, metadata = excluded.metadata, updated_at = excluded.updated_at")
      .bind(id, uid, String(args.kind || "note"), String(args.content), JSON.stringify(args.metadata || {}), timestamp, timestamp).run();
    return mcpResponse(rpc.id, mcpText({ ok: true, id, updated_at: timestamp }), env);
  }
  if (name === "list_tasks") {
    const rows = await env.DB.prepare("SELECT id, title, details, status, priority, created_at, updated_at FROM tasks WHERE user_id = ? ORDER BY updated_at DESC LIMIT 200").bind(uid).all();
    return mcpResponse(rpc.id, mcpText({ tasks: rows.results || [] }), env);
  }
  if (name === "save_task") {
    if (!args.title) throw new Error("title is required");
    const id = args.id || uuid();
    const timestamp = now();
    await env.DB.prepare("INSERT INTO tasks (id, user_id, title, details, status, priority, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET title = excluded.title, details = excluded.details, status = excluded.status, priority = excluded.priority, updated_at = excluded.updated_at")
      .bind(id, uid, String(args.title), String(args.details || ""), String(args.status || "open"), String(args.priority || "normal"), timestamp, timestamp).run();
    return mcpResponse(rpc.id, mcpText({ ok: true, id, updated_at: timestamp }), env);
  }
  if (name === "web_search") {
    if (!args.query) throw new Error("query is required");
    const result = await callOpenAI(env, [{ role: "user", content: String(args.query) }], true);
    return mcpResponse(rpc.id, mcpText(result.text), env);
  }
  return json({ jsonrpc: "2.0", id: rpc.id ?? null, error: { code: -32602, message: `Unknown tool: ${name}` } }, 200, env);
}

const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ara Conductor</title><style>
body{font:16px system-ui;margin:0;background:#0b1020;color:#eef2ff}.wrap{max-width:780px;margin:auto;padding:24px}
.card{background:#151c32;border:1px solid #2b3554;border-radius:18px;padding:20px;margin:16px 0}input,textarea,button{font:inherit;border-radius:10px;border:1px solid #435071;padding:12px;background:#0d1428;color:#fff}input,textarea{width:100%;box-sizing:border-box;margin:6px 0}textarea{min-height:110px}button{cursor:pointer;background:#5b65f5}.muted{color:#aeb8d7}.msg{white-space:pre-wrap;line-height:1.5}</style></head>
<body><main class="wrap"><h1>Ara Conductor</h1><p class="muted">OpenAI lead conductor with persistent tasks and memory.</p>
<section class="card"><label>Bridge key (kept only in this browser tab)</label><input id="key" type="password" autocomplete="off"><label>Your request</label><textarea id="q"></textarea><button id="send">Send</button> <button id="voice">🎙 Speak</button><p id="status" class="muted"></p><div id="answer" class="msg"></div></section></main>
<script>const key=document.querySelector('#key'),q=document.querySelector('#q'),answer=document.querySelector('#answer'),status=document.querySelector('#status');
key.value=sessionStorage.bridgeKey||'';key.oninput=()=>sessionStorage.bridgeKey=key.value;
document.querySelector('#send').onclick=async()=>{status.textContent='Working…';answer.textContent='';try{const r=await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json','authorization':'Bearer '+key.value},body:JSON.stringify({query:q.value,use_web_search:true})});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');answer.textContent=d.response;status.textContent='Ready';if('speechSynthesis'in window)speechSynthesis.speak(new SpeechSynthesisUtterance(d.response));}catch(e){status.textContent=e.message}};
document.querySelector('#voice').onclick=()=>{const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R){status.textContent='Speech recognition is unavailable in this browser';return}const r=new R();r.onresult=e=>q.value=e.results[0][0].transcript;r.start()};</script></body></html>`;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });
    if (url.pathname === "/") return new Response(page, { headers: { "content-type": "text/html; charset=utf-8" } });
    if (url.pathname === "/health") {
      return json({
        status: "ok",
        service: "ara-conductor",
        providers: { openai: Boolean(env.OPENAI_API_KEY), perplexity: Boolean(env.PERPLEXITY_API_KEY), anthropic: Boolean(env.ANTHROPIC_API_KEY) },
        memory: Boolean(env.DB),
        mcp: "/mcp",
      }, 200, env);
    }
    if (!authorized(request, env)) return json({ error: "unauthorized" }, 401, env);
    try {
      if (url.pathname === "/mcp" && request.method === "POST") return await handleMcp(request, env);
      if (url.pathname === "/api/chat" && request.method === "POST") return await chat(request, env, false);
      if (url.pathname === "/v1/chat/completions" && request.method === "POST") return await chat(request, env, true);
      if (url.pathname === "/v1/responses" && request.method === "POST") return await proxyOpenAIResponses(request, env);
      if (url.pathname === "/api/memories" && request.method === "GET") return await listMemories(request, env);
      if (url.pathname === "/api/memories" && request.method === "POST") return await saveMemory(request, env);
      if (url.pathname.startsWith("/api/memories/") && request.method === "DELETE") return await deleteMemory(request, env, decodeURIComponent(url.pathname.slice(14)));
      if (url.pathname === "/api/tasks" && request.method === "GET") return await listTasks(request, env);
      if (url.pathname === "/api/tasks" && ["POST", "PATCH"].includes(request.method)) return await saveTask(request, env);
      return json({ error: "not found" }, 404, env);
    } catch (error) {
      return json({ error: error.message || "internal error" }, error.status || 500, env);
    }
  },
};
