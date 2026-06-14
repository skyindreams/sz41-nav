# sz41-nav

导航页 Docker 版，基于 skyindreams/icloud 静态导航页，v2.0 新增后台管理系统。

## 结构

```
sz41-nav/
├── icloud/              # 前端静态资源
├── admin/               # 后台管理系统（FastAPI + SQLite）
│   ├── app/
│   │   ├── main.py      # FastAPI 应用
│   │   ├── models.py    # 数据模型
│   │   ├── schemas.py   # 请求/响应模型
│   │   ├── templates/   # 导航页模板
│   │   └── ...
│   ├── Dockerfile
│   └── docker-compose.yml
├── index.html           # 生成的导航页
├── nginx.conf           # Nginx 配置（/admin/ 反向代理）
├── docker-compose.yml   # 前端 Nginx
└── Dockerfile
```

## v2.0 新功能

- 多分组动态导航管理
- 后台添加/编辑/删除链接
- 拖拽排序
- 自动获取网站标题
- 安全防护（频率限制、Secure Cookie、安全响应头）
- Docker 非 root 运行

详见 `admin/README.md`。
