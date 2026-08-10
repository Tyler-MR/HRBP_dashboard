# HRBP 招聘看板 — 新环境复现指南

## 一、环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+（Vite 5 要求） |
| MySQL（可选） | 仅电商/拼多多 BI 数据源需要，内网 192.168.16.40 |

## 二、克隆与安装

```bash
git clone git@github.com:Tyler-MR/HRBP_dashboard.git
cd HRBP_dashboard

# 后端依赖
cd backend
pip install -r requirements.txt

# 前端依赖
cd ../frontend
npm install
```

## 三、配置凭证（关键步骤）

```bash
# 1. 复制模板并填入真实值
cp backend/.env.example backend/.env

# 2. 编辑 backend/.env，填入：
#    - 钉钉 AppKey / AppSecret / AgentId（企业内部应用凭证）
#    - MySQL 连接信息（淘宝/拼多多 BI 数据源）
```

> `.env` 含敏感凭证，已被 `.gitignore` 排除，**不要**提交或分享。

## 四、启动

```bash
# 后端（main.py 无 __main__ 入口，必须用 uvicorn 启动）
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 前端（另开终端）
cd frontend
npm run dev
```

浏览器访问 http://127.0.0.1:3000

## 五、数据说明

| 数据 | 来源 | 说明 |
|------|------|------|
| 招聘漏斗/人力指标 | 钉钉多维表 API | 启动后自动同步（每5分钟），也可在页面点"同步"按钮 |
| 花名册/员工 | 钉钉智能人事 API | 同上，同步按钮同时触发 |
| 电商/拼多多 BI | MySQL（192.168.16.40） | 需与内网连通 |
| 产品团队 | 钉钉多维表 API | 同上 |

- `backend/recruitment.db`（SQLite）为本地缓存，由钉钉实时同步自动重建，**无需手动传递**。
- 首次启动后建议立即点击页面"同步"按钮拉取全量数据。

## 六、常见问题

- **后端无法连接钉钉**：检查 `.env` 凭证是否正确、服务器时间是否与北京时区一致（钉钉签名校验对时差敏感）。
- **MySQL 连不上**：确认新电脑与 192.168.16.40 网络互通（`ping 192.168.16.40`）。
- **端口被占用**：后端 8000 / 前端 3000 可分别通过 `--port` 修改。
