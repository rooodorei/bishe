# 儿童互动绘本生成系统技术文档

## 1. 项目概述

本项目是一个面向儿童互动阅读场景的多用户 AI 绘本生成系统。用户可以在前端注册/登录，在自己的故事库中创建和管理多本互动绘本。每本绘本都有独立的故事标题、主题、主角特征和剧情树，用户可以随时进入某一本故事继续生成新分支。

创建故事时，用户在前端选择故事主题并通过“捏主角”组件生成主角特征。后端会调用大语言模型生成剧情旁白、主角台词、中文绘图场景提示词、中文绘图动作提示词和两个下一步选项。用户每次点击选项或输入自定义选择，都会生成一个新的剧情节点，多个分支最终组成可回溯的“剧情树”。

图片生成部分接入 ComfyUI。当前正式代码使用基于角色卡的 Z-Image 工作流：后端会把前端主角特征整理成稳定角色卡，并在每个绘本页提示词中注入同一份角色设定，以降低角色漂移。仓库中同时保留了一套旧版基于 IPAdapter、OpenPose/ControlNet 的 legacy 工作流，用于对照或回退，但正式 FastAPI 接口不会调用它。

## 2. 目录结构

```text
bishe/
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── frontend/
│   └── index.html
├── src/
│   ├── storybook.db              # 历史遗留数据库文件，当前配置不再使用
│   └── storybook_app/
│       ├── __init__.py
│       ├── main.py               # FastAPI 入口
│       ├── config.py             # 路径、LLM、ComfyUI 配置
│       ├── database.py           # SQLite 数据访问层
│       ├── llm_engine.py         # 剧情、台词、安全审核
│       ├── image_engine.py       # ComfyUI 绘图调度
│       └── character_card.py     # 角色卡与提示词构建
├── workflows/
│   ├── zimage/                   # 当前正式使用：角色卡 + Z-Image 工作流
│   │   ├── character_base.json   # 角色定妆照工作流
│   │   ├── story_page.json       # 绘本页工作流
│   │   └── pose.json             # 预留/实验工作流，当前代码未调用
│   └── legacy/                   # 旧版：IPAdapter + OpenPose/ControlNet 三阶段工作流
│       ├── workflow_stage1_base.json
│       ├── workflow_stage2_pose.json
│       └── workflow_stage3_final.json
├── tests/
│   ├── test_image_engine.py      # 独立验证绘图链路的脚本
│   └── test_character_card.py    # 角色卡函数重导出/测试辅助入口
├── data/                         # 运行时自动创建，保存当前 SQLite 数据库
└── outputs/                      # 运行时自动创建，保存生成结果
    ├── images/                   # 前端可访问的最终绘本页
    ├── character_cards/          # 每个 session 的角色卡 JSON
    ├── temp/                     # 临时图片
    └── test_assets/              # 测试脚本输出
```

`data/`、`outputs/`、虚拟环境和缓存目录已加入 `.gitignore`。当前实际数据库路径由 `config.py` 统一指定为 `data/storybook.db`。

## 3. 模块职责

| 文件/目录 | 作用 |
| --- | --- |
| `frontend/index.html` | Vue 3 单页前端。包含注册登录、故事库、多故事管理、故事主题选择、主角捏人、剧情阅读、图片展示、自定义选择和剧情树回溯。 |
| `src/storybook_app/main.py` | FastAPI 入口。定义用户认证、故事管理、剧情生成、图片生成和时间线查询 API，协调 LLM、数据库、绘图流程，并挂载前端静态页面和 `/images` 图片目录。 |
| `src/storybook_app/config.py` | 集中管理项目路径、运行产物目录、LLM 配置和 ComfyUI 地址；导入时自动创建 `data/` 与 `outputs/` 子目录。 |
| `src/storybook_app/database.py` | SQLite 数据访问层。保存用户账号、绘本故事、剧情节点、父子分支、绘图提示词、图片 URL 和选项 JSON。 |
| `src/storybook_app/llm_engine.py` | 调用 OpenAI 兼容接口。用 Director 生成剧情 JSON，用 Actor 生成主角台词，用 Critic 做儿童内容安全审核。 |
| `src/storybook_app/character_card.py` | 当前正式角色一致性模块。把用户主角特征转为结构化角色卡，并构建角色定妆照/绘本页提示词。 |
| `src/storybook_app/image_engine.py` | 当前正式绘图模块。加载 `workflows/zimage` 工作流，注入提示词和随机种子，提交 ComfyUI 并下载生成图片。 |
| `workflows/zimage/` | 当前正式绘图工作流目录，属于“角色卡 + 中文 Z-Image 提示词”路线。 |
| `workflows/legacy/` | 旧版三阶段工作流目录，属于“IPAdapter + OpenPose/ControlNet”路线，当前代码不调用。 |
| `tests/test_image_engine.py` | 不经过 FastAPI，直接测试角色卡、Z-Image 定妆照和绘本页生成链路。 |
| `tests/test_character_card.py` | 从正式角色卡模块重新导出函数，避免测试代码维护重复实现。 |

## 4. 两套 ComfyUI 工作流说明

代码和仓库中同时存在两类工作流，二者设计思路不同，不应混为一谈。

### 4.1 当前正式工作流：角色卡 + Z-Image

位置：`workflows/zimage/`

| 文件 | 当前状态 | 说明 |
| --- | --- | --- |
| `character_base.json` | 当前代码未调用 | 保留的实验/对照工作流，可用于单独生成角色设定图，但正式 FastAPI 绘图流程不再调用它。 |
| `story_page.json` | 正式调用 | 使用 Z-Image 模型生成最终绘本页。`image_engine.py` 会把节点 `4` 的正向提示词替换为角色卡 + 当前页动作/场景组合后的中文提示词，并设置节点 `7`、`9` 的随机种子，优先下载保存节点 `14` 的图片。 |
| `pose.json` | 当前代码未调用 | 保留的实验/预留工作流。正式 `generate_full_story_page()` 只加载 `story_page.json`。 |

这一套工作流不依赖 IPAdapter 图像输入来保持角色，而是通过以下机制控制一致性：

```text
用户输入主角特征
  -> character_card.build_character_card()
  -> 保存 outputs/character_cards/character_card_{session_id}.json
  -> 每页调用 build_story_page_prompt() 注入固定外貌、服装、配饰、主色
  -> 使用 workflows/zimage/story_page.json 生成最终绘本页
```

注意：当前正式 `story_page.json` 没有把角色设定图作为 LoadImage/IPAdapter 输入；角色延续主要靠角色卡提示词反复注入，因此正式接口不再生成定妆照。

### 4.2 旧版工作流：IPAdapter + OpenPose/ControlNet

位置：`workflows/legacy/`

| 文件 | 说明 |
| --- | --- |
| `workflow_stage1_base.json` | 使用 SD/Pixar 风格模型生成基础角色图。 |
| `workflow_stage2_pose.json` | 使用 OpenPose 预处理器生成姿态/草图相关图像。 |
| `workflow_stage3_final.json` | 使用 `LoadImage` 加载角色图和草图，使用 `IPAdapterAdvanced`、`IPAdapterModelLoader`、`CLIPVisionLoader` 以及 `ControlNetApplyAdvanced` 做角色参考和姿态控制。 |

旧版路线的核心是图像参考约束：先准备角色图，再通过 IPAdapter 引用角色视觉特征，并结合 OpenPose/ControlNet 控制姿态。这套工作流当前仅保留在仓库中，`image_engine.py` 不会读取 `workflows/legacy`，`config.py` 也把它标注为“保留用于对照或回退”。

## 5. 启动方式

### 5.1 安装依赖

项目使用 `uv` 管理依赖，`pyproject.toml` 中声明了主要依赖：`fastapi`、`uvicorn`、`openai`、`pydantic`、`requests`。

```bash
uv sync
```

### 5.2 配置外部服务

运行前需要准备：

1. 可访问的 OpenAI 兼容大模型接口，例如 DeepSeek/OpenAI 兼容网关。
2. 已启动的 ComfyUI HTTP 服务，默认地址为 `http://127.0.0.1:8188`。
3. ComfyUI 中安装并能加载工作流引用的模型，例如 Z-Image 相关模型、`qwen_3_4b.safetensors`、`ae.safetensors` 等。

推荐通过环境变量覆盖敏感配置：

```bash
export LLM_API_KEY="你的 API Key"
export LLM_BASE_URL="https://api.deepseek.com"
export LLM_MODEL_NAME="deepseek-v4-pro"
export COMFYUI_SERVER_ADDRESS="http://127.0.0.1:8188"
```

Windows PowerShell 示例：

```powershell
$env:LLM_API_KEY="你的 API Key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL_NAME="deepseek-v4-pro"
$env:COMFYUI_SERVER_ADDRESS="http://127.0.0.1:8188"
```

### 5.3 启动后端和前端

从项目根目录启动：

```bash
uv run uvicorn storybook_app.main:app --app-dir src --reload --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000/
```

首次进入页面需要注册或登录。登录后会进入“我的故事库”，用户可以创建多本绘本、进入已有故事继续分支创作，也可以删除自己的故事。

`main.py` 会把 `frontend/` 挂载到根路径，并把 `outputs/images/` 挂载为 `/images`。

## 6. 配置变量

| 变量 | 默认值/来源 | 作用 |
| --- | --- | --- |
| `PROJECT_ROOT` | 自动计算 | 项目根目录。 |
| `SRC_DIR` | `PROJECT_ROOT / "src"` | Python 源码目录。 |
| `FRONTEND_DIR` | `frontend/` | 前端静态页面目录。 |
| `WORKFLOW_DIR` | `workflows/` | ComfyUI 工作流根目录。 |
| `ZIMAGE_WORKFLOW_DIR` | `workflows/zimage/` | 当前正式 Z-Image 工作流目录。 |
| `LEGACY_WORKFLOW_DIR` | `workflows/legacy/` | 旧版 IPAdapter 工作流目录，当前正式流程不调用。 |
| `DATA_DIR` | `data/` | SQLite 数据库目录。 |
| `OUTPUT_DIR` | `outputs/` | 运行产物根目录。 |
| `IMAGE_OUTPUT_DIR` | `outputs/images/` | 最终绘本页目录，对应 URL 前缀 `/images`。 |
| `BASE_IMAGE_OUTPUT_DIR` | 已移除 | 旧版角色定妆照目录配置，当前正式流程不再生成定妆照。 |
| `CHARACTER_CARD_OUTPUT_DIR` | `outputs/character_cards/` | 角色卡 JSON 目录。 |
| `TEMP_OUTPUT_DIR` | `outputs/temp/` | 临时图片目录。 |
| `LLM_API_KEY` | 环境变量优先 | 大语言模型 API Key。 |
| `LLM_BASE_URL` | 环境变量优先 | OpenAI 兼容 API 地址。 |
| `LLM_MODEL_NAME` | 环境变量优先 | 大模型名称。 |
| `COMFYUI_SERVER_ADDRESS` | 环境变量优先 | ComfyUI HTTP 服务地址。 |
| `COMFYUI_INPUT_DIR` | 环境变量优先 | ComfyUI 输入目录，当前正式 Z-Image 流程不依赖，主要兼容测试或旧逻辑。 |

## 7. API 接口

除 `/api/register` 和 `/api/login` 外，业务接口都需要携带登录 token：

```http
Authorization: Bearer <token>
```

当前 token 保存在后端内存中，适合本地演示和毕业设计原型。服务重启后，用户需要重新登录。

### 7.1 `POST /api/register`

注册新用户并直接返回登录 token。

请求：

```json
{
  "username": "alice",
  "password": "123456"
}
```

返回：

```json
{
  "token": "登录token",
  "user": {
    "id": 1,
    "username": "alice"
  }
}
```

### 7.2 `POST /api/login`

用户登录。

请求：

```json
{
  "username": "alice",
  "password": "123456"
}
```

返回：

```json
{
  "token": "登录token",
  "user": {
    "id": 1,
    "username": "alice"
  }
}
```

### 7.3 `GET /api/me`

获取当前登录用户。

返回：

```json
{
  "user": {
    "id": 1,
    "username": "alice",
    "create_time": "2026-05-04 12:00:00"
  }
}
```

### 7.4 `POST /api/logout`

退出登录，后端会移除当前 token。

返回：

```json
{
  "ok": true
}
```

### 7.5 `GET /api/storybooks`

获取当前用户的全部绘本故事。

返回：

```json
{
  "stories": [
    {
      "session_id": "uuid",
      "user_id": 1,
      "title": "小红帽的森林冒险",
      "theme": "魔法森林探险",
      "features": "主角特征",
      "create_time": "2026-05-04 12:00:00",
      "update_time": "2026-05-04 12:10:00",
      "page_count": 3,
      "latest_page_id": 8
    }
  ]
}
```

### 7.6 `DELETE /api/storybooks/{session_id}`

删除当前用户的一本绘本及其剧情节点。接口会校验故事归属，不能删除其他用户的故事。

返回：

```json
{
  "ok": true
}
```

### 7.7 `POST /api/init_story_text`

创建新绘本故事并生成根节点文本。该接口只生成文字，不生成图片；前端收到 `page_id` 后会再调用 `/api/render_image`。

请求：

```json
{
  "title": "小红帽的森林冒险",
  "child_features": "白色短发，红色斗篷的小女孩，戴星星发卡",
  "theme": "魔法森林探险"
}
```

返回：

```json
{
  "session_id": "uuid",
  "page_id": 1,
  "narrator_text": "旁白文本",
  "actor_dialogue": "主角台词",
  "options": ["选项1", "选项2"]
}
```

主要调用链：

```text
init_story_text()
  -> get_current_user()
  -> uuid.uuid4()
  -> generate_script_turn(child_features, opening_context, "开始冒险")
  -> create_storybook(user_id=current_user.id)
  -> add_page_node(parent_id=0, depth=0)
```

### 7.8 `POST /api/next_turn_text`

根据当前节点和用户选择生成新的剧情分支节点。接口会校验 `session_id` 是否属于当前用户，并校验父节点是否属于该故事。

请求：

```json
{
  "session_id": "uuid",
  "parent_page_id": 1,
  "user_choice": "走进发光的小路"
}
```

返回：

```json
{
  "page_id": 2,
  "narrator_text": "新节点旁白",
  "actor_dialogue": "新节点台词",
  "options": ["选项1", "选项2"]
}
```

主要调用链：

```text
next_turn_text()
  -> ensure_story_owner(current_user.id, session_id)
  -> rebuild_llm_context(parent_page_id)
  -> generate_script_turn(features, memory_list, user_choice)
  -> add_page_node(parent_id=parent_page_id, depth=父节点深度+1)
```

### 7.9 `POST /api/render_image`

为指定剧情节点生成绘本图片，并把图片 URL 写回数据库。接口会通过节点所属故事校验当前用户权限。

请求：

```json
{
  "page_id": 2
}
```

返回：

```json
{
  "image_url": "/images/node_2.png"
}
```

主要调用链：

```text
render_image()
  -> get_page(page_id)
  -> get_storybook_info(session_id)
  -> ensure_story_owner(current_user.id, session_id)
  -> generate_full_story_page(session_id, features, action_prompt, scene_prompt)
  -> outputs/temp/final_storybook_page.png 移动为 outputs/images/node_{page_id}.png
  -> update_page_image(page_id, image_url)
```

### 7.10 `GET /api/get_timeline/{session_id}`

获取当前用户某个绘本故事下的全部剧情节点，用于前端构建剧情树。

返回结构：

```json
{
  "session_id": "uuid",
  "title": "小红帽的森林冒险",
  "theme": "魔法森林探险",
  "features": "主角特征",
  "nodes": [
    {
      "id": 1,
      "session_id": "uuid",
      "parent_id": 0,
      "depth": 0,
      "user_choice": "开始冒险",
      "narrator_text": "旁白",
      "actor_dialogue": "台词",
      "action_prompt": "动作提示词",
      "scene_prompt": "场景提示词",
      "image_url": "/images/node_1.png",
      "options_json": "[...]",
      "options": ["选项1", "选项2"]
    }
  ]
}
```

## 8. 核心业务流程

### 8.0 多用户故事管理流程

```text
用户注册/登录
  -> 后端生成内存 token
  -> 前端把 token 保存到 localStorage
  -> 后续业务请求携带 Authorization: Bearer <token>

用户进入故事库
  -> GET /api/storybooks
  -> 只返回当前用户 user_id 对应的绘本故事

用户创建新故事
  -> POST /api/init_story_text
  -> storybooks 写入 user_id / title / theme / features
  -> pages 写入根节点

用户删除故事
  -> DELETE /api/storybooks/{session_id}
  -> 校验故事归属
  -> 删除 storybooks 和对应 pages
```

当前认证实现定位为本地演示版：token 存在后端内存中，服务重启后失效；密码以随机盐 + SHA-256 摘要保存到 SQLite。若用于真实公网部署，建议替换为 JWT、服务端会话存储或成熟认证方案。

### 8.1 文本生成流程

`llm_engine.py` 把一轮剧情生成拆成三个模型角色：

```text
用户输入 child_features / theme / user_choice
  -> Director：生成标准 JSON
       - narrator_text
       - story_scene
       - story_action
       - options
  -> Actor：根据旁白和场景生成一句主角第一人称台词
  -> Critic：审核旁白和台词是否适合儿童
  -> database.add_page_node() 入库
```

Director 必须返回标准 JSON，且 `story_scene` 和 `story_action` 必须使用中文，以适配当前 Z-Image 中文提示词路线。角色外貌和服装不由 LLM 在每页重复描述，而是由 `character_card.py` 统一注入。

### 8.2 图片生成流程

```text
render_image(page_id)
  -> 读取页面 action_prompt / scene_prompt
  -> 读取绘本 features
  -> image_engine.generate_full_story_page()
      -> build_character_card(features)
      -> 保存角色卡 JSON
      -> build_story_page_prompt(card, story_action, story_scene)
      -> 使用 workflows/zimage/story_page.json 生成 outputs/temp/final_storybook_page.png
  -> main.py 移动图片到 outputs/images/node_{page_id}.png
  -> 数据库写入 /images/node_{page_id}.png
```

### 8.3 角色一致性流程

```text
前端捏人/手动输入主角特征
  -> character_card.build_character_card()
      -> 保留完整角色卡原文 raw_features
      -> 提取 role / hair / clothes / accessories / colors
      -> 生成角色卡提示词字段
  -> story_page.json 每页注入一份精简提示词：角色卡原文 + 简短一致性约束 + 当前动作 + 当前场景
```

`character_card.py` 内部通过关键词表提取颜色、发型、服装和配饰。如果某类信息没有提取到，会使用保守默认描述，保证绘图提示词始终完整。当前正式绘本页流程不会再额外生成角色定妆照。

### 8.4 剧情树流程

```text
每次生成剧情节点
  -> pages.parent_id 记录父节点
  -> pages.depth 记录深度
  -> pages.options_json 保存下一步选项

前端点击“打开剧情树”
  -> GET /api/get_timeline/{session_id}
  -> 后端校验当前用户是否拥有该故事
  -> 将扁平 nodes 组装成树
  -> 点击任意节点时恢复该节点旁白、台词、选项和图片
```

后端 `rebuild_llm_context(page_id)` 只沿当前分支回溯，不会把整棵树都塞给大模型。为了控制上下文长度，它最终保留全局设定和最近 3 条剧情记忆。

## 9. 数据库设计

当前数据库文件：`data/storybook.db`。

### 9.1 `users` 表

| 字段 | 说明 |
| --- | --- |
| `id` | 用户 ID，自增主键。 |
| `username` | 用户名，唯一。 |
| `password_hash` | 随机盐 + SHA-256 生成的密码摘要。 |
| `create_time` | 用户创建时间。 |

### 9.2 `storybooks` 表

| 字段 | 说明 |
| --- | --- |
| `session_id` | 绘本会话 ID，主键。 |
| `user_id` | 所属用户 ID。 |
| `title` | 故事标题，用户创建故事时填写；为空时使用“主题 + 绘本”。 |
| `theme` | 用户选择的故事主题。 |
| `features` | 用户输入或前端捏人生成的主角特征。 |
| `create_time` | 创建时间。 |
| `update_time` | 最近更新时间；新增剧情节点或更新图片时刷新。 |

### 9.3 `pages` 表

| 字段 | 说明 |
| --- | --- |
| `id` | 剧情节点 ID，自增主键。 |
| `session_id` | 所属绘本会话 ID。 |
| `parent_id` | 父节点 ID，根节点为 `0`。 |
| `depth` | 节点深度，根节点为 `0`。 |
| `user_choice` | 用户进入该节点时做出的选择。 |
| `narrator_text` | 旁白文本。 |
| `actor_dialogue` | 主角第一人称台词。 |
| `action_prompt` | LLM 生成的中文动作绘图提示词。 |
| `scene_prompt` | LLM 生成的中文场景绘图提示词。 |
| `image_url` | 最终图片 URL，例如 `/images/node_2.png`。 |
| `options_json` | 下一步选项列表的 JSON 字符串。 |

## 10. 前端功能说明

`frontend/index.html` 使用 Vue 3 CDN 实现，无需额外构建步骤。

主要功能：

1. 用户注册/登录：前端调用 `/api/register`、`/api/login`，登录 token 保存到 `localStorage.storybook_token`。
2. 故事库：登录后展示当前用户的所有故事，支持创建、进入和删除。
3. 多故事管理：每个用户可以创建多本绘本，每本绘本独立保存标题、主题、主角特征和剧情树。
4. 选择故事主题：内置“魔法森林探险”“太空宇宙漫游”“深海寻宝奇遇”。
5. 主角捏人：可选择身份、脸部感觉、发型颜色、固定主色、服装、配饰、道具、鞋子和画风，并自动合成为 `child_features`。
6. 文字剧情：显示旁白和主角台词。
7. 图片展示：调用 `/api/render_image` 后显示 `/images/node_{page_id}.png`。
8. 选项推进：支持点击 LLM 给出的两个选项，也支持输入自定义选择。
9. 剧情树：读取当前故事的所有节点后在前端组装树形结构，点击历史节点可恢复该节点剧情、图片和选项，再从该节点继续分支。

## 11. 测试与验证

### 11.1 角色卡函数

`tests/test_character_card.py` 当前主要重新导出正式模块函数，避免维护重复实现。后续可以补充 pytest 测试，例如：

- 输入“白色短发的小女孩”时是否识别出女孩和短发。
- 保存角色卡后是否能通过 `load_character_card()` 恢复。
- `build_story_page_prompt()` 是否包含固定服装和固定主色。

### 11.2 绘图链路脚本

`tests/test_image_engine.py` 是独立脚本，不经过 FastAPI。它会：

1. 使用固定主角特征生成角色卡。
2. 使用固定测试剧情调用 `workflows/zimage/story_page.json` 生成测试绘本页。
3. 输出到 `outputs/test_assets/`。

运行示例：

```bash
uv run python tests/test_image_engine.py
```

运行前必须确保 ComfyUI 已启动，并且相关模型、节点和工作流依赖可用。

## 12. 部署与打包

本项目不是单纯的前端页面，而是一个“FastAPI 后端 + Vue CDN 静态前端 + SQLite 数据库 + 外部 LLM 服务 + 外部 ComfyUI 服务”的组合应用。因此给别人部署运行时，需要同时考虑 Python 服务、模型 API 配置、ComfyUI 环境和工作流文件。

### 12.1 最推荐：源码包/压缩包部署

适合答辩演示、同学复现、服务器部署和局域网共享。把仓库整体交付给对方，对方按下面步骤运行。

#### 交付内容

必须包含：

```text
README.md
pyproject.toml
uv.lock
frontend/
src/
workflows/zimage/
workflows/legacy/      # 可选保留，用于说明旧版 IPAdapter 工作流
```

不建议打包运行时产物：

```text
.venv/
__pycache__/
.pytest_cache/
data/storybook.db
outputs/
```

其中 `data/` 和 `outputs/` 会在程序启动时自动创建。

#### 部署步骤

1. 安装 Python 和 uv。

当前 `pyproject.toml` 写的是 `requires-python = ">=3.14"`。如果对方环境没有 Python 3.14，需要先安装匹配版本，或者根据实际兼容性把项目 Python 版本约束调整为更容易安装的版本。

2. 在项目根目录安装依赖。

```bash
uv sync
```

3. 配置环境变量。

Windows PowerShell：

```powershell
$env:LLM_API_KEY="你的 API Key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL_NAME="deepseek-v4-pro"
$env:COMFYUI_SERVER_ADDRESS="http://127.0.0.1:8188"
```

Linux/macOS：

```bash
export LLM_API_KEY="你的 API Key"
export LLM_BASE_URL="https://api.deepseek.com"
export LLM_MODEL_NAME="deepseek-v4-pro"
export COMFYUI_SERVER_ADDRESS="http://127.0.0.1:8188"
```

4. 启动 ComfyUI。

对方机器上需要单独部署 ComfyUI，并确保 `workflows/zimage/story_page.json` 中引用的模型、节点和自定义插件都已经安装。当前正式流程使用的是角色卡 + Z-Image 工作流，不是 legacy 目录下的 IPAdapter 工作流。

5. 启动本项目。

```bash
uv run uvicorn storybook_app.main:app --app-dir src --host 0.0.0.0 --port 8000
```

本机访问：

```text
http://127.0.0.1:8000/
```

局域网其他设备访问：

```text
http://部署机器IP:8000/
```

如果给别人使用，通常只需要把地址发给对方，不需要每个人都安装项目。

### 12.2 服务器部署

适合把系统部署到一台固定机器上，多人通过浏览器访问。

推荐结构：

```text
浏览器
  -> FastAPI/uvicorn 本项目，端口 8000
      -> LLM OpenAI 兼容接口
      -> ComfyUI HTTP 服务，端口 8188
          -> 本地 GPU 和绘图模型
```

启动命令示例：

```bash
uv run uvicorn storybook_app.main:app --app-dir src --host 0.0.0.0 --port 8000
```

生产环境可以在前面加 Nginx/Caddy 做反向代理和 HTTPS，也可以用系统服务或进程管理工具保持 uvicorn 和 ComfyUI 常驻运行。

部署时要注意：

1. `LLM_API_KEY` 不要写死在代码中，建议只放在服务器环境变量里。
2. `outputs/images/` 会持续增长，需要定期清理或做存储策略。
3. SQLite 适合演示和小规模使用；如果多人高并发使用，建议后续迁移到 PostgreSQL/MySQL。
4. ComfyUI 绘图通常需要 GPU，完整模型体积很大，不适合直接放进普通 Python 应用包。
5. 当前 FastAPI 挂载的是本地 `frontend/index.html`，前端不需要单独构建。

### 12.3 Docker 部署思路

可以把本项目后端做成 Docker 镜像，但不建议把 ComfyUI、模型权重和本项目强行塞进同一个镜像。更合理的方式是：

```text
容器 A：storybook_app，本项目 FastAPI + 前端静态页
容器 B 或宿主机：ComfyUI + GPU + 模型
外部服务：LLM API
```

本项目容器需要暴露 `8000` 端口，并通过环境变量连接 ComfyUI：

```bash
COMFYUI_SERVER_ADDRESS=http://comfyui:8188
```

如果 ComfyUI 运行在宿主机，Windows/macOS Docker Desktop 通常可以使用：

```bash
COMFYUI_SERVER_ADDRESS=http://host.docker.internal:8188
```

Linux 服务器上则建议使用 Docker 网络、宿主机网络，或直接填写宿主机可访问 IP。

容器化时应把运行数据挂载为 volume：

```text
/app/data
/app/outputs
```

这样重新创建容器时不会丢失数据库和生成图片。

### 12.4 打包成桌面应用的可行方案

如果希望“像应用程序一样双击运行”，可以做桌面壳，但要明确：本项目真正重的部分是 ComfyUI 和绘图模型，完整打进单个 exe 通常不现实。更推荐下面两种方式。

#### 方案 A：轻量桌面启动器

用 PyInstaller、Tauri 或 Electron 做一个启动器，负责：

1. 启动 FastAPI 后端。
2. 打开内置浏览器窗口或系统浏览器访问 `http://127.0.0.1:8000/`。
3. 检查 ComfyUI 是否运行。
4. 提示用户填写 LLM API Key 和 ComfyUI 地址。

这种方式的应用体积较小，适合交付给已经安装好 ComfyUI 的用户。

#### 方案 B：完整离线整合包

把以下内容放在一个发行目录中：

```text
storybook-app/
  app/                  # 本项目源码或 PyInstaller 后端程序
  python/               # 可选：内置 Python 运行时
  comfyui/              # ComfyUI 程序
  models/               # Z-Image 等模型权重
  start.bat             # 一键启动脚本
  README_DEPLOY.md      # 给最终用户的部署说明
```

启动脚本依次启动 ComfyUI 和本项目后端，再打开浏览器。这个方式对用户最友好，但体积可能达到几十 GB，且需要处理显卡驱动、CUDA/PyTorch、模型授权和插件版本问题。

### 12.5 Windows 一键启动脚本示例

如果只是给同学或老师演示，可以提供一个 `start.bat`，让对方在已经配置好 uv、Python 和 ComfyUI 的前提下一键启动本项目。

示例内容：

```bat
@echo off
set LLM_API_KEY=你的 API Key
set LLM_BASE_URL=https://api.deepseek.com
set LLM_MODEL_NAME=deepseek-v4-pro
set COMFYUI_SERVER_ADDRESS=http://127.0.0.1:8188

uv run uvicorn storybook_app.main:app --app-dir src --host 127.0.0.1 --port 8000
```

更安全的做法是不要把真实 API Key 写进脚本，而是让用户在系统环境变量中配置。

### 12.6 推荐交付路线

对于当前项目，最稳妥的交付路线是：

1. 代码仓库或压缩包交付本项目。
2. README 中明确 Python、uv、LLM API、ComfyUI、Z-Image 模型和工作流依赖。
3. 演示机提前安装好 ComfyUI 和模型。
4. 用 `uv run uvicorn ... --host 0.0.0.0 --port 8000` 启动后端。
5. 其他人通过浏览器访问，不要求他们安装 Python 或模型。

如果一定要做成应用程序，建议先做“桌面启动器 + 外部 ComfyUI”的轻量版本；只有在需要完全离线交付时，再考虑包含 ComfyUI 和模型的完整整合包。

## 13. 注意事项

1. 当前正式 FastAPI 绘图只调用 `workflows/zimage/character_base.json` 和 `workflows/zimage/story_page.json`。
2. `workflows/legacy/` 是旧版 IPAdapter/OpenPose/ControlNet 路线，保留但不参与当前正式流程。
3. `workflows/zimage/pose.json` 当前代码未调用，如果启用需要同步修改 `image_engine.py`。
4. 当前 Z-Image 流程的角色一致性主要依赖角色卡提示词，不是 IPAdapter 图像参考。
5. LLM 输出的 `story_scene` 和 `story_action` 必须是中文，不要回退到旧版英文提示词风格。
6. 当前正式流程不再生成 `outputs/base_images/base_{session_id}.png` 角色定妆照。
7. 重复渲染同一节点会覆盖 `outputs/images/node_{page_id}.png`，数据库中的 `image_url` 保持不变。
8. `outputs/temp/final_storybook_page.png` 是临时文件，生成成功后会被移动到最终图片目录。
9. 生产或答辩演示环境建议使用环境变量设置 `LLM_API_KEY`，不要把真实密钥提交到仓库。
10. 如果更换 ComfyUI 工作流节点编号，需要同步修改 `image_engine.py` 中注入提示词、设置种子和优先下载节点的逻辑。
