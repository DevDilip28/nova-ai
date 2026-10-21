import os
import json
import re
import subprocess
import uuid
from pathlib import Path
from .config import settings
from . import store

def safe_root(project_id):
    project = store.get_project(project_id)
    if not project: raise ValueError("Project was not found.")
    root = Path(project["path"]).resolve()
    if not root.is_relative_to(settings.projects_root.resolve()): raise ValueError("Project path is outside the approved workspace.")
    return root

def secret_path(path):
    parts = [part.lower() for part in Path(path).parts]
    return any(part == ".env" or part.startswith(".env.") or part in {"credentials", "credentials.json", "secrets", "secrets.json", "id_rsa", "id_ed25519"} for part in parts)

def create_project(name, specification, stack="react-vite"):
    if stack not in {"react-vite", "fastapi"}: raise ValueError("Supported stacks are react-vite and fastapi.")
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:42] or "nova-project"
    folder = settings.projects_root / f"{slug}-{uuid.uuid4().hex[:6]}"
    folder.mkdir(parents=True, exist_ok=False)
    if stack == "react-vite":
        files = {
            "package.json": '{"name":"'+slug+'","private":true,"version":"0.1.0","type":"module","scripts":{"dev":"vite --host 127.0.0.1","build":"tsc -b && vite build","preview":"vite preview --host 127.0.0.1"},"dependencies":{"@vitejs/plugin-react":"^4.3.4","vite":"^6.0.7","typescript":"~5.7.2","react":"^18.3.1","react-dom":"^18.3.1","lucide-react":"^0.468.0"},"devDependencies":{"@types/react":"^18.3.12","@types/react-dom":"^18.3.1"}}',
            "index.html": '<div id="root"></div><script type="module" src="/src/main.tsx"></script>',
            "tsconfig.json": '{"compilerOptions":{"target":"ES2022","lib":["ES2022","DOM","DOM.Iterable"],"module":"ESNext","moduleResolution":"Bundler","jsx":"react-jsx","strict":true,"skipLibCheck":true,"noEmit":true,"esModuleInterop":true,"allowSyntheticDefaultImports":true},"include":["src"]}',
            "vite.config.ts": 'import {defineConfig} from "vite";import react from "@vitejs/plugin-react";export default defineConfig({plugins:[react()]});',
            "src/main.tsx": 'import React from "react";import{createRoot}from"react-dom/client";import App from"./App";import"./style.css";createRoot(document.getElementById("root")!).render(<App/>);',
            "src/App.tsx": '''import { useEffect, useMemo, useState } from "react";
type Expense = { id: string; title: string; category: string; amount: number; date: string };
const seed: Expense[] = [{id:"seed-1",title:"Design subscription",category:"Tools",amount:24,date:new Date().toISOString().slice(0,10)},{id:"seed-2",title:"Team lunch",category:"Food",amount:38.5,date:new Date().toISOString().slice(0,10)}];
export default function App(){const [items,setItems]=useState<Expense[]>(()=>{try{return JSON.parse(localStorage.getItem("expenses")||"null")||seed}catch{return seed}});const [title,setTitle]=useState("");const [amount,setAmount]=useState("");const [category,setCategory]=useState("Other");useEffect(()=>{localStorage.setItem("expenses",JSON.stringify(items))},[items]);const total=useMemo(()=>items.reduce((sum,item)=>sum+item.amount,0),[items]);const add=(event:React.FormEvent)=>{event.preventDefault();const value=Number(amount);if(!title.trim()||!Number.isFinite(value)||value<=0)return;setItems([{id:crypto.randomUUID(),title:title.trim(),category,amount:value,date:new Date().toISOString().slice(0,10)},...items]);setTitle("");setAmount("")};return <main><header><div className="brand"><span className="mark">N</span> NOVA / LEDGER</div><span className="period">PERSONAL FINANCE · THIS MONTH</span></header><section className="intro"><div className="eyebrow">EXPENSE OVERVIEW</div><h1>Spend with<br/><em>intention.</em></h1><p>{''' + json.dumps(specification[:260]) + '''}</p></section><section className="summary"><div><small>TOTAL SPENT</small><strong>${total.toFixed(2)}</strong><span>Across {items.length} recorded expenses</span></div><div className="summary-orbit">↗</div></section><section className="layout"><div className="ledger"><div className="section-head"><h2>Recent expenses</h2><span>{items.length} RECORDS</span></div>{items.length?items.map(item=><article className="expense" key={item.id}><div className="category-icon">{item.category.slice(0,1)}</div><div className="expense-info"><b>{item.title}</b><small>{item.category} · {item.date}</small></div><strong>−${item.amount.toFixed(2)}</strong><button aria-label={"Remove "+item.title} onClick={()=>setItems(items.filter(x=>x.id!==item.id))}>×</button></article>):<div className="empty">Your expenses will appear here.</div>}</div><form className="add-card" onSubmit={add}><div className="eyebrow">NEW TRANSACTION</div><h2>Add an expense</h2><label>Description<input value={title} onChange={e=>setTitle(e.target.value)} placeholder="e.g. Coffee with Sam" required/></label><div className="form-row"><label>Amount<input type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="0.00" required/></label><label>Category<select value={category} onChange={e=>setCategory(e.target.value)}>{["Other","Food","Travel","Tools","Home","Health"].map(x=><option key={x}>{x}</option>)}</select></label></div><button className="add-button">Add expense <span>＋</span></button><small className="storage-note">Your records are saved in this browser.</small></form></section><footer><span>BUILT WITH NOVA AI</span><span>PRIVATE BY DESIGN · STORED LOCALLY</span></footer></main>}''',
            "src/style.css": '''@import url("https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap");*{box-sizing:border-box}body{margin:0;background:#0a0b11;color:#f0eff7;font:14px "DM Sans",sans-serif}main{max-width:980px;margin:auto;padding:30px 44px}header,footer{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #24242e;padding:0 0 17px}.brand{font:700 11px "Space Grotesk";letter-spacing:.12em;display:flex;align-items:center;gap:9px}.mark{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;background:#211b37;color:#b9a5ff}.period,footer{color:#777988;font-size:9px;letter-spacing:.12em}.intro{padding:47px 0 22px}.eyebrow{font-size:9px;letter-spacing:.16em;color:#a493ef;font-weight:700}.intro h1{font:600 clamp(43px,7vw,69px)/.99 "Space Grotesk";letter-spacing:-.06em;margin:14px 0}.intro h1 em{font-style:normal;color:#a693ff}.intro p{max-width:590px;color:#878a9a;line-height:1.65;font-size:12px}.summary{height:117px;border:1px solid #343040;border-radius:12px;background:linear-gradient(105deg,#191624,#11131a);padding:19px 22px;display:flex;align-items:center;justify-content:space-between}.summary div:first-child{display:flex;flex-direction:column;gap:5px}.summary small,.summary span{color:#838696;font-size:9px}.summary strong{font:600 29px "Space Grotesk"}.summary-orbit{width:45px;height:45px;display:grid;place-items:center;border:1px solid #594e78;background:#29223c;border-radius:50%;color:#b3a0ff;font-size:19px}.layout{display:grid;grid-template-columns:1.25fr .75fr;gap:17px;margin:18px 0 45px}.ledger,.add-card{border:1px solid #242530;background:#101118;border-radius:11px;padding:16px}.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}.section-head h2,.add-card h2{font:500 16px "Space Grotesk";margin:0}.section-head>span{font-size:8px;letter-spacing:.1em;color:#777988}.expense{display:flex;align-items:center;gap:10px;padding:11px 0;border-top:1px solid #20212a}.category-icon{width:31px;height:31px;border-radius:9px;background:#211c31;color:#b7a8eb;display:grid;place-items:center;font-size:11px}.expense-info{display:flex;flex:1;flex-direction:column;gap:4px}.expense-info b{font-size:10px;font-weight:600}.expense-info small{font-size:9px;color:#818494}.expense>strong{font-size:11px}.expense button{background:none;border:0;color:#737687;font-size:17px}.expense button:hover{color:#ff9ba6}.empty{padding:22px 4px;color:#7d8090;font-size:11px}.add-card .eyebrow{margin:1px 0 6px}.add-card h2{margin-bottom:15px}.add-card label{display:flex;flex-direction:column;gap:6px;color:#9295a5;font-size:9px;margin:11px 0}.add-card input,.add-card select{width:100%;border:1px solid #2c2d39;background:#0c0d13;border-radius:7px;padding:9px;color:#e5e4ed;font:10px "DM Sans";outline:none}.add-card input:focus,.add-card select:focus{border-color:#806bd0}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.add-button{width:100%;display:flex;justify-content:space-between;align-items:center;padding:10px 11px;border:1px solid #7565bf;border-radius:7px;background:linear-gradient(100deg,#7765c3,#61529f);color:white;font:600 10px "DM Sans";margin-top:5px}.add-button span{font-size:14px}.storage-note{display:block;text-align:center;color:#777988;font-size:8px;margin-top:10px}footer{border-top:1px solid #24242e;border-bottom:0;padding:15px 0}@media(max-width:650px){main{padding:20px 17px}.period{font-size:7px}.intro{padding-top:36px}.layout{grid-template-columns:1fr}.summary{height:104px}.ledger{order:2}}''',
            "README.md": f"# {name}\n\nGenerated by NOVA AI.\n\n## Specification\n\n{specification}\n\n## Start\n\nRun `npm install` and `npm run dev`.\n"
        }
    else:
        files = {"requirements.txt": "fastapi\nuvicorn[standard]\n", "main.py": 'from fastapi import FastAPI\napp=FastAPI(title="'+name.replace('"','')+'")\n@app.get("/")\ndef home(): return {"message":"'+specification[:100].replace('"','')+'"}\n', "README.md": f"# {name}\n\nGenerated by NOVA AI.\n\n## Specification\n\n{specification}\n\n## Start\n\nRun `uvicorn main:app --reload`.\n"}
    for relative, content in files.items():
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    pid = uuid.uuid4().hex
    store.save_project(pid, name, folder, stack)
    return {"id": pid, "name": name, "path": str(folder), "stack": stack, "files": list(files)}

def list_files(project_id):
    root = safe_root(project_id)
    return [str(p.relative_to(root)).replace(os.sep, "/") for p in root.rglob("*") if p.is_file() and "node_modules" not in p.parts]

def read_file(project_id, relative):
    if secret_path(relative): raise ValueError("Secret and environment files cannot be read through NOVA tools.")
    root = safe_root(project_id)
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file(): raise ValueError("Requested file is not available in this project.")
    if target.stat().st_size > 300_000: raise ValueError("File exceeds the 300 KB read limit.")
    return target.read_text(encoding="utf-8")

def write_file(project_id, relative, content):
    if secret_path(relative): raise ValueError("Secret and environment files cannot be written through NOVA tools.")
    root = safe_root(project_id); target = (root / relative).resolve()
    if not target.is_relative_to(root) or target == root: raise ValueError("Path escapes the project workspace or does not name a file.")
    if len(content.encode()) > 300_000: raise ValueError("File exceeds the 300 KB write limit.")
    target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content, encoding="utf-8")
    return {"path": relative, "bytes": target.stat().st_size}

def run_command(project_id, command, approved=False):
    project = store.get_project(project_id); root = safe_root(project_id)
    command = command.strip()
    allowed = {"npm install", "npm run build", "npm run dev", "python -m uvicorn main:app --reload", "uvicorn main:app --reload"}
    if command not in allowed: raise ValueError("Command is not on NOVA's project command allowlist.")
    if command in {"npm install", "npm run build"} and not approved: raise ValueError("This project command needs approval from the NOVA interface.")
    if command.endswith("dev") or "--reload" in command:
        raise ValueError("Long-running development servers must be started from your terminal using the project path.")
    executable, *args = command.split()
    timeout = settings.dependency_install_timeout_seconds if command == "npm install" else settings.command_timeout_seconds
    try:
        result = subprocess.run([executable, *args], cwd=root, capture_output=True, text=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired as exc: return {"exit_code": None, "stdout": (exc.stdout or "")[:12000], "stderr": "Command exceeded the configured time limit."}
    return {"exit_code": result.returncode, "stdout": result.stdout[-12000:], "stderr": result.stderr[-12000:]}

def setup_fastapi(project_id, approved=False):
    if not approved: raise ValueError("Python dependency installation needs approval from the NOVA interface.")
    root = safe_root(project_id)
    try:
        env = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "venv", ".venv"], cwd=root, capture_output=True, text=True, timeout=settings.command_timeout_seconds, shell=False)
        if env.returncode: return {"exit_code":env.returncode,"stdout":env.stdout[-12000:],"stderr":env.stderr[-12000:]}
        python = root / ".venv" / "Scripts" / "python.exe"
        if not python.is_file(): raise ValueError("Could not locate the project virtual environment's Python executable.")
        result = subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements.txt"], cwd=root, capture_output=True, text=True, timeout=settings.dependency_install_timeout_seconds, shell=False)
        return {"exit_code":result.returncode,"stdout":result.stdout[-12000:],"stderr":result.stderr[-12000:]}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code":None,"stdout":(exc.stdout or "")[-12000:],"stderr":"Project setup exceeded the configured time limit."}
