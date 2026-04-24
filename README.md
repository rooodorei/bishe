# 儿童绘本生成系统技术文档

## 1. 项目概述

本项目是一个儿童互动绘本生成系统，主要代码位于 `src` 目录。系统通过 FastAPI 提供后端接口，Vue 3 实现前端交互，SQLite 保存故事分支，大语言模型生成剧情文本，ComfyUI 工作流负责绘本图片生成。目前 `src/main.py` 中图片接口使用占位图调试模式，真实 ComfyUI 生成逻辑保留在注释中。

## 2. 目录与模块

| 文件 | 作用 |
| --- | --- |
| `src/main.py` | 后端入口，定义 API、请求模型、静态文件服务。 |
| `src/database.py` | SQLite 数据库初始化、故事和页面节点读写、上下文重建。 |
| `src/llm_engine.py` | 调用大语言模型生成剧情、台词并审核内容安全。 |
| `src/image_engine.py` | 调用 ComfyUI 三阶段工作流生成绘本图片。 |
| `src/config.py` | 大模型和 ComfyUI 配置。 |
| `src/index.html` | Vue 3 前端页面，包含创建故事、阅读故事、命运之树。 |
| `src/workflow_stage1_base.json` | ComfyUI 阶段 1：生成主角定妆照。 |
| `src/workflow_stage2_pose.json` | ComfyUI 阶段 2：生成动作姿态图。 |
| `src/workflow_stage3_final.json` | ComfyUI 阶段 3：生成最终绘本图。 |

## 3. 系统流程

1. 用户选择故事主题并输入主角特征。
2. 前端调用 `/api/init_story_text` 创建新故事。
3. 后端调用大模型生成开局旁白、台词、绘图提示词和选项。
4. 后端将故事信息和根节点写入 SQLite。
5. 前端调用 `/api/render_image` 获取图片。
6. 用户选择下一步，前端调用 `/api/next_turn_text`。
7. 后端根据父节点回溯上下文，再生成新剧情节点。
8. 所有节点形成“命运之树”，前端通过 `/api/get_timeline/{session_id}` 展示分支。

## 4. 后端接口 `src/main.py`

### 4.1 全局变量

| 名称 | 类型 | 作用 |
| --- | --- | --- |
| `app` | `FastAPI` | FastAPI 应用实例。 |
| `IMAGE_DIR` | `str` | 图片目录，值为 `images`。 |

启动时执行 `init_db()` 初始化数据库，并创建 `images` 目录。

### 4.2 请求模型

| 模型 | 字段 | 作用 |
| --- | --- | --- |
| `InitRequest` | `child_features: str` | 主角特征。 |
| `InitRequest` | `theme: str` | 故事主题。 |
| `NextTurnRequest` | `session_id: str` | 当前故事会话 ID。 |
| `NextTurnRequest` | `parent_page_id: int` | 当前父节点 ID。 |
| `NextTurnRequest` | `user_choice: str` | 用户选择或自定义输入。 |
| `RenderRequest` | `page_id: int` | 需要渲染图片的页面节点 ID。 |

### 4.3 `POST /api/init_story_text`

创建新故事并生成开局剧情。

请求示例：

```json
{
  "child_features": "a cute boy, wearing a yellow hat",
  "theme": "魔法森林探险"
}
```

返回示例：

```json
{
  "session_id": "uuid",
  "page_id": 1,
  "narrator_text": "旁白",
  "actor_dialogue": "主角台词",
  "options": ["选项1", "选项2"]
}
```

关键变量：

| 变量 | 作用 |
| --- | --- |
| `session_id` | 使用 `uuid.uuid4()` 创建的新故事 ID。 |
| `opening_context` | 初始上下文，包含故事主题。 |
| `turn_data` | 大模型生成的剧情数据。 |
| `page_id` | 保存到数据库后的根节点 ID。 |

### 4.4 `POST /api/next_turn_text`

根据用户选择生成下一幕剧情。

请求示例：

```json
{
  "session_id": "uuid",
  "parent_page_id": 1,
  "user_choice": "走进发光的小路"
}
```

返回示例：

```json
{
  "page_id": 2,
  "narrator_text": "下一幕旁白",
  "actor_dialogue": "主角台词",
  "options": ["选项1", "选项2"]
}
```

关键变量：

| 变量 | 作用 |
| --- | --- |
| `features` | 当前故事主角特征。 |
| `memory_list` | 压缩后的上下文记忆。 |
| `current_path` | 从根节点到父节点的路径。 |
| `turn_data` | 新一轮剧情数据。 |
| `depth` | 新节点深度。 |
| `page_id` | 新节点 ID。 |

### 4.5 `POST /api/render_image`

为指定节点生成或返回图片。当前为调试模式，返回占位图。

请求示例：

```json
{
  "page_id": 2
}
```

返回示例：

```json
{
  "image_url": "https://placehold.co/800x400/2b2b36/00d2ff.png?text=Node+2"
}
```

关键变量：

| 变量 | 作用 |
| --- | --- |
| `page` | 数据库中的页面节点。 |
| `book` | 当前故事信息。调试模式下未实际使用。 |
| `placeholder_url` | 占位图地址。 |

真实 ComfyUI 模式下，注释代码会使用 `generate_full_story_page()` 生成图片，保存为 `images/node_{page_id}.png`，并把 `/images/node_{page_id}.png` 写入数据库。

### 4.6 `GET /api/get_timeline/{session_id}`

获取故事的所有节点，用于前端构建命运之树。

返回示例：

```json
{
  "theme": "魔法森林探险",
  "features": "a cute boy",
  "nodes": []
}
```

关键变量：

| 变量 | 作用 |
| --- | --- |
| `book` | 故事基础信息。 |
| `nodes` | 当前故事的全部剧情节点。 |

## 5. 数据库模块 `src/database.py`

### 5.1 全局变量

| 名称 | 作用 |
| --- | --- |
| `DB_FILE` | SQLite 数据库文件名，值为 `storybook.db`。 |

### 5.2 表结构

#### `storybooks`

| 字段 | 作用 |
| --- | --- |
| `session_id` | 故事唯一 ID，主键。 |
| `theme` | 故事主题。 |
| `features` | 主角特征。 |
| `create_time` | 创建时间。 |

#### `pages`

| 字段 | 作用 |
| --- | --- |
| `id` | 页面节点自增 ID。 |
| `session_id` | 所属故事 ID。 |
| `parent_id` | 父节点 ID，根节点为 `0`。 |
| `depth` | 节点深度。 |
| `user_choice` | 用户进入该节点时的选择。 |
| `narrator_text` | 旁白文本。 |
| `actor_dialogue` | 主角台词。 |
| `action_prompt` | 英文动作提示词。 |
| `scene_prompt` | 英文场景提示词。 |
| `image_url` | 图片地址。 |
| `options_json` | 下一步选项的 JSON 字符串。 |

### 5.3 函数

| 函数 | 作用 | 关键变量 |
| --- | --- | --- |
| `init_db()` | 创建 `storybooks` 和 `pages` 表。 | `conn` 数据库连接；`cursor` SQL 游标。 |
| `create_storybook(session_id, theme, features)` | 新增故事记录。 | `create_time` 创建时间。 |
| `add_page_node(...)` | 新增剧情节点。 | `options_str` 选项 JSON 字符串；`new_page_id` 新节点 ID。 |
| `update_page_image(page_id, image_url)` | 更新节点图片。 | `page_id` 节点 ID；`image_url` 图片地址。 |
| `get_page(page_id)` | 查询单个节点。 | `page` 查询结果。 |
| `get_storybook_info(session_id)` | 查询故事信息。 | `book` 查询结果。 |
| `get_all_nodes(session_id)` | 查询全部节点并解析选项。 | `nodes` 原始节点；`result` 返回列表；`node_dict` 节点字典。 |
| `rebuild_llm_context(page_id)` | 从当前节点回溯，重建大模型上下文。 | `path` 节点路径；`current_id` 当前回溯 ID；`memory_list` 上下文记忆。 |

`rebuild_llm_context()` 返回 `(features, memory_list, path)`；若找不到路径，返回 `(None, [], [])`。

## 6. 大模型模块 `src/llm_engine.py`

### 6.1 全局对象

| 名称 | 作用 |
| --- | --- |
| `client` | OpenAI 兼容客户端，使用 `LLM_API_KEY`、`LLM_BASE_URL`。 |

### 6.2 `chat_with_agent(system_prompt, user_message, json_mode=False)`

封装一次大模型对话。

| 参数/变量 | 作用 |
| --- | --- |
| `system_prompt` | 系统提示词。 |
| `user_message` | 用户消息。 |
| `json_mode` | 是否要求返回 JSON 对象。 |
| `messages` | 发送给模型的消息数组。 |
| `kwargs` | 模型调用参数。 |
| `response` | 模型响应。 |
| `result` | 返回文本。 |

### 6.3 `generate_script_turn(child_features, context_history, user_choice, max_retries=3)`

生成一轮剧情并审核安全。

期望返回结构：

```json
{
  "narrator_text": "旁白",
  "story_scene": "英文场景提示词",
  "story_action": "英文动作提示词",
  "options": ["选项1", "选项2"],
  "actor_dialogue": "主角台词"
}
```

关键变量：

| 变量 | 作用 |
| --- | --- |
| `director_sys` | 导演角色提示词，生成 JSON 剧情。 |
| `actor_sys` | 演员角色提示词，生成第一人称台词。 |
| `critic_sys` | 评论家提示词，审核儿童内容安全。 |
| `critic_feedback` | 上轮审核或 JSON 错误反馈。 |
| `attempt` | 当前尝试次数。 |
| `director_user` | 发给导演模型的上下文。 |
| `director_response` | 导演模型原始输出。 |
| `data` | 解析后的剧情字典。 |
| `narrator_text` | 旁白。 |
| `story_scene` | 场景提示词。 |
| `actor_user` | 发给演员模型的内容。 |
| `actor_dialogue` | 主角台词。 |
| `critic_user` | 发给审核模型的内容。 |
| `critic_verdict` | 审核结果，包含 `PASS` 表示通过。 |

## 7. 图片模块 `src/image_engine.py`

### 7.1 `log(step, message)`

打印带时间戳的日志。

| 参数 | 作用 |
| --- | --- |
| `step` | 当前步骤。 |
| `message` | 日志信息。 |

### 7.2 `run_comfyui_task(workflow_json, output_name, task_name="未知任务")`

提交 ComfyUI 工作流并下载输出图片。

| 参数/变量 | 作用 |
| --- | --- |
| `workflow_json` | ComfyUI 工作流对象。 |
| `output_name` | 下载后的图片路径。 |
| `task_name` | 日志中的任务名。 |
| `res` | `/prompt` 接口响应。 |
| `prompt_id` | ComfyUI 任务 ID。 |
| `history` | 任务历史。 |
| `outputs` | 输出节点集合。 |
| `img_info` | 图片文件信息。 |
| `img_url` | 图片下载 URL。 |
| `img_res` | 图片响应内容。 |

### 7.3 `generate_full_story_page(session_id, child_features, story_action, story_scene)`

三阶段生成最终绘本图。

| 参数/变量 | 作用 |
| --- | --- |
| `session_id` | 故事 ID，用于区分定妆照。 |
| `child_features` | 主角特征。 |
| `story_action` | 动作提示词。 |
| `story_scene` | 场景提示词。 |
| `base_image_name` | 定妆照文件名 `base_{session_id}.png`。 |
| `wf1` | 阶段 1 工作流。 |
| `wf2` | 阶段 2 工作流。 |
| `wf3` | 阶段 3 工作流。 |

阶段说明：

1. 阶段 1 使用 `workflow_stage1_base.json` 生成角色定妆照。
2. 阶段 2 使用 `workflow_stage2_pose.json` 生成动作姿态图 `temp_pose.png`。
3. 阶段 3 使用 `workflow_stage3_final.json` 结合定妆照、姿态图和场景提示词生成 `final_storybook_page.png`。

## 8. 配置 `src/config.py`

| 配置项 | 作用 |
| --- | --- |
| `LLM_API_KEY` | 大模型 API Key。建议改为环境变量。 |
| `LLM_BASE_URL` | 大模型接口地址。 |
| `LLM_MODEL_NAME` | 模型名称。 |
| `COMFYUI_SERVER_ADDRESS` | ComfyUI 服务地址。 |
| `COMFYUI_INPUT_DIR` | ComfyUI 输入目录。 |

## 9. 前端 `src/index.html`

### 9.1 页面状态

| 状态 | 作用 |
| --- | --- |
| `setup` | 创建故事页面。 |
| `loading` | 加载页面。 |
| `story` | 阅读和选择页面。 |
| `timeline` | 命运之树页面。 |

### 9.2 核心变量

| 变量 | 作用 |
| --- | --- |
| `currentScreen` | 当前界面状态。 |
| `loadingText` | 加载提示文字。 |
| `isDrawing` | 图片是否生成中。 |
| `sessionId` | 当前故事 ID。 |
| `currentPageId` | 当前节点 ID。 |
| `setupData` | 表单数据，含 `theme` 和 `features`。 |
| `customChoice` | 用户自定义选择。 |
| `currentStory` | 当前剧情，含旁白、台词、选项。 |
| `currentImage` | 当前图片 URL。 |
| `timelineTree` | 树形时间线根节点。 |
| `flatNodes` | 扁平节点列表，便于跳转查找。 |

### 9.3 前端函数

| 函数 | 作用 | 关键变量 |
| --- | --- | --- |
| `callApi(url, data)` | 发送 POST 请求。 | `res` 响应；`result` JSON 结果。 |
| `processStoryData(data)` | 更新当前故事并触发图片请求。 | `data` 后端剧情数据。 |
| `fetchImage(pageId)` | 调用 `/api/render_image`。 | `pageId` 节点 ID。 |
| `startGame()` | 创建新故事。 | `setupData` 初始化数据。 |
| `makeChoice(choiceText)` | 生成下一幕。 | `choiceText` 用户选择。 |
| `viewTimeline()` | 加载命运之树。 | `treeMap` 节点映射；`rootNode` 根节点。 |
| `jumpToNode(id)` | 跳转到历史节点。 | `targetNode` 目标节点。 |
| `handleImageError()` | 图片加载失败兜底。 | `currentImage` 兜底占位图。 |

### 9.4 `TreeNodeComponent`

递归显示时间线节点。

| 名称 | 作用 |
| --- | --- |
| `node` | 当前节点数据。 |
| `currentPageId` | 当前激活节点 ID。 |
| `jump(id)` | 点击节点后向父组件发送跳转事件。 |

## 10. 工作流 JSON

| 文件 | 关键节点 | 作用 |
| --- | --- | --- |
| `workflow_stage1_base.json` | `1` 加载模型，`3` 正向提示词，`4` 负向提示词，`7` 预览图 | 生成角色定妆照。 |
| `workflow_stage2_pose.json` | `1` 动作提示词，`8` OpenPose 预处理，`10` 保存图像 | 生成姿态参考图。 |
| `workflow_stage3_final.json` | `6` 场景提示词，`8` 角色图，`14` 姿态图，`13` IPAdapter，`16` ControlNet，`20` 预览图 | 生成最终绘本图。 |

## 11. 重要数据结构

### 剧情节点

```json
{
  "id": 1,
  "session_id": "uuid",
  "parent_id": 0,
  "depth": 0,
  "user_choice": "开始冒险",
  "narrator_text": "旁白",
  "actor_dialogue": "台词",
  "action_prompt": "英文动作提示词",
  "scene_prompt": "英文场景提示词",
  "image_url": "图片地址",
  "options_json": "选项JSON字符串",
  "options": ["选项1", "选项2"]
}
```

### 大模型剧情结果

```json
{
  "narrator_text": "绘本旁白",
  "story_scene": "English scene prompt",
  "story_action": "English action prompt",
  "options": ["下一步选项1", "下一步选项2"],
  "actor_dialogue": "主角台词"
}
```

## 12. 改进建议

1. `LLM_API_KEY` 不应硬编码，建议改为环境变量读取。
2. `/api/render_image` 当前为调试占位图，正式使用需恢复 ComfyUI 逻辑。
3. `except:` 建议改为捕获具体异常。
4. `/api/next_turn_text` 建议校验 `parent_page_id` 是否属于传入 `session_id`。
5. 可为 `pages.session_id` 和 `pages.parent_id` 建索引，提高查询效率。
