from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
import os
import time
import hashlib
import secrets
from collections import defaultdict
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.database import init_db, get_db
from app.models import Link, Group
from app.schemas import (LoginRequest, GroupCreate, GroupUpdate, GroupOut,
                         LinkCreate, LinkUpdate, LinkOut, ReorderRequest)
from app.fetcher import fetch_title

app = FastAPI(title="sz41-nav Admin", version="2.0.0")

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "templates")
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# === Auth Config ===
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
serializer = URLSafeTimedSerializer(SECRET_KEY, salt="sz41-admin-auth")
COOKIE_NAME = "sz41_session"
COOKIE_MAX_AGE = 86400 * 7  # 7 days

# === Rate Limiter ===
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 900  # 15 minutes
RATE_LIMIT_BAN_TIME = 900  # 15 minutes
rate_limit_store = {}  # ip -> {"attempts": [timestamps], "banned_until": timestamp or None}


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    entry = rate_limit_store.get(ip)

    # Check if currently banned
    if entry and entry.get("banned_until") and now < entry["banned_until"]:
        return True

    # Clean old attempts
    if entry:
        entry["attempts"] = [t for t in entry["attempts"] if now - t < RATE_LIMIT_WINDOW]
        if len(entry["attempts"]) >= RATE_LIMIT_MAX_ATTEMPTS:
            entry["banned_until"] = now + RATE_LIMIT_BAN_TIME
            return True
    return False


def record_failed_attempt(ip: str):
    now = time.time()
    if ip not in rate_limit_store:
        rate_limit_store[ip] = {"attempts": [], "banned_until": None}
    rate_limit_store[ip]["attempts"].append(now)


def record_successful_attempt(ip: str):
    """Clear rate limit on successful login."""
    rate_limit_store.pop(ip, None)


def get_client_ip(request: Request) -> str:
    """Get real client IP behind Cloudflare/nginx proxy."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def is_https(request: Request) -> bool:
    """Detect if original request was HTTPS (Cloudflare proxy)."""
    return request.headers.get("X-Forwarded-Proto", "") == "https"


def verify_password(password: str) -> bool:
    return password == ADMIN_PASSWORD


def create_session() -> str:
    return serializer.dumps({"role": "admin"})


def verify_session(token: str) -> bool:
    try:
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("role") == "admin"
    except (BadSignature, SignatureExpired):
        return False


def get_token_from_request(request: Request) -> Optional[str]:
    # Check Authorization header first
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    # Check cookie
    return request.cookies.get(COOKIE_NAME)


async def require_auth(request: Request, response: Response = None):
    """Dependency: check auth, return 401/redirect if not authenticated."""
    token = get_token_from_request(request)
    if not token or not verify_session(token):
        # If it's an API request, return JSON error
        accept = request.headers.get("accept", "")
        if "/json" in accept or request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="未登录，请先登录")
        # Otherwise redirect to login page
        return None
    return token


def require_auth_api(request: Request):
    """Dependency for API routes - only returns JSON 401."""
    token = get_token_from_request(request)
    if not token or not verify_session(token):
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    return token


# === Public routes (no auth needed) ===

@app.get("/api/check-auth")
def check_auth(request: Request):
    """Check if the user is authenticated."""
    token = get_token_from_request(request)
    if token and verify_session(token):
        return {"authenticated": True}
    return {"authenticated": False}


@app.post("/api/login")
async def login(data: LoginRequest, request: Request, response: Response = None):
    """Login endpoint with rate limiting."""
    client_ip = get_client_ip(request)

    # Rate limit check
    if is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请15分钟后再试")

    if not verify_password(data.password):
        record_failed_attempt(client_ip)
        raise HTTPException(status_code=401, detail="密码错误")

    # Success - clear rate limit
    record_successful_attempt(client_ip)
    session_token = create_session()

    secure = is_https(request)
    resp = JSONResponse({"ok": True, "token": session_token})
    resp.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return resp


@app.post("/api/logout")
async def logout(response: Response = None):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    token = get_token_from_request(request)
    if token and verify_session(token):
        return RedirectResponse(url="/admin")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sz41-nav 登录</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background: #0f172a; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 40px; width: 100%; max-width: 400px; }
  input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; border-radius: 8px; padding: 10px 14px; width: 100%; outline: none; }
  input:focus { border-color: #3b82f6; }
  .btn { background: #3b82f6; color: white; padding: 10px 20px; border-radius: 8px; cursor: pointer; border: none; font-size: 15px; width: 100%; }
  .btn:hover { background: #2563eb; }
  .error { color: #ef4444; font-size: 14px; text-align: center; margin-top: 8px; display: none; }
  .logo { font-size: 48px; text-align: center; margin-bottom: 20px; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">🔗</div>
  <h1 class="text-xl font-bold text-center mb-6">sz41-nav 后台管理</h1>
  <form id="loginForm" onsubmit="return handleLogin(event)">
    <div class="mb-4">
      <input type="password" id="password" placeholder="请输入管理密码" autofocus>
    </div>
    <button type="submit" class="btn">登录</button>
    <div id="errorMsg" class="error"></div>
  </form>
</div>
<script>
async function handleLogin(e) {
  e.preventDefault();
  const pwd = document.getElementById('password').value;
  const errEl = document.getElementById('errorMsg');
  if (!pwd) { errEl.textContent = '请输入密码'; errEl.style.display = 'block'; return; }

  try {
    const r = await fetch('/admin/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: pwd})
    });
    if (!r.ok) {
      errEl.textContent = '密码错误'; errEl.style.display = 'block'; return;
    }
    const data = await r.json();
    if (data.ok) {
      window.location.href = '/admin/';
    }
  } catch(e) {
    errEl.textContent = '登录失败，请重试'; errEl.style.display = 'block';
  }
}
</script>
</body>
</html>"""
    return html


# === Protected API routes ===

@app.get("/api/links", response_model=List[LinkOut])
def list_links(group_id: int = 0, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    query = db.query(Link)
    if group_id:
        query = query.filter(Link.group_id == group_id)
    return query.order_by(Link.sort_order, Link.id).all()


@app.post("/api/links", response_model=LinkOut)
async def create_link(data: LinkCreate, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    title = data.title
    if not title:
        title = await fetch_title(data.url)

    max_order = db.query(Link.sort_order).filter(Link.group_id == data.group_id).order_by(Link.sort_order.desc()).first()
    sort_order = (max_order[0] + 1) if max_order and max_order[0] else 0

    link = Link(
        title=title,
        url=data.url,
        group_id=data.group_id,
        sort_order=sort_order * 10,
        icon=data.icon,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@app.get("/api/links/{link_id}", response_model=LinkOut)
def get_link(link_id: int, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(404, "链接不存在")
    return link


@app.put("/api/links/{link_id}", response_model=LinkOut)
async def update_link(link_id: int, data: LinkUpdate, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(404, "链接不存在")

    if data.title is not None:
        link.title = data.title
    if data.url is not None:
        link.url = data.url
        if data.title is None:
            link.title = await fetch_title(data.url)
    if data.group_id is not None:
        link.group_id = data.group_id
    if data.sort_order is not None:
        link.sort_order = data.sort_order
    if data.enabled is not None:
        link.enabled = data.enabled
    if data.icon is not None:
        link.icon = data.icon

    db.commit()
    db.refresh(link)
    return link


@app.delete("/api/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    link = db.query(Link).filter(Link.id == link_id).first()
    if not link:
        raise HTTPException(404, "链接不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}


@app.post("/api/links/reorder")
def reorder_links(data: ReorderRequest, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    for item in data.items:
        db.query(Link).filter(Link.id == item.id).update({"sort_order": item.sort_order})
    db.commit()
    return {"ok": True}


@app.get("/api/fetch-title")
async def api_fetch_title(url: str, _=Depends(require_auth_api)):
    title = await fetch_title(url)
    return {"title": title}


# === Group CRUD ===

@app.get("/api/groups", response_model=List[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(Group).order_by(Group.sort_order, Group.id).all()


@app.post("/api/groups", response_model=GroupOut)
def create_group(data: GroupCreate, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    existing = db.query(Group).filter(Group.name == data.name).first()
    if existing:
        raise HTTPException(400, "分组名称已存在")
    group = Group(name=data.name, sort_order=data.sort_order, is_default=data.is_default)
    db.add(group)
    db.commit()
    db.refresh(group)
    if data.is_default:
        db.query(Group).filter(Group.id != group.id).update({"is_default": False})
        db.commit()
    return group


@app.put("/api/groups/{group_id}", response_model=GroupOut)
def update_group(group_id: int, data: GroupUpdate, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "分组不存在")
    if data.name is not None:
        existing = db.query(Group).filter(Group.name == data.name, Group.id != group_id).first()
        if existing:
            raise HTTPException(400, "分组名称已存在")
        group.name = data.name
    if data.sort_order is not None:
        group.sort_order = data.sort_order
    if data.is_default is not None and data.is_default:
        db.query(Group).filter(Group.id != group_id).update({"is_default": False})
        group.is_default = True
    db.commit()
    db.refresh(group)
    return group


@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "分组不存在")
    link_count = db.query(Link).filter(Link.group_id == group_id).count()
    if link_count > 0:
        raise HTTPException(400, f"该分组下还有 {link_count} 个链接，请先移动或删除它们")
    db.delete(group)
    db.commit()
    return {"ok": True}


@app.put("/api/groups/{group_id}/default")
def set_default_group(group_id: int, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "分组不存在")
    db.query(Group).filter(Group.id != group_id).update({"is_default": False})
    group.is_default = True
    db.commit()
    return {"ok": True}


@app.post("/api/generate")
def generate_index(default_group_id: int = 0, db: Session = Depends(get_db), _=Depends(require_auth_api)):
    """Generate the static index.html with all groups."""
    groups = db.query(Group).order_by(Group.sort_order, Group.id).all()
    if not groups:
        return {"ok": False, "error": "没有分组"}

    # Determine default group
    default_id = default_group_id
    if not default_id:
        default = db.query(Group).filter(Group.is_default == True).first()
        if default:
            default_id = default.id
        else:
            default_id = groups[0].id

    # Build links per group
    group_data = []
    for g in groups:
        links = db.query(Link).filter(Link.group_id == g.id, Link.enabled == True).order_by(Link.sort_order, Link.id).all()
        group_data.append({"group": g, "links": links})

    template = jinja_env.get_template("index_template.html")
    output = template.render(groups=group_data, default_group_id=default_id)

    # Write to output dir (mounted by icloud container)
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    # Also try to write via nginx path
    try:
        with open("/usr/share/nginx/html/index.html", "w", encoding="utf-8") as f:
            f.write(output)
    except OSError:
        pass

    return {"ok": True, "path": output_path, "default_group_id": default_id, "groups": len(groups)}


# === Protected Admin UI ===

@app.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Protected admin page."""
    token = get_token_from_request(request)
    if not token or not verify_session(token):
        return RedirectResponse(url="/admin/login")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sz41-nav 后台管理</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background: #0f172a; color: #e2e8f0; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; }
  input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; border-radius: 8px; padding: 8px 12px; width: 100%; }
  input:focus { outline: none; border-color: #3b82f6; }
  select { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; border-radius: 8px; padding: 8px 12px; width: 100%; }
  select:focus { outline: none; border-color: #3b82f6; }
  .btn { padding: 8px 16px; border-radius: 8px; cursor: pointer; border: none; font-size: 14px; }
  .btn-primary { background: #3b82f6; color: white; }
  .btn-primary:hover { background: #2563eb; }
  .btn-danger { background: #ef4444; color: white; }
  .btn-success { background: #22c55e; color: white; }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .btn-ghost { background: transparent; color: #94a3b8; border: 1px solid #334155; }
  .btn-ghost:hover { background: #1e293b; }
  .link-item { display: flex; align-items: center; gap: 12px; padding: 12px; background: #0f172a; border-radius: 8px; margin-bottom: 8px; cursor: grab; border: 1px solid #334155; }
  .link-item:hover { border-color: #3b82f6; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: rgba(59,130,246,0.15); color: #60a5fa; }
  .toast { position: fixed; bottom: 24px; right: 24px; padding: 12px 20px; border-radius: 8px; color: white; z-index: 100; animation: slideIn 0.3s; }
  @keyframes slideIn { from { transform: translateY(20px); opacity: 0; } to { opacity: 1; transform: none; } }
</style>
</head>
<body class="p-4">
<div class="max-w-4xl mx-auto">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold">🔗 sz41-nav 后台管理</h1>
    <div class="flex gap-2 items-center">
      <button class="btn btn-success" onclick="generateSite()">🔄 生成导航页</button>
      <button class="btn btn-ghost" onclick="handleLogout()">退出登录</button>
    </div>
  </div>

  <!-- Add Link Form -->
  <div class="card mb-6">
    <h2 class="text-lg font-semibold mb-4">＋ 添加链接</h2>
    <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
      <input type="url" id="new-url" placeholder="网址 https://..." onchange="autoFetchTitle()">
      <input type="text" id="new-title" placeholder="显示名称（自动获取）">
      <select id="new-group"></select>
      <input type="text" id="new-icon" placeholder="图标（可选）">
      <button class="btn btn-primary" onclick="addLink()">添加</button>
    </div>
  </div>

  <!-- Dynamic Link Panels -->
  <div id="group-panels"></div>

  <!-- Group Management -->
  <div class="card mt-6">
    <h2 class="text-lg font-semibold mb-4">📋 分组管理</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
      <input type="text" id="new-group-name" placeholder="新分组名称">
      <button class="btn btn-primary" onclick="addGroup()">添加分组</button>
      <button class="btn btn-success" onclick="generateSite()">🔄 生成导航页</button>
    </div>
    <div id="group-list"></div>
  </div>
</div>

<script>
let dragSrcId = null;
let groups = [];
let currentGroupId = 0;

async function api(method, path, body) {
  const base = '/admin';
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(base + path, opts);
  if (r.status === 401) {
    window.location.href = '/admin/login';
    return;
  }
  return r.json();
}

function toast(msg, type) {
  const t = document.createElement('div');
  t.className = `toast ${type === 'error' ? 'bg-red-500' : 'bg-green-500'}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

async function handleLogout() {
  await fetch('/admin/api/logout', {method: 'POST'});
  window.location.href = '/admin/login';
}

async function autoFetchTitle() {
  const url = document.getElementById('new-url').value;
  if (!url) return;
  const data = await api('GET', '/api/fetch-title?url='+encodeURIComponent(url));
  if (data && data.title) document.getElementById('new-title').value = data.title;
}

// === Groups ===
async function loadGroups() {
  groups = await api('GET', '/api/groups') || [];
  // Update the group select in add form
  const sel = document.getElementById('new-group');
  sel.innerHTML = groups.map(g => `<option value="${g.id}">${esc(g.name)}</option>`).join('');

  // Build group tabs + single panel
  const panelsEl = document.getElementById('group-panels');
  const firstGroup = groups.length > 0 ? groups[0].id : 0;
  let currentGroup = currentGroupId || firstGroup;

  // If current group no longer exists, reset
  if (!groups.find(g => g.id === currentGroup)) currentGroup = firstGroup;
  currentGroupId = currentGroup;

  // Tab bar
  panelsEl.innerHTML = `
    <div class="flex gap-1 mb-3 flex-wrap" id="group-tabs">
      ${groups.map(g => `
        <button class="tab-btn px-4 py-2 rounded-lg text-sm cursor-pointer border transition-all duration-200
          ${g.id === currentGroup
            ? 'bg-blue-500 text-white border-blue-500'
            : 'bg-transparent text-gray-400 border-gray-700 hover:border-blue-400 hover:text-gray-200'}"
          data-gid="${g.id}" onclick="switchGroupTab(${g.id})">
          ${esc(g.name)} ${g.is_default ? '<span class="text-xs ml-1 opacity-60">★</span>' : ''}
        </button>
      `).join('')}
    </div>
    <div id="active-panel" class="card">
      <div id="links-${currentGroup}" class="space-y-1"></div>
    </div>
  `;

  renderGroupManagement();
  return loadLinks();
}

// === Tab switching ===
function switchGroupTab(groupId) {
  currentGroupId = groupId;
  // Update tab styles
  document.querySelectorAll('#group-tabs .tab-btn').forEach(btn => {
    const gid = parseInt(btn.dataset.gid);
    if (gid === groupId) {
      btn.className = 'tab-btn px-4 py-2 rounded-lg text-sm cursor-pointer border bg-blue-500 text-white border-blue-500';
    } else {
      btn.className = 'tab-btn px-4 py-2 rounded-lg text-sm cursor-pointer border bg-transparent text-gray-400 border-gray-700 hover:border-blue-400 hover:text-gray-200';
    }
  });
  // Replace panel content
  document.getElementById('active-panel').innerHTML = `<div id="links-${groupId}" class="space-y-1"></div>`;
  loadLinks();
}

// === Links ===
async function loadLinks() {
  const links = await api('GET', '/api/links') || [];
  // Only load the currently active group's links
  const activeGroupId = currentGroupId || (groups.length > 0 ? groups[0].id : 0);
  const el = document.getElementById('links-' + activeGroupId);
  if (el) {
    const glinks = links.filter(l => (l.group_id === activeGroupId) || (l.group_id == null && l.group === ''));
    el.innerHTML = glinks.map(renderLink).join('');
  }
}

function renderLink(l) {
  return `<div class="link-item" draggable="true"
    data-id="${l.id}"
    ondragstart="onDragStart(event)" ondrop="onDrop(event)" ondragover="event.preventDefault()" ondragend="onDragEnd(event)">
    <span class="cursor-move text-gray-500 text-lg">⠿</span>
    <div class="flex-1">
      <strong>${esc(l.title)}</strong>
      <span class="text-gray-400 text-sm ml-2">${esc(l.url)}</span>
    </div>
    <span class="badge">${l.icon || ''}</span>
    <a href="${l.url}" target="_blank" class="text-blue-400 text-sm">打开</a>
    <button class="btn btn-sm btn-primary" onclick="editLink(${l.id})">编辑</button>
    <button class="btn btn-sm btn-danger" onclick="deleteLink(${l.id})">删除</button>
  </div>`;
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;'); }

async function addLink() {
  const url = document.getElementById('new-url').value;
  const title = document.getElementById('new-title').value;
  const group_id = parseInt(document.getElementById('new-group').value);
  const icon = document.getElementById('new-icon').value;
  if (!url) { toast('请输入网址', 'error'); return; }
  await api('POST', '/api/links', {url, title: title || null, group_id, icon: icon || ''});
  document.getElementById('new-url').value = '';
  document.getElementById('new-title').value = '';
  document.getElementById('new-icon').value = '';
  toast('已添加 ✅');
  loadLinks();
}

async function editLink(id) {
  const links = await api('GET', '/api/links');
  if (!links) return;
  const link = links.find(l => l.id === id);
  if (!link) return;
  const newTitle = prompt('显示名称:', link.title);
  if (newTitle === null) return;
  const newUrl = prompt('网址:', link.url);
  if (newUrl === null) return;
  const gid = prompt('分组ID (当前: ' + link.group_id + '):', link.group_id);
  if (gid === null) return;
  await api('PUT', '/api/links/'+id, {title: newTitle, url: newUrl, group_id: parseInt(gid)});
  toast('已更新 ✅');
  loadLinks();
}

async function deleteLink(id) {
  if (!confirm('删除这个链接？')) return;
  await api('DELETE', '/api/links/'+id);
  toast('已删除');
  loadLinks();
}

// === Drag & Drop ===
function onDragStart(ev) {
  dragSrcId = ev.currentTarget.dataset.id;
  ev.currentTarget.style.opacity = '0.4';
}

function onDragEnd(ev) {
  ev.currentTarget.style.opacity = '1';
}

function onDrop(ev) {
  ev.preventDefault();
  const targetEl = ev.currentTarget;
  const srcId = parseInt(dragSrcId);
  const tgtId = parseInt(targetEl.dataset.id);
  if (srcId === tgtId) return;
  const container = targetEl.parentElement;
  const items = [...container.querySelectorAll('[data-id]')];
  const linkIds = items.map(el => parseInt(el.dataset.id));
  const srcIdx = linkIds.indexOf(srcId);
  const tgtIdx = linkIds.indexOf(tgtId);
  linkIds.splice(srcIdx, 1);
  linkIds.splice(tgtIdx, 0, srcId);
  const reorderItems = linkIds.map((id, idx) => ({id, sort_order: idx * 10}));
  api('POST', '/api/links/reorder', {items: reorderItems}).then(() => {
    loadLinks();
    toast('排序已更新 ✅');
  });
}

// === Generate ===
async function generateSite() {
  const result = await api('POST', '/api/generate');
  if (result && result.ok) toast('导航页已生成 ✅');
  else toast('生成失败: ' + (result?.error || ''), 'error');
}

// === Group Management ===
function renderGroupManagement() {
  const el = document.getElementById('group-list');
  el.innerHTML = groups.map(g => `
    <div class="flex items-center gap-3 p-3 bg-[#0f172a] rounded-lg mb-2 border border-[#334155]">
      <span class="flex-1">
        <strong>${esc(g.name)}</strong>
        ${g.is_default ? '<span class="badge ml-2" style="background:#22c55e20;color:#22c55e">默认</span>' : ''}
        <span class="text-gray-500 text-sm ml-2">ID: ${g.id}</span>
      </span>
      <button class="btn btn-sm ${g.is_default ? 'btn-ghost' : 'btn-warning'}" onclick="setDefault(${g.id})" ${g.is_default ? 'disabled' : ''}>
        ${g.is_default ? '✓ 默认' : '设为默认'}
      </button>
      <button class="btn btn-sm btn-primary" onclick="renameGroup(${g.id}, '${esc(g.name)}')">重命名</button>
      <button class="btn btn-sm btn-danger" onclick="deleteGroup(${g.id})">删除</button>
    </div>
  `).join('');
}

async function addGroup() {
  const name = document.getElementById('new-group-name').value.trim();
  if (!name) { toast('请输入分组名称', 'error'); return; }
  await api('POST', '/api/groups', {name});
  document.getElementById('new-group-name').value = '';
  toast('分组已创建 ✅');
  await loadGroups();
}

async function renameGroup(id, oldName) {
  const name = prompt('新名称:', oldName);
  if (!name || name === oldName) return;
  await api('PUT', '/api/groups/' + id, {name});
  toast('已重命名 ✅');
  await loadGroups();
}

async function deleteGroup(id) {
  if (!confirm('确定删除这个分组？')) return;
  try {
    await api('DELETE', '/api/groups/' + id);
    toast('已删除');
    await loadGroups();
  } catch(e) {
    toast(e.message, 'error');
  }
}

async function setDefault(id) {
  await api('PUT', '/api/groups/' + id + '/default');
  toast('默认分组已更新 ✅');
  await loadGroups();
}

// Init
(async function() {
  const check = await fetch('/admin/api/check-auth');
  const state = await check.json();
  if (!state.authenticated) { window.location.href = '/admin/login'; return; }
  await loadGroups();
})();
</script>
</body>
</html>"""
    return html


@app.on_event("startup")
def startup():
    init_db()
