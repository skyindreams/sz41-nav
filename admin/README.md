# sz41-admin v2.0

sz41-nav 导航后台管理系统 — FastAPI + SQLite 多分组动态导航管理。

## 架构

```
sz41-admin/          ← 本仓库（FastAPI 后台管理系统）
├── app/
│   ├── main.py          # FastAPI 应用（内嵌管理 UI）
│   ├── models.py        # SQLAlchemy 数据模型（Group + Link）
│   ├── schemas.py       # Pydantic 请求/响应模型
│   ├── database.py      # SQLite 数据库连接
│   ├── fetcher.py       # 自动获取网页标题
│   ├── templates/       # Jinja2 导航页模板
│   └── static/          # Nginx 配置参考
├── data/                # SQLite 数据库（本地数据，不提交）
├── Dockerfile
├── docker-compose.yml
└── .env                 # 管理密码（不提交）

icloud/                ← 前端 Nginx + 静态资源（独立仓库）
├── icloud/             # CSS/JS/图标/字体
├── nginx.conf          # Nginx 配置（含 /admin/ 反向代理）
├── index.html          # 生成的导航页
└── output/             # 后台生成导航页输出
```

## 功能

- 🔐 **密码登录** — 单用户管理后台，Cookie 会话（7天有效）
- 🛡️ **安全防护** — 登录频率限制（5次失败封15分钟）、Secure Cookie、安全响应头
- 📁 **多分组管理** — 支持多个分组，可设置默认分组
- 🔗 **链接管理** — 添加/编辑/删除链接，自动获取网站标题
- 🎨 **图标选择** — 每个链接可指定不同图标
- 🔄 **拖拽排序** — 后台拖拽调整链接顺序
- 📄 **导航页生成** — 动态生成静态导航首页
- 🐳 **Docker 部署** — 非 root 运行

## 快速开始

### 1. 配置

```bash
cp .env.example .env
# 编辑 .env，设置管理密码
```

### 2. 启动

```bash
docker compose up -d
```

后台管理地址：`http://localhost:8901`
默认无数据，首次启动自动创建数据库。

### 3. 配合前端 Nginx

前端静态导航页（sz41-nav/icloud）配置反向代理：

```nginx
location /admin/ {
    proxy_pass http://sz41-admin:8901/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect http://sz41-admin:8901/ /admin/;
}
```

参考 `app/static/default.conf`。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/login` | 登录获取会话 |
| GET | `/api/check-auth` | 检查登录状态 |
| GET | `/api/links` | 获取链接列表 |
| POST | `/api/links` | 添加链接 |
| PUT | `/api/links/{id}` | 编辑链接 |
| DELETE | `/api/links/{id}` | 删除链接 |
| POST | `/api/links/reorder` | 拖拽排序 |
| GET | `/api/groups` | 获取分组列表 |
| POST | `/api/groups` | 添加分组 |
| PUT | `/api/groups/{id}` | 编辑分组 |
| DELETE | `/api/groups/{id}` | 删除分组 |
| POST | `/api/generate` | 生成静态导航页 |

## 技术栈

- **后端**: Python 3.11 + FastAPI + SQLAlchemy
- **数据库**: SQLite
- **前端**: 内嵌 HTML + Tailwind CSS（CDN）
- **模板**: Jinja2
- **容器**: Docker

## 许可

MIT
