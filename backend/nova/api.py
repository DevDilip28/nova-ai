import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from . import store, agent, projects
from .config import settings
from .providers import ai_provider, search_provider

@asynccontextmanager
async def lifespan(app):
    store.initialize()
    yield

app = FastAPI(title="NOVA AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.allowed_origins.split(",")], allow_methods=["*"], allow_headers=["*"])
running = {}

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)

class ApprovalRequest(BaseModel):
    approved: bool

class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    specification: str = Field(min_length=1, max_length=8000)
    stack: str = "react-vite"

class FileWrite(BaseModel):
    path: str
    content: str

class CommandRequest(BaseModel):
    command: str
    approved: bool = False

@app.get("/api/health")
def health():
    return {"status":"ok","ai_provider":settings.ai_provider.strip().lower(),"ai_provider_configured":ai_provider.configured,"bedrock_configured":bool(settings.bedrock_model_id),"search_provider":"tavily" if settings.tavily_api_key else "duckduckgo-html","mcp_url":"http://127.0.0.1:8001/mcp"}

@app.get("/api/messages")
def get_messages(): return store.messages()

@app.post("/api/chat")
async def chat(body: ChatRequest):
    history = store.messages(30)
    user_id, task_id = uuid.uuid4().hex, uuid.uuid4().hex
    store.save_message(user_id, "user", body.message)
    store.create_task(task_id, agent.classify(body.message), body.message)
    running[task_id] = asyncio.create_task(agent.process(task_id, body.message, history))
    return {"task_id":task_id,"user_message_id":user_id}

@app.get("/api/tasks")
def tasks(): return store.list_tasks()

@app.get("/api/tasks/{task_id}")
def task(task_id: str):
    result = store.get_task(task_id)
    if not result: raise HTTPException(404, "Task not found")
    return result

@app.get("/api/tasks/{task_id}/events")
async def task_events(task_id: str):
    if not store.get_task(task_id): raise HTTPException(404, "Task not found")
    async def stream():
        previous = None
        while True:
            current = store.get_task(task_id)
            if not current: break
            payload = json.dumps(current)
            if payload != previous:
                yield f"data: {payload}\n\n"; previous = payload
            if current["status"] in {"completed", "failed", "cancelled", "waiting_for_approval", "waiting_for_user"}: break
            await asyncio.sleep(0.8)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.post("/api/tasks/{task_id}/cancel")
async def cancel(task_id: str):
    task_obj = store.get_task(task_id)
    if not task_obj: raise HTTPException(404, "Task not found")
    job = running.get(task_id)
    if job and not job.done(): job.cancel()
    store.update_task(task_id, status="cancelled", event="Task cancelled by user")
    return store.get_task(task_id)

@app.get("/api/approvals")
def approvals(): return store.pending_approvals()

@app.post("/api/approvals/{approval_id}")
async def approve(approval_id: str, body: ApprovalRequest):
    item = store.resolve_approval(approval_id, body.approved)
    if not item: raise HTTPException(404, "Approval request not found")
    task_obj = store.get_task(item["task_id"])
    if not body.approved:
        answer = "Dependency installation was declined. Project files remain available; you can install dependencies manually." if "install" in item["action"] else "The project build was declined. Project files remain available."
        result = task_obj["result"] | {"answer":answer}
        store.update_task(item["task_id"], status="completed", result=result, event="Approval declined; generated project retained")
        return {"status":"rejected"}
    project_id = item["details"].get("project_id")
    project_info = store.get_project(project_id) if project_id else None
    allowed = {"react-vite": {"npm install", "npm run build", "npm run dev"}, "fastapi": {"pip install -r requirements.txt", "python -m compileall -q .", "python -m uvicorn main:app --reload"}}
    if not project_info or item["action"] not in allowed.get(project_info["stack"], set()):
        answer = "This action is not available through NOVA's supported project tools. No external action was taken."
        result = task_obj["result"] | {"answer":answer,"error":"No connected execution tool supports this approved action."}
        store.update_task(item["task_id"], status="waiting_for_user", result=result, event="Approval recorded; action is outside supported project operations")
        return {"status":"blocked","message":answer}
    try:
        store.update_task(item["task_id"], status="running", event=f"Running approved action: {item['action']}")
        if item["action"] in {"npm run dev", "python -m uvicorn main:app --reload"}:
            result = await asyncio.to_thread(projects.start_server, project_id, True)
            if result["status"] != "running" or not result.get("url"):
                raise ValueError("The server did not report a ready local URL before the startup timeout. " + "\n".join(result.get("output", [])[-10:]))
            final = task_obj["result"] | {"answer":f"Application running at {result['url']}", "server":result}
            store.update_task(item["task_id"], status="completed", result=final, event="Managed development server is running")
            return {"status":"completed","result":result}
        if project_info["stack"] == "react-vite":
            result = await asyncio.to_thread(projects.run_command, project_id, item["action"], True)
        elif item["action"] == "pip install -r requirements.txt":
            result = await asyncio.to_thread(projects.setup_fastapi, project_id, True)
        else:
            result = await asyncio.to_thread(projects.run_command, project_id, item["action"], True)
        if result["exit_code"] != 0:
            raise ValueError(f"Approved command failed with exit code {result['exit_code']}.\n{result.get('stderr', '')[-4000:]}\n{result.get('stdout', '')[-4000:]}")
        if item["action"] == "pip install -r requirements.txt":
            completion = "Dependencies installed in the project virtual environment. Start it with .venv\\Scripts\\python.exe -m uvicorn main:app --reload from the project directory."
        elif item["action"] == "npm install":
            completion = "Dependencies installed successfully. Start the app with npm run dev from the project directory."
        else:
            completion = "The project build command completed successfully."
        final = task_obj["result"] | {"answer":completion,"command_result":result}
        store.update_task(item["task_id"], status="completed", result=final, event="Approved project action completed successfully")
        return {"status":"completed","result":result}
    except Exception as exc:
        store.update_task(item["task_id"], status="failed", result=task_obj["result"] | {"error":str(exc)}, event="Approved setup could not be completed")
        raise HTTPException(400, str(exc))

@app.get("/api/projects")
def project_list(): return store.projects()

@app.post("/api/projects")
def project_create(body: ProjectRequest):
    try: return projects.create_project(body.name, body.specification, body.stack)
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.get("/api/projects/{project_id}/files")
def files(project_id: str):
    try: return {"files":projects.list_files(project_id)}
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.get("/api/projects/{project_id}/files/{path:path}")
def file_read(project_id: str, path: str):
    try: return {"content":projects.read_file(project_id, path)}
    except (ValueError, UnicodeDecodeError) as exc: raise HTTPException(400, str(exc))

@app.put("/api/projects/{project_id}/files")
def file_write(project_id: str, body: FileWrite):
    try: return projects.write_file(project_id, body.path, body.content)
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.post("/api/projects/{project_id}/commands")
def command(project_id: str, body: CommandRequest):
    action = body.command.strip()
    project = store.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    supported = {"react-vite": {"npm install", "npm run build", "npm run dev"}, "fastapi": {"pip install -r requirements.txt", "python -m compileall -q .", "python -m uvicorn main:app --reload"}}
    if action in supported.get(project["stack"], set()):
        if not project: raise HTTPException(404, "Project not found")
        task_id, approval_id = uuid.uuid4().hex, uuid.uuid4().hex
        store.create_task(task_id, "setup", f"{action} for {project['name']}", "waiting_for_approval")
        store.update_task(task_id, result={"project_id":project_id,"project":project,"approval":{"id":approval_id,"action":action}}, event=f"{action} is waiting for approval")
        store.create_approval(approval_id, task_id, action, {"project_id":project_id,"path":project["path"]})
        return {"status":"waiting_for_approval","task_id":task_id,"approval_id":approval_id,"action":action}
    try: return projects.run_command(project_id, action)
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.get("/api/projects/{project_id}/server")
def server_status(project_id: str):
    try: return projects.server_status(project_id)
    except ValueError as exc: raise HTTPException(400, str(exc))

@app.delete("/api/projects/{project_id}/server")
def server_stop(project_id: str):
    try: return projects.stop_server(project_id)
    except ValueError as exc: raise HTTPException(400, str(exc))
