import json
import re
import uuid
from . import store, projects
from .providers import ai_provider, search_provider, ProviderError

async def generate_files(system, prompt, allowed, max_tokens):
    response = await ai_provider.complete(system, [{"role":"user","content":[{"text":prompt}]}], max_tokens)
    for attempt in range(2):
        match = re.search(r"\{[\s\S]*\}", response)
        try:
            files = json.loads(match.group(0)).get("files", {}) if match else None
        except json.JSONDecodeError:
            files = None
        valid = isinstance(files, dict) and 0 < len(files) <= len(allowed) and all(path in allowed and isinstance(content, str) and len(content.encode()) <= 300_000 for path, content in files.items())
        if valid: return files
        if attempt == 0:
            response = await ai_provider.complete("Your previous output was not a valid bounded JSON file bundle. Return only valid JSON with a files object containing complete string values for allowed paths. Do not add markdown or commentary.", [{"role":"user","content":[{"text":f"Original request: {prompt}\nAllowed paths: {json.dumps(allowed)}\nInvalid output to correct:\n{response[:18000]}"}]}], max_tokens)
    raise ProviderError(f"{ai_provider.name} could not return a valid bounded file bundle after one repair attempt. No proposed file changes were applied.")

def classify(text):
    value = text.lower()
    if re.search(r"\b(build|create|make|implement|scaffold|add|update|modify)\b.*\b(app|application|website|dashboard|project|feature|tracker|portfolio)\b", value) or "expense tracker" in value: return "build"
    if any(x in value for x in ("research", "find the best", "compare", "current price", "latest", "under ₹", "under rs", "laptop", "search for")): return "research"
    return "answer"

async def process(task_id, request, history):
    kind = classify(request)
    store.update_task(task_id, status="planning", event="Understanding the request")
    project = None
    sources = []
    try:
        action_text = request.lower()
        external_action = re.search(r"\b(publish|deploy|release|send|purchase|buy)\b", action_text) and re.search(r"\b(production|public|live|account|email|message|purchase|order)\b", action_text)
        if external_action:
            project = store.get_project()
            answer = "NOVA does not publish to production, send external messages, or make purchases. No external action was taken. Production credentials and publishing integrations are not connected. I can help prepare the project or outline the steps for you to review."
            result = {"kind":kind,"answer":answer,"project":project}
            store.update_task(task_id, status="waiting_for_user", result=result, event="Stopped before an unsupported external action")
            store.save_message(uuid.uuid4().hex, "assistant", answer, {"task_id":task_id})
            return
        if kind == "answer":
            store.update_task(task_id, status="running", event=f"Preparing an answer with {ai_provider.name}")
            context = [{"role": x["role"], "content": [{"text": x["content"]}]} for x in history[-12:] if x["role"] in ("user", "assistant")]
            context.append({"role": "user", "content": [{"text": request}]})
            answer = await ai_provider.complete("You are NOVA, a clear and helpful voice-first assistant. Answer accurately. If uncertain, say so.", context)
            result = {"kind": kind, "answer": answer}
        elif kind == "research":
            store.update_task(task_id, status="running", event="Searching the web for current source material")
            sources = await search_provider.search(request, 7)
            store.update_task(task_id, event=f"Reviewing {len(sources)} real search results")
            evidence = "\n\n".join(f"[{i+1}] {x['title']}\nURL: {x['url']}\nSnippet: {x['snippet']}" for i,x in enumerate(sources))
            research_system = "You are NOVA's evidence-based research analyst. Use only the supplied search results. Cite every factual recommendation with [n] matching the supplied URL. Never invent a product, price, specification, stock status, or URL. Separate facts directly supported by retrieved evidence from estimates and unknowns. For a laptop budget in INR, preserve the stated INR budget, distinguish new from refurbished or used options, and explicitly say if the sources do not support a reliable new-laptop recommendation under budget."
            answer = await ai_provider.complete(research_system, [{"role":"user","content":[{"text":f"Research request: {request}\n\nRetrieved evidence:\n{evidence}"}]}], 1500)
            result = {"kind": kind, "answer": answer, "sources": sources}
        else:
            store.update_task(task_id, event="Creating a bounded implementation plan")
            plan = ["Choose a supported application template", f"Generate an implementation from the request when {ai_provider.name} is configured", "Create project files inside NOVA's dedicated workspace", "Request approval before dependency installation", "Report project files and local startup instructions"]
            active = store.get_project()
            if active and any(term in request.lower() for term in ("dashboard", "existing project", "just created", "the app", "this app")) and any(term in request.lower() for term in ("add", "modify", "update", "change", "create")):
                project = active
                plan.insert(0, f"Inspect files in the active project {project['name']}")
                store.update_task(task_id, status="running", event="Inspecting the active project before a targeted change")
                files = projects.list_files(project["id"])
                sources = {path:projects.read_file(project["id"], path) for path in files if path.endswith((".tsx", ".ts", ".css", ".py")) and "node_modules" not in path}
                if not sources: raise ValueError("No supported source files were found in the active project.")
                if not ai_provider.configured: raise ProviderError(ai_provider.configuration_error())
                source_text = json.dumps(sources, ensure_ascii=False)
                updates = await generate_files("You are editing an existing application. Return only valid JSON with a files object. Include only files that need to change. Preserve unrelated functionality. Do not include markdown or text outside JSON.", f"Request: {request}\nAuthorized existing source files:\n{source_text[:24000]}", list(sources), 4000)
                for relative, content in updates.items():
                    projects.write_file(project["id"], relative, content)
                result = {"kind":kind,"plan":plan,"project":project,"changed_files":list(updates),"answer":f"Updated {', '.join(updates)} in {project['name']}. The development server was not started."}
                store.update_task(task_id, status="completed", result=result, event=f"Updated {len(updates)} inspected project source file(s)")
                store.save_message(uuid.uuid4().hex, "assistant", result["answer"], {"task_id":task_id})
                return
            store.update_task(task_id, status="running", event="Creating the project in the approved workspace")
            stack = "fastapi" if "fastapi" in request.lower() else "react-vite"
            name_match = re.search(r"(?:create|build|make)\s+(?:me\s+)?(?:a\s+)?(.{3,70}?)(?:\s+using|\s+with|\s+app|\s+application|$)", request, re.I)
            name = (name_match.group(1) if name_match else "NOVA generated application").strip(" .")[:60]
            plan.insert(0, f"Generate a {stack} project named {name}")
            if not ai_provider.configured:
                raise ProviderError(ai_provider.configuration_error())
            store.update_task(task_id, event=f"Generating application code with {ai_provider.name}")
            allowed = ["main.py"] if stack == "fastapi" else ["src/App.tsx", "src/style.css"]
            file_bundle = await generate_files("Implement the user's application request as working code files. Return only a JSON files object. Include only allowed paths. Produce complete code, not pseudocode; omit source comments; use existing dependencies only; preserve accessible responsive behavior; include useful empty and error states.", f"Application specification: {request}\nProject name: {name}\nStack: {stack}\nAllowed files: {json.dumps(allowed)}\nReturn complete file contents for every allowed file.", allowed, 5000)
            project = projects.create_project(name, request, stack)
            for path, content in file_bundle.items(): projects.write_file(project["id"], path, content)
            approval_id = uuid.uuid4().hex
            store.create_approval(approval_id, task_id, "npm install" if stack == "react-vite" else "pip install -r requirements.txt", {"project_id":project["id"],"path":project["path"]})
            result = {"kind":kind,"plan":plan,"project":project,"approval":{"id":approval_id,"action":"Install project dependencies"},"answer":f"Generated application source with {ai_provider.name} and created {len(project['files'])} project files at {project['path']}. Review the files, then approve dependency installation before building or running the app."}
            store.update_task(task_id, status="waiting_for_approval", result=result, event="Project files created; dependency installation is waiting for your approval")
            store.save_message(uuid.uuid4().hex, "assistant", result["answer"], {"task_id":task_id})
            return
        store.save_message(uuid.uuid4().hex, "assistant", result["answer"], {"task_id":task_id})
        store.update_task(task_id, status="completed", result=result, event="Task completed")
    except ProviderError as exc:
        failed = {"kind":kind,"error":str(exc)}
        if project: failed["project"] = project
        if sources: failed["sources"] = sources
        store.update_task(task_id, status="failed", result=failed, event="A required external provider is unavailable")
        store.save_message(uuid.uuid4().hex, "assistant", str(exc), {"task_id":task_id,"error":True})
    except Exception as exc:
        store.update_task(task_id, status="failed", result={"kind":kind,"error":str(exc) or "NOVA could not complete this operation. Check service configuration and try again."}, event="Task stopped after an internal operation error")
