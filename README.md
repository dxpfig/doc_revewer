# doc_revewer - 文档审查系统

AI 驱动的文档审查工具，支持上传文档并根据可配置的标准进行智能审查。

## 功能特性

- **用户认证** - 支持管理员和普通用户角色
- **标准管理** - 管理员可创建和管理审查标准
- **规则管理** - 为每个标准配置多条审查规则
- **文档审查** - 支持 PDF 和 DOCX 格式文档审查
- **增量处理** - 支持大量规则和大文档的增量审查
- **结果查看** - 详细展示审查结果和不符合项
- **PDF 导出** - 导出审查报告为 PDF 格式

## 技术栈

### 前端
- React + TypeScript
- Vite
- React Router

### 后端
- FastAPI
- SQLAlchemy (SQLite)
- AgentScope (多智能体编排)
- ReportLab (PDF生成)

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/dxpfig/doc_revewer.git
cd doc_revewer
```

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
python main.py
```

后端服务将在 http://127.0.0.1:18000 启动

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端将在 http://localhost:5173 启动

### 4. 登录测试

- **管理员账号**: `admin` / `admin`
- **普通用户账号**: `user1` / `user1`

## 项目结构

```
doc_revewer/
├── backend/
│   ├── agents/          # AgentScope 智能体
│   ├── api/v1/         # FastAPI 接口
│   ├── db/             # 数据库
│   ├── models/         # 数据模型
│   ├── services/       # 业务逻辑
│   └── main.py         # 入口文件
├── frontend/
│   ├── src/            # React 源代码
│   └── public/         # 静态资源
└── CLAUDE.md           # 开发指南
```

## 环境变量

### 后端
- `AGENTSCOPE_STUDIO_URL` - AgentScope Studio 地址（可选）
- `AGENTSCOPE_TRACE_DIAG=1` - 启用追踪诊断（可选）

### 前端
- `VITE_API_BASE_URL` - 后端 API 地址（默认: http://127.0.0.1:18000/api/v1）

## API 文档

启动后端后访问 http://127.0.0.1:18000/docs 查看完整的 API 文档。

## 许可证

MIT License