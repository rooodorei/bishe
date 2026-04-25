# 儿童互动绘本生成系统技术文档

## 1. 项目概述

本项目是一个可交互儿童绘本生成系统。用户输入主角特征和故事主题后，后端调用大语言模型生成剧情、旁白、主角台词和下一步选项；用户每次选择都会形成新的剧情节点，最终组成“命运之树”。当用户请求渲染图片时，系统使用角色卡机制固定主角形象，并调用 ComfyUI 的 Z-Image 工作流生成绘本页。

## 2. 重构后的目录结构

```text
bishe/
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── frontend/
│   └── index.html
├── src/
│   └── storybook_app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── llm_engine.py
│       ├── image_engine.py
│       └── character_card.py
├── workflows/
│   ├── zimage/
│   │   ├── character_base.json
│   │   ├── story_page.json
│   │   └── pose.json
│   └── legacy/
│       ├── workflow_stage1_base.json
│       ├── workflow_stage2_pose.json
│       └── workflow_stage3_final.json
├── tests/
│   ├── test_image_engine.py
│   └── test_character_card.py
├── data/
│   └── storybook.db
└── outputs/
    ├── images/
    ├── base_images/
    ├── character_cards/
    ├── temp/
    └── test_assets/
```

`data/` 和 `outputs/` 是运行产物目录，已加入 `.gitignore`。

## 3. 模块职责

| 文件/目录 | 作用 |
| --- | --- |
| `src/storybook_app/main.py` | FastAPI 入口，定义接口、请求模型、图片保存与静态资源服务。 |
| `src/storybook_app/database.py` | SQLite 数据库读写，保存绘本、节点、图片 URL 和分支关系。 |
| `src/storybook_app/llm_engine.py` | 调用大模型生成剧情 JSON、台词，并做儿童内容安全审核。 |
| `src/storybook_app/character_card.py` | 正式角色卡模块，提取主角发型、服装、颜色、配饰，生成一致性提示词。 |
| `src/storybook_app/image_engine.py` | 绘图模块，加载 ComfyUI 工作流，注入提示词和随机种子，下载图片。 |
| `src/storybook_app/config.py` | 大模型、ComfyUI、项目路径和产物路径配置。 |
| `frontend/index.html` | 前端页面，负责创建故事、选择剧情、请求图片和展示命运之树。 |
| `workflows/zimage/character_base.json` | 当前正式使用的角色定妆照工作流。 |
| `workflows/zimage/story_page.json` | 当前正式使用的绘本页工作流。 |
| `workflows/legacy/` | 旧版三阶段工作流，当前正式流程不调用。 |
| `tests/` | 测试和独立验证脚本。 |

## 4. 启动方式

推荐从项目根目录启动：

```bash
uvicorn storybook_app.main:app --app-dir src --reload
```

启动后访问：

```text
http://127.0.0.1:8000/
```

## 5. 配置变量 `config.py`

| 变量 | 作用 |
| --- | --- |
| `PROJECT_ROOT` | 项目根目录。 |
| `FRONTEND_DIR` | 前端目录 `frontend/`。 |
| `WORKFLOW_DIR` | 工作流根目录 `workflows/`。 |
| `ZIMAGE_WORKFLOW_DIR` | 当前正式 Z-Image 工作流目录。 |
| `DATA_DIR` | 数据目录 `data/`。 |
| `OUTPUT_DIR` | 运行产物目录 `outputs/`。 |
| `IMAGE_OUTPUT_DIR` | 最终图片目录 `outputs/images/`。 |
| `BASE_IMAGE_OUTPUT_DIR` | 角色定妆照目录 `outputs/base_images/`。 |
| `CHARACTER_CARD_OUTPUT_DIR` | 角色卡目录 `outputs/character_cards/`。 |
| `TEMP_OUTPUT_DIR` | 临时图片目录 `outputs/temp/`。 |
| `LLM_API_KEY` | 大语言模型 API Key，优先读取环境变量。 |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址。 |
| `LLM_MODEL_NAME` | 大模型名称。 |
| `COMFYUI_SERVER_ADDRESS` | ComfyUI 服务地址。 |
| `COMFYUI_INPUT_DIR` | ComfyUI 输入目录，主要兼容旧逻辑或测试脚本。 |

## 6. API 接口

### `POST /api/init_story_text`

创建新绘本并生成开局文本。

请求：

```json
{"child_features":"白色短发，红色斗篷的小女孩","theme":"魔法森林探险"}
```

返回：

```json
{"session_id":"uuid","page_id":1,"narrator_text":"旁白","actor_dialogue":"台词","options":["选项1","选项2"]}
```

调用顺序：

```text
init_story_text()
  -> uuid.uuid4()
  -> generate_script_turn(child_features, opening_context, "开始冒险")
  -> create_storybook()
  -> add_page_node()
```

### `POST /api/next_turn_text`

根据用户选择生成下一幕剧情。

请求：

```json
{"session_id":"uuid","parent_page_id":1,"user_choice":"走进发光的小路"}
```

调用顺序：

```text
next_turn_text()
  -> rebuild_llm_context(parent_page_id)
  -> generate_script_turn(features, memory_list, user_choice)
  -> add_page_node()
```

### `POST /api/render_image`

为指定剧情节点生成绘本图片。

请求：

```json
{"page_id":2}
```

返回：

```json
{"image_url":"/images/node_2.png"}
```

调用顺序：

```text
render_image()
  -> get_page(page_id)
  -> get_storybook_info(session_id)
  -> generate_full_story_page(session_id, features, action_prompt, scene_prompt)
  -> 移动 outputs/temp/final_storybook_page.png 到 outputs/images/node_{page_id}.png
  -> update_page_image()
```

### `GET /api/get_timeline/{session_id}`

获取当前绘本所有剧情节点，用于展示命运之树。

调用顺序：

```text
get_timeline()
  -> get_storybook_info(session_id)
  -> get_all_nodes(session_id)
```

## 7. 核心工作流程

### 文本生成

```text
用户输入 child_features/theme/user_choice
  -> llm_engine.generate_script_turn()
  -> 导演生成 JSON
  -> 演员生成主角台词
  -> 审核员 PASS/REJECT
  -> database.add_page_node()
```

LLM 返回结构：

```json
{"narrator_text":"旁白","story_scene":"中文场景提示词","story_action":"中文动作提示词","options":["选项1","选项2"],"actor_dialogue":"主角台词"}
```

### 图片生成

```text
render_image()
  -> image_engine.generate_full_story_page()
      -> build_character_card(child_features)
      -> 保存角色卡到 outputs/character_cards/
      -> 若无定妆照，使用 workflows/zimage/character_base.json 生成 outputs/base_images/base_{session_id}.png
      -> build_story_page_prompt(card, story_action, story_scene)
      -> 使用 workflows/zimage/story_page.json 生成 outputs/temp/final_storybook_page.png
  -> 保存最终图到 outputs/images/node_{page_id}.png
```

### 角色一致性

```text
child_features
  -> CharacterCard
  -> card.positive_prompt 生成定妆照
  -> build_story_page_prompt() 注入每页绘图
  -> 保持同一角色、同一发型、同一服装、同一配色
```

## 8. 数据库

数据库文件：`data/storybook.db`。

`storybooks` 表：`session_id`、`theme`、`features`、`create_time`。

`pages` 表：`id`、`session_id`、`parent_id`、`depth`、`user_choice`、`narrator_text`、`actor_dialogue`、`action_prompt`、`scene_prompt`、`image_url`、`options_json`。

`rebuild_llm_context(page_id)` 会沿 `parent_id` 回溯到根节点，构造给 LLM 的上下文，并只保留全局设定和最近 3 条剧情。

## 9. 注意事项

1. 正式绘图只调用 `workflows/zimage/character_base.json` 和 `workflows/zimage/story_page.json`。
2. LLM 输出的 `story_scene` 和 `story_action` 是中文，以适配 Z-Image。
3. 主角形象由 `character_card.py` 统一注入，保证同一发型、服装、配色。
4. `outputs/base_images/base_{session_id}.png` 已存在时会跳过定妆照生成。
5. 重复渲染同一节点会覆盖 `outputs/images/node_{page_id}.png`。
6. 生产环境建议通过环境变量设置 `LLM_API_KEY`，不要把真实密钥提交到仓库。
