"""大模型剧情生成模块。

本模块把“一轮剧情生成”拆成三个模型角色，目的是让输出更稳定、也更安全：

1. 导演 Director：
   - 根据主角特征、前情提要、用户选择生成下一幕剧情。
   - 必须返回 JSON，便于后端解析和入库。
   - 输出中文 `story_scene` 和 `story_action`，直接服务于 Z-Image 绘图。

2. 演员 Actor：
   - 根据旁白和场景，为主角生成一句第一人称台词。
   - 台词不参与绘图，主要用于前端阅读体验。

3. 审核员 Critic：
   - 审核旁白和台词是否适合儿童绘本。
   - 通过返回 PASS；不通过返回 REJECT 和原因，导演会带着反馈重写。
"""

import json

from openai import OpenAI

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


# 当前运行时使用的大语言模型配置。默认来自环境变量/配置文件，设置页可以临时切换。
CURRENT_LLM_API_KEY = LLM_API_KEY
CURRENT_LLM_BASE_URL = LLM_BASE_URL
CURRENT_LLM_MODEL_NAME = LLM_MODEL_NAME


def _mask_api_key(api_key: str) -> str:
    """返回 API Key 掩码，避免前端读取到明文。"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}****{api_key[-4:]}"


def get_llm_settings() -> dict:
    """返回当前运行时使用的大语言模型配置，不包含明文 API Key。"""
    return {
        "model_name": CURRENT_LLM_MODEL_NAME,
        "base_url": CURRENT_LLM_BASE_URL,
        "api_key_configured": bool(CURRENT_LLM_API_KEY),
        "api_key_masked": _mask_api_key(CURRENT_LLM_API_KEY),
    }


def set_llm_settings(model_name: str, base_url: str, api_key: str | None = None) -> dict:
    """切换当前运行时使用的大语言模型配置。"""
    global CURRENT_LLM_API_KEY, CURRENT_LLM_BASE_URL, CURRENT_LLM_MODEL_NAME
    CURRENT_LLM_MODEL_NAME = model_name.strip()
    CURRENT_LLM_BASE_URL = base_url.strip().rstrip("/")
    if api_key is not None and api_key.strip():
        CURRENT_LLM_API_KEY = api_key.strip()
    return get_llm_settings()


def chat_with_agent(system_prompt, user_message, json_mode=False):
    """封装一次 OpenAI 兼容接口调用。

    Args:
        system_prompt: 系统提示词，定义当前模型角色和输出约束。
        user_message: 用户消息，提供本轮任务的具体上下文。
        json_mode: 是否要求模型返回 JSON 对象。导演阶段需要 True。

    Returns:
        模型返回的文本内容。调用方负责进一步解析。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    print("\n" + "=" * 25 + " LLM INPUT " + "=" * 25)
    print(f"【User Message】: {user_message}")

    kwargs = {"model": CURRENT_LLM_MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        # OpenAI 兼容 JSON 模式可以降低返回 Markdown 或普通文本的概率。
        kwargs["response_format"] = {"type": "json_object"}

    client = OpenAI(api_key=CURRENT_LLM_API_KEY, base_url=CURRENT_LLM_BASE_URL)
    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content.strip()

    print("-" * 25 + " LLM RESPONSE " + "-" * 25)
    print(result)
    print("=" * 64)

    return result


def generate_script_turn(child_features, context_history, user_choice, max_retries=3):
   # 1. 导演提示词：加入 plot_reasoning 强制大模型进行一致性思考
    director_sys = """你是一个专业的中文儿童互动绘本导演，同时熟悉 Z-Image/中文文生图模型的提示词写法。
请根据小朋友的选择构思下一幕，并严格输出一个标准 JSON 对象，不要输出 Markdown，不要添加解释。

JSON 必须包含以下字段：
{
    "plot_reasoning": "（必填）在生成剧情前，简要分析前情提要和主角性格，说明为什么这段新剧情在逻辑上是连贯的（50字内）",
    "narrator_text": "150字左右的中文生动旁白，适合儿童阅读，温暖、有画面感、有互动感",
    "story_scene": "中文绘图场景提示词",
    "story_action": "中文绘图动作提示词",
    "options": ["中文下一步选项1", "中文下一步选项2"]
}

剧情连贯性要求：
1. 必须优先承接【前情提要】中最近一幕的地点、正在发生的动作、主角目标和小朋友刚做出的选择。
2. 不要突然更换地点、任务、道具或新增重要角色；如果必须转换场景，必须在旁白中写出自然过渡。
3. 不要遗忘前情中已经建立的关键事实，例如主角已发现/获得/答应/正在寻找的事物。
4. 新一幕应解决或推进当前选择带来的直接结果，而不是另起一个无关事件。
5. options 必须基于当前旁白结尾自然延伸，不跳到与当前场景无关的行动。

绘图提示词要求：
1. story_scene 和 story_action 必须使用中文。
2. story_scene 描述环境、时间、氛围、光线等。
3. story_action 描述主角当前动作、姿态、表情等。
4. 不要在提示词中重复主角外貌和服装（由角色卡控制）。
5. 每一幕只能围绕一个主角展开，剧情必须连贯。
6. 内容必须安全、温柔、童趣。
7. 如果收到审核打回意见，请针对性修改，并保持 JSON 格式正确。"""

    # 2. 演员提示词：强调基于主角设定发声
    actor_sys = """你正在扮演儿童绘本主角。
请严格结合你的【主角特征】、【前情提要】以及当前的【场景环境】和【旁白内容】，说一句符合你人设的中文第一人称台词。
要求：50字以内，童真、温暖、积极，语气必须符合你的性格特征；不要恐吓、攻击或成人化表达。"""

    # 3. 审核员提示词：增加对“剧情逻辑”和“人设”的审查
    critic_sys = """你是儿童内容安全与剧情连贯性审核专家。
请审核导演和演员生成的内容是否合格。
重点检查：
1. 内容安全性：有无暴力、血腥、恐怖惊吓、危险模仿等。
2. 逻辑一致性：是否与【前情提要】存在严重脱节或逻辑矛盾？
3. 承接性：是否自然延续最近一幕的地点、动作、目标和小朋友刚做出的选择？
4. 事实保持：是否遗忘或推翻前情中已经建立的重要道具、任务、承诺或发现？
如果既安全又连贯，只回复 PASS。
如果存在安全隐患、逻辑崩坏、明显跳戏、突然换任务或无过渡换场景，回复 REJECT，并用中文简要说明需要修改的具体原因。"""

    critic_feedback = ""

    for attempt in range(max_retries):
        print(f"\n🎬 [LLM] 第 {attempt + 1} 次尝试生成剧情...")

        # 导演输入保持不变
        director_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【小朋友的选择】：{user_choice}"
        if critic_feedback:
            director_user += f"\n\n⚠️【上轮审核未通过，请修正】：{critic_feedback}"

        director_response = chat_with_agent(director_sys, director_user, json_mode=True)

        try:
            data = json.loads(director_response)
        except Exception:
            critic_feedback = "JSON格式错误，请确保返回标准的JSON对象。"
            continue

        narrator_text = data.get("narrator_text", "")
        story_scene = data.get("story_scene", "")

        print("🗣️ 演员正在根据场景和人设配音...")
        # 【关键修改】：将特征和前情传入给Actor
        actor_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【当前场景】：{story_scene}\n【当前旁白】：{narrator_text}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data["actor_dialogue"] = actor_dialogue

        print("🛡️ 评论家正在逐字审核安全与一致性...")
        # 【关键修改】：将特征和前情传入给Critic作为裁判依据
        critic_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【待审旁白】：{narrator_text}\n【待审台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)

        if "PASS" in critic_verdict.upper():
            print("✅ 剧本完美！通过安全与连贯性审核。")
            # 可以选择在存入数据库前删掉 plot_reasoning 减小体积
            data.pop("plot_reasoning", None) 
            return data

        critic_feedback = critic_verdict
        print(f"⚠️ 触发拦截！评论家意见：{critic_feedback}")
        print("🔄 正在将意见反馈给导演进行重写...")

    print("❌ 达到最大尝试次数，生成失败。")
    return None