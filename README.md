# 儿童互动绘本生成系统技术文档

## 1. 项目概述

本项目是一个面向儿童互动阅读场景的 AI 绘本生成系统。用户在前端选择故事主题并通过“捏主角”组件生成主角特征后，后端会调用大语言模型生成剧情旁白、主角台词、中文绘图场景提示词、中文绘图动作提示词和两个下一步选项。用户每次点击选项或输入自定义选择，都会生成一个新的剧情节点，多个分支最终组成可回溯的“命运之树”。

图片生成部分接入 ComfyUI。当前正式代码使用基于角色卡的 Z-Image 工作流：先把用户输入整理成稳定的角色卡，再为每个会话生成一次角色定妆照，后续绘本页持续注入相同的角色设定，以降低角色漂移。仓库中同时保留了一套旧版基于 IPAdapter、OpenPose/ControlNet 的 legacy 工作流，用于对照或回退，但正式 FastAPI 接口不会调用它。

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
    ├── base_images/              # 每个 session 的角色定妆照
    ├── character_cards/          # 每个 session 的角色卡 JSON
    ├── temp/                     # 临时图片
    └── test_assets/              # 测试脚本输出
```

`data/`、`outputs/`、虚拟环境和缓存目录已加入 `.gitignore`。当前实际数据库路径由 `config.py` 统一指定为 `data/storybook.db`。

## 3. 模块职责

| 文件/目录 | 作用 |
| --- | --- |
| `frontend/index.html` | Vue 3 单页前端。包含故事主题选择、主角捏人、剧情阅读、图片展示、自定义选择和命运之树回溯。 |
| `src/storybook_app/main.py` | FastAPI 入口。定义 API 请求模型，协调 LLM、数据库、绘图流程，并挂载前端静态页面和 `/images` 图片目录。 |
| `src/storybook_app/config.py` | 集中管理项目路径、运行产物目录、LLM 配置和 ComfyUI 地址；导入时自动创建 `data/` 与 `outputs/` 子目录。 |
| `src/storybook_app/database.py` | SQLite 数据访问层。保存绘本会话、剧情节点、父子分支、绘图提示词、图片 URL 和选项 JSON。 |
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
| `character_base.json` | 正式调用 | 使用 Z-Image 模型生成角色定妆照。`image_engine.py` 会把节点 `4` 的正向提示词替换为 `CharacterCard.positive_prompt`，并设置节点 `7`、`9` 的随机种子，优先下载保存节点 `11` 的图片。 |
| `story_page.json` | 正式调用 | 使用 Z-Image 模型生成最终绘本页。`image_engine.py` 会把节点 `4` 的正向提示词替换为角色卡 + 当前页动作/场景组合后的中文提示词，并设置节点 `7`、`9` 的随机种子，优先下载保存节点 `14` 的图片。 |
| `pose.json` | 当前代码未调用 | 保留的实验/预留工作流。正式 `generate_full_story_page()` 只加载 `character_base.json` 和 `story_page.json`。 |

这一套工作流不依赖 IPAdapter 图像输入来保持角色，而是通过以下机制控制一致性：

```text
用户输入主角特征
  -> character_card.build_character_card()
  -> 保存 outputs/character_cards/character_card_{session_id}.json
  -> 首次渲染时生成 outputs/base_images/base_{session_id}.png
  -> 每页调用 build_story_page_prompt() 注入固定外貌、服装、配饰、主色
  -> 使用 workflows/zimage/story_page.json 生成最终绘本页
```

注意：当前定妆照主要作为会话视觉锚点和人工复查产物，正式 `story_page.json` 没有把该定妆照作为 LoadImage/IPAdapter 输入；角色延续主要靠角色卡提示词反复注入。

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
| `BASE_IMAGE_OUTPUT_DIR` | `outputs/base_images/` | 角色定妆照目录。 |
| `CHARACTER_CARD_OUTPUT_DIR` | `outputs/character_cards/` | 角色卡 JSON 目录。 |
| `TEMP_OUTPUT_DIR` | `outputs/temp/` | 临时图片目录。 |
| `LLM_API_KEY` | 环境变量优先 | 大语言模型 API Key。 |
| `LLM_BASE_URL` | 环境变量优先 | OpenAI 兼容 API 地址。 |
| `LLM_MODEL_NAME` | 环境变量优先 | 大模型名称。 |
| `COMFYUI_SERVER_ADDRESS` | 环境变量优先 | ComfyUI HTTP 服务地址。 |
| `COMFYUI_INPUT_DIR` | 环境变量优先 | ComfyUI 输入目录，当前正式 Z-Image 流程不依赖，主要兼容测试或旧逻辑。 |

## 7. API 接口

### 7.1 `POST /api/init_story_text`

创建新绘本会话并生成根节点文本。该接口只生成文字，不生成图片；前端收到 `page_id` 后会再调用 `/api/render_image`。

请求：

```json
{
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
  -> uuid.uuid4()
  -> generate_script_turn(child_features, opening_context, "开始冒险")
  -> create_storybook()
  -> add_page_node(parent_id=0, depth=0)
```

### 7.2 `POST /api/next_turn_text`

根据当前节点和用户选择生成新的剧情分支节点。

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
  -> rebuild_llm_context(parent_page_id)
  -> generate_script_turn(features, memory_list, user_choice)
  -> add_page_node(parent_id=parent_page_id, depth=父节点深度+1)
```

### 7.3 `POST /api/render_image`

为指定剧情节点生成绘本图片，并把图片 URL 写回数据库。

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
  -> generate_full_story_page(session_id, features, action_prompt, scene_prompt)
  -> outputs/temp/final_storybook_page.png 移动为 outputs/images/node_{page_id}.png
  -> update_page_image(page_id, image_url)
```

### 7.4 `GET /api/get_timeline/{session_id}`

获取某个绘本会话下的全部剧情节点，用于前端构建命运之树。

返回结构：

```json
{
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
      -> 若 base_{session_id}.png 不存在：
           使用 workflows/zimage/character_base.json 生成定妆照
      -> build_story_page_prompt(card, story_action, story_scene)
      -> 使用 workflows/zimage/story_page.json 生成 outputs/temp/final_storybook_page.png
  -> main.py 移动图片到 outputs/images/node_{page_id}.png
  -> 数据库写入 /images/node_{page_id}.png
```

### 8.3 角色一致性流程

```text
前端捏人/手动输入主角特征
  -> character_card.build_character_card()
      -> 提取 role / hair / clothes / accessories / colors
      -> 生成 positive_prompt / negative_prompt
  -> character_base.json 生成会话定妆照
  -> story_page.json 每页重复注入固定外貌、固定服装、固定配饰、固定主色
```

`character_card.py` 内部通过关键词表提取颜色、发型、服装和配饰。如果某类信息没有提取到，会使用保守默认描述，保证绘图提示词始终完整。

### 8.4 命运之树流程

```text
每次生成剧情节点
  -> pages.parent_id 记录父节点
  -> pages.depth 记录深度
  -> pages.options_json 保存下一步选项

前端点击“打开命运之树”
  -> GET /api/get_timeline/{session_id}
  -> 将扁平 nodes 组装成树
  -> 点击任意节点时恢复该节点旁白、台词、选项和图片
```

后端 `rebuild_llm_context(page_id)` 只沿当前分支回溯，不会把整棵树都塞给大模型。为了控制上下文长度，它最终保留全局设定和最近 3 条剧情记忆。

## 9. 数据库设计

当前数据库文件：`data/storybook.db`。

### 9.1 `storybooks` 表

| 字段 | 说明 |
| --- | --- |
| `session_id` | 绘本会话 ID，主键。 |
| `theme` | 用户选择的故事主题。 |
| `features` | 用户输入或前端捏人生成的主角特征。 |
| `create_time` | 创建时间。 |

### 9.2 `pages` 表

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

1. 选择故事主题：内置“魔法森林探险”“太空宇宙漫游”“深海寻宝奇遇”。
2. 主角捏人：可选择身份、脸部感觉、发型颜色、固定主色、服装、配饰、道具、鞋子和画风，并自动合成为 `child_features`。
3. 文字剧情：显示旁白和主角台词。
4. 图片展示：调用 `/api/render_image` 后显示 `/images/node_{page_id}.png`。
5. 选项推进：支持点击 LLM 给出的两个选项，也支持输入自定义选择。
6. 命运之树：读取所有节点后在前端组装树形结构，点击历史节点可恢复该节点剧情、图片和选项，再从该节点继续分支。

## 11. 测试与验证

### 11.1 角色卡函数

`tests/test_character_card.py` 当前主要重新导出正式模块函数，避免维护重复实现。后续可以补充 pytest 测试，例如：

- 输入“白色短发的小女孩”时是否识别出女孩和短发。
- 保存角色卡后是否能通过 `load_character_card()` 恢复。
- `build_story_page_prompt()` 是否包含固定服装和固定主色。

### 11.2 绘图链路脚本

`tests/test_image_engine.py` 是独立脚本，不经过 FastAPI。它会：

1. 使用固定主角特征生成角色卡。
2. 调用 `workflows/zimage/character_base.json` 生成测试定妆照。
3. 使用固定测试剧情调用 `workflows/zimage/story_page.json` 生成测试绘本页。
4. 输出到 `outputs/test_assets/`。

运行示例：

```bash
uv run python tests/test_image_engine.py
```

运行前必须确保 ComfyUI 已启动，并且相关模型、节点和工作流依赖可用。

## 12. 注意事项

1. 当前正式 FastAPI 绘图只调用 `workflows/zimage/character_base.json` 和 `workflows/zimage/story_page.json`。
2. `workflows/legacy/` 是旧版 IPAdapter/OpenPose/ControlNet 路线，保留但不参与当前正式流程。
3. `workflows/zimage/pose.json` 当前代码未调用，如果启用需要同步修改 `image_engine.py`。
4. 当前 Z-Image 流程的角色一致性主要依赖角色卡提示词，不是 IPAdapter 图像参考。
5. LLM 输出的 `story_scene` 和 `story_action` 必须是中文，不要回退到旧版英文提示词风格。
6. 同一个 `session_id` 的 `outputs/base_images/base_{session_id}.png` 已存在时，会跳过定妆照生成。
7. 重复渲染同一节点会覆盖 `outputs/images/node_{page_id}.png`，数据库中的 `image_url` 保持不变。
8. `outputs/temp/final_storybook_page.png` 是临时文件，生成成功后会被移动到最终图片目录。
9. 生产或答辩演示环境建议使用环境变量设置 `LLM_API_KEY`，不要把真实密钥提交到仓库。
10. 如果更换 ComfyUI 工作流节点编号，需要同步修改 `image_engine.py` 中注入提示词、设置种子和优先下载节点的逻辑。
