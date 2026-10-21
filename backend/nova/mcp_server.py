import asyncio
import json
import uuid
from mcp.server.fastmcp import FastMCP
from . import store, projects
from .providers import ai_provider, search_provider, ProviderError

mcp = FastMCP("NOVA AI", instructions="NOVA tools use only configured providers and the isolated generated_projects workspace.")

@mcp.tool()
async def answer_question(question: str, context: str = "") -> dict:
    """Answer a question using the configured AI provider."""
    answer = await ai_provider.complete("You are NOVA, a clear and accurate assistant. State uncertainty.", [{"role":"user","content":[{"text":f"Context: {context[:6000]}\nQuestion: {question[:4000]}"}]}])
    return {"answer":answer,"provider":ai_provider.name}

@mcp.tool()
async def search_web(query: str, limit: int = 5) -> dict:
    """Search the web using Tavily or DuckDuckGo HTML search."""
    try: return {"results":await search_provider.search(query, limit)}
    except ProviderError as exc: return {"error":str(exc),"results":[]}

@mcp.tool()
async def research_topic(objective: str, constraints: str = "") -> dict:
    """Retrieve real web results and summarize the evidence with citations."""
    try: results = await search_provider.search(f"{objective} {constraints}".strip(), 7)
    except ProviderError as exc: return {"error":str(exc),"sources":[]}
    evidence = "\n".join(f"[{i+1}] {x['title']} {x['url']} {x['snippet']}" for i,x in enumerate(results))
    try: summary = await ai_provider.complete("Use only supplied source evidence. Cite [1] references and call out missing or uncertain facts.", [{"role":"user","content":[{"text":f"{objective}\nConstraints: {constraints}\nEvidence:\n{evidence}"}]}], 1500)
    except ProviderError as exc: return {"error":str(exc),"sources":results}
    return {"summary":summary,"sources":results}

@mcp.tool()
async def compare_products(requirements: str, budget: str = "") -> dict:
    """Search current product evidence and compare candidates without inventing facts."""
    try: results = await search_provider.search(f"{requirements} {budget} specifications price comparison", 8)
    except ProviderError as exc: return {"error":str(exc),"sources":[]}
    evidence = "\n".join(f"[{i+1}] {x['title']} {x['url']} {x['snippet']}" for i,x in enumerate(results))
    try: comparison = await ai_provider.complete("Compare only evidence provided. Do not invent prices or specifications. Identify what could not be confirmed and cite [n].", [{"role":"user","content":[{"text":f"Requirements: {requirements}; budget: {budget}\nEvidence:\n{evidence}"}]}], 1500)
    except ProviderError as exc: return {"error":str(exc),"sources":results}
    return {"comparison":comparison,"sources":results}

@mcp.tool()
def create_project(name: str, stack: str, specification: str) -> dict:
    """Create a supported application in NOVA's isolated project workspace."""
    return projects.create_project(name, specification, stack)

@mcp.tool()
def list_project_files(project_id: str) -> dict:
    """List files from a registered NOVA project."""
    return {"files":projects.list_files(project_id)}

@mcp.tool()
def read_project_file(project_id: str, path: str) -> dict:
    """Read a UTF-8 file contained within a registered NOVA project."""
    return {"content":projects.read_file(project_id, path)}

@mcp.tool()
def write_project_file(project_id: str, path: str, content: str) -> dict:
    """Create or update a bounded UTF-8 file inside a registered NOVA project."""
    return projects.write_file(project_id, path, content)

@mcp.tool()
def run_project_command(project_id: str, command: str) -> dict:
    """Run an exact command from NOVA's narrow project command allowlist."""
    if command.strip() in {"npm install", "npm run build"}:
        approval_id = uuid.uuid4().hex
        project = store.get_project(project_id)
        if not project: return {"error":"Project was not found."}
        task_id = uuid.uuid4().hex
        store.create_task(task_id, "setup", "Install dependencies for " + project["name"], "waiting_for_approval")
        store.create_approval(approval_id, task_id, command.strip(), {"project_id":project_id,"path":project["path"]})
        return {"status":"waiting_for_approval","task_id":task_id,"approval_id":approval_id}
    return projects.run_command(project_id, command)

@mcp.tool()
def get_task_status(task_id: str) -> dict:
    """Return persisted status and events for a NOVA task."""
    return store.get_task(task_id) or {"error":"Task not found."}

@mcp.tool()
def request_human_approval(task_id: str, action: str, details: str) -> dict:
    """Create a pending human approval record; this tool never performs the action."""
    if not store.get_task(task_id): return {"error":"Task not found."}
    approval_id = uuid.uuid4().hex
    store.create_approval(approval_id, task_id, action[:120], {"description":details[:2000]})
    store.update_task(task_id, status="waiting_for_approval", event=f"Approval required for: {action[:120]}")
    return {"approval_id":approval_id,"status":"pending"}

if __name__ == "__main__":
    store.initialize()
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
