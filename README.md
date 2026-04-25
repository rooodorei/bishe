# 儿童互动绘本生成系统技术文档

## 1. 项目概述

本项目是一个可交互儿童绘本生成系统。用户输入主角特征和故事主题后，后端调用大语言模型生成剧情、旁白、主角台词和下一步选项；用户的每次选择都会形成新的剧情节点，最终组成“命运之树”。当用户请求渲染图片时，系统使用角色卡机制固定主角形象，并调用 ComfyUI 的 Z-Image 工作流生成绘本页。

## 2. 模块职责

| 文件 | 作用 |
| --- | --- |
| `src/main.py` | FastAPI 入口，定义接口、请求模型、图片保存与静态资源服务。 |
| `src/database.py` | SQLite 数据库读写，保存绘本、节点、图片 URL 和分支关系。 |
| `src/llm_engine.py` | 调用大模型生成剧情 JSON、台词，并做儿童内容安全审核。 |
| `src/character_card.py` | 正式角色卡模块，提取主角发型、服装、颜色、配饰，生成一致性提示词。 |
| `src/image_engine.py` | 绘图模块，加载 ComfyUI 工作流，注入提示词和随机种子，下载图片。 |
| `src/config.py` | 大模型和 ComfyUI 配置。 |
| `src/index.html` | 前端页面，负责创建故事、选择剧情、请求图片和展示命运之树。 |
| `src/TEST_workflow_character_base.json` | 当前正式使用的角色定妆照工作流。 |
| `src/TEST_workflow_story_page.json` | 当前正式使用的绘本页工作流。 |

旧版 `workflow_stage1_base.json`、`workflow_stage2_pose.json`、`workflow_stage3_final.json` 当前正式流程不再调用。

## 3. 配置变量 `src/config.py`

| 变量 | 作用 |
| --- | --- |
| `LLM_API_KEY` | 大语言模型 API Key。 |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址。 |
| `LLM_MODEL_NAME` | 大模型名称。 |
| `COMFYUI_SERVER_ADDRESS` | ComfyUI 服务地址，默认 `http://127.0.0.1:8188`。 |
| `COMFYUI_INPUT_DIR` | ComfyUI 输入目录，当前主要保留兼容旧逻辑。 |

## 4. API 接口 `src/main.py`

### 全局变量

| 名称 | 作用 |
| --- | --- |
| `app` | FastAPI 应用实例。 |
| `IMAGE_DIR` | 最终图片目录，值为 `images`。 |

启动顺序：

```text
加载 main.py -> 创建 app -> init_db() -> 创建 images 目录 -> 注册接口 -> 挂载静态文件
```

### 请求模型

| 模型 | 字段 | 作用 |
| --- | --- | --- |
| `InitRequest` | `child_features` | 主角特征。 |
| `InitRequest` | `theme` | 故事主题。 |
| `NextTurnRequest` | `session_id` | 绘本会话 ID。 |
| `NextTurnRequest` | `parent_page_id` | 当前父节点 ID。 |
| `NextTurnRequest` | `user_choice` | 用户选择。 |
| `RenderRequest` | `page_id` | 需要生成图片的节点 ID。 |

### `POST /api/init_story_text`

作用：创建新绘本并生成开局文本。

请求：

```json
{"child_features":"白色短发，红色斗篷的小女孩","theme":"魔法森林探险"}
```

返回：

```json
{"session_id":"uuid","page_id":1,"narrator_text":"旁白","actor_dialogue":"台词","options":["选项1","选项2"]}
```

关键变量：`session_id` 新会话 ID；`opening_context` 初始上下文；`turn_data` LLM 生成结果；`page_id` 根节点 ID。

调用顺序：

```text
前端 -> init_story_text()
  -> uuid.uuid4()
  -> generate_script_turn(child_features, opening_context, "开始冒险")
  -> create_storybook()
  -> add_page_node()
  -> 返回开局文本
```

### `POST /api/next_turn_text`

作用：根据用户选择生成下一幕剧情。

请求：

```json
{"session_id":"uuid","parent_page_id":1,"user_choice":"走进发光的小路"}
```

返回：

```json
{"page_id":2,"narrator_text":"旁白","actor_dialogue":"台词","options":["选项1","选项2"]}
```

关键变量：`features` 主角特征；`memory_list` 上下文记忆；`current_path` 当前分支路径；`depth` 新节点深度。

调用顺序：

```text
前端 -> next_turn_text()
  -> rebuild_llm_context(parent_page_id)
  -> generate_script_turn(features, memory_list, user_choice)
  -> add_page_node()
  -> 返回新节点文本
```

### `POST /api/render_image`

作用：为指定剧情节点生成绘本图片。

请求：

```json
{"page_id":2}
```

返回：

```json
{"image_url":"/images/node_2.png"}
```

关键变量：`page` 当前节点；`book` 当前绘本；`img_path` 临时图片路径；`final_img_path` 最终图片路径；`image_url` 前端访问路径。

调用顺序：

```text
前端 -> render_image()
  -> get_page(page_id)
  -> get_storybook_info(session_id)
  -> generate_full_story_page(session_id, features, action_prompt, scene_prompt)
  -> 重命名 final_storybook_page.png 为 images/node_{page_id}.png
  -> update_page_image()
  -> 返回 image_url
```

### `GET /api/get_timeline/{session_id}`

作用：获取当前绘本所有剧情节点，用于展示命运之树。

调用顺序：

```text
前端 -> get_timeline()
  -> get_storybook_info(session_id)
  -> get_all_nodes(session_id)
  -> 返回 theme、features、nodes
```

## 5. 数据库 `src/database.py`

### 全局变量

| 变量 | 作用 |
| --- | --- |
| `DB_FILE` | SQLite 数据库文件名，值为 `storybook.db`。 |

### 表结构

`storybooks`：`session_id` 会话 ID；`theme` 主题；`features` 主角特征；`create_time` 创建时间。

`pages`：`id` 节点 ID；`session_id` 所属会话；`parent_id` 父节点；`depth` 深度；`user_choice` 用户选择；`narrator_text` 旁白；`actor_dialogue` 台词；`action_prompt` 中文动作提示词；`scene_prompt` 中文场景提示词；`image_url` 图片地址；`options_json` 下一步选项 JSON。

### 方法

| 方法 | 作用 |
| --- | --- |
| `init_db()` | 创建两张表。 |
| `create_storybook(session_id, theme, features)` | 新增绘本记录。 |
| `add_page_node(...)` | 新增剧情节点，序列化 `options_list`。 |
| `update_page_image(page_id, image_url)` | 更新节点图片 URL。 |
| `get_page(page_id)` | 查询单个节点。 |
| `get_storybook_info(session_id)` | 查询绘本信息。 |
| `get_all_nodes(session_id)` | 查询所有节点，并解析 `options_json` 为 `options`。 |
| `rebuild_llm_context(page_id)` | 沿 `parent_id` 回溯，重建 LLM 上下文。 |

`rebuild_llm_context()` 顺序：

```text
page_id -> 查询当前节点 -> 沿 parent_id 回溯到根节点 -> 反转路径
  -> 查询 storybooks -> 构造 memory_list -> 保留全局设定和最近 3 条剧情
  -> 返回 features、memory_list、current_path
```

## 6. 大模型 `src/llm_engine.py`

`client` 是 OpenAI 兼容客户端。

`chat_with_agent(system_prompt, user_message, json_mode=False)`：构造消息、调用模型、返回文本。`json_mode=True` 时要求返回 JSON 对象。

`generate_script_turn(child_features, context_history, user_choice, max_retries=3)`：生成一轮剧情。

关键变量：`director_sys` 导演提示词，要求输出中文 `story_scene` 和 `story_action`；`actor_sys` 生成第一人称台词；`critic_sys` 审核儿童安全；`critic_feedback` 保存失败反馈；`data` 是剧情 JSON。

返回结构：

```json
{"narrator_text":"旁白","story_scene":"中文场景提示词","story_action":"中文动作提示词","options":["选项1","选项2"],"actor_dialogue":"主角台词"}
```

调用顺序：

```text
generate_script_turn()
  -> chat_with_agent(director_sys, director_user, json_mode=True)
  -> json.loads(director_response)
  -> chat_with_agent(actor_sys, actor_user)
  -> chat_with_agent(critic_sys, critic_user)
  -> PASS 返回 data，REJECT 带反馈重试
```

## 7. 角色卡 `src/character_card.py`

`CharacterCard` 字段：`raw_features` 原始特征；`role` 角色类型；`hair` 发型；`face` 脸部；`clothes` 服装；`accessories` 配饰；`colors` 主色；`style` 风格；`positive_prompt` 正向提示词；`negative_prompt` 负向提示词。

关键词变量：`COLOR_WORDS` 颜色；`HAIR_WORDS` 发型；`CLOTHES_WORDS` 服装；`ACCESSORY_WORDS` 配饰。

方法：`_normalize_feature_text()` 规范化输入；`_collect_terms()` 提取关键词；`build_character_card()` 构建角色卡；`build_story_page_prompt()` 合成绘本页提示词；`save_character_card()` 保存角色卡；`load_character_card()` 读取角色卡。

调用顺序：

```text
build_character_card(child_features)
  -> 规范化文本 -> 提取发型/颜色/服装/配饰
  -> 判断 role -> 生成角色字段
  -> 拼接 positive_prompt 和 negative_prompt
  -> 返回 CharacterCard
```

```text
build_story_page_prompt(card, story_action, story_scene)
  -> 读取角色卡固定设定
  -> 拼接中文动作和中文场景
  -> 返回 positive、negative
```

## 8. 绘图 `src/image_engine.py`

`ROOT_DIR` 指向 `src` 目录，用于加载工作流。

`load_workflow(filename)` 读取工作流 JSON。

`run_comfyui_task(workflow_json, output_name, task_name, preferred_node_id)` 调用 ComfyUI。

调用顺序：

```text
POST /prompt -> 获取 prompt_id -> 循环 GET /history/{prompt_id}
  -> 找到 preferred_node_id 或其它图片输出节点
  -> GET /view 下载图片 -> 写入 output_name -> 返回路径
```

`generate_full_story_page(session_id, child_features, story_action, story_scene)` 是正式图片生成入口。

关键变量：`card` 角色卡；`base_image_name` 定妆照；`wf1` 角色工作流；`wf2` 绘本页工作流；`seed` 随机种子；`positive` 最终正向提示词。

调用顺序：

```text
generate_full_story_page()
  -> build_character_card(child_features)
  -> save_character_card(card, character_card_{session_id}.json)
  -> 若 base_{session_id}.png 不存在：
      -> load_workflow("TEST_workflow_character_base.json")
      -> 注入 card.positive_prompt 到节点 4
      -> 设置节点 7、9 的 noise_seed
      -> run_comfyui_task(..., preferred_node_id="11")
  -> build_story_page_prompt(card, story_action, story_scene)
  -> load_workflow("TEST_workflow_story_page.json")
  -> 注入 positive 到节点 4
  -> 设置节点 7、9 的 noise_seed
  -> run_comfyui_task(..., preferred_node_id="14")
  -> 返回 final_storybook_page.png
```

## 9. 完整流程

创建新绘本：

```text
输入主角特征和主题 -> /api/init_story_text -> generate_script_turn()
  -> create_storybook() -> add_page_node() -> 前端显示开局
```

生成下一幕：

```text
点击选项 -> /api/next_turn_text -> rebuild_llm_context()
  -> generate_script_turn() -> add_page_node() -> 前端显示新节点
```

生成图片：

```text
请求渲染 page_id -> /api/render_image -> get_page() -> get_storybook_info()
  -> generate_full_story_page() -> 生成/复用定妆照 -> 生成绘本页
  -> 保存为 images/node_{page_id}.png -> update_page_image() -> 前端显示图片
```

获取命运之树：

```text
/api/get_timeline/{session_id} -> get_storybook_info() -> get_all_nodes() -> 返回所有节点
```

## 10. 生成文件

| 文件 | 作用 |
| --- | --- |
| `storybook.db` | SQLite 数据库。 |
| `character_card_{session_id}.json` | 角色卡快照。 |
| `base_{session_id}.png` | 会话角色定妆照。 |
| `final_storybook_page.png` | 临时最终绘本图。 |
| `images/node_{page_id}.png` | 前端访问的最终节点图片。 |

## 11. 注意事项

1. 正式绘图只调用 `TEST_workflow_character_base.json` 和 `TEST_workflow_story_page.json`。
2. LLM 输出的 `story_scene` 和 `story_action` 是中文，以适配 Z-Image。
3. 主角形象由 `character_card.py` 统一注入，保证同一发型、服装、配色。
4. `base_{session_id}.png` 已存在时会跳过定妆照生成。
5. 重复渲染同一节点会覆盖 `images/node_{page_id}.png`。
6. 生产环境建议把 `config.py` 中的 API Key 改为环境变量。
