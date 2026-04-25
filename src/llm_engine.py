"""大模型剧情生成模块。

本模块把一轮剧情生成拆成三个角色：
1. 导演：生成旁白、中文绘图提示词和下一步选项。
2. 演员：根据旁白和场景生成主角第一人称台词。
3. 审核员：检查内容是否适合儿童绘本。
"""

import json

from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)


def chat_with_agent(system_prompt, user_message, json_mode=False):
    """封装一次 OpenAI 兼容接口调用。

    `json_mode=True` 时会要求模型返回标准 JSON 对象，主要用于导演阶段。
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    print("\n" + "=" * 25 + " LLM INPUT " + "=" * 25)
    print(f"【User Message】: {user_message}")

    kwargs = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content.strip()

    print("-" * 25 + " LLM RESPONSE " + "-" * 25)
    print(result)
    print("=" * 64)

    return result


def generate_script_turn(child_features, context_history, user_choice, max_retries=3):
    """生成一轮剧情、台词和选项。

    返回字段会直接写入 `pages` 表，其中 `story_action` 和 `story_scene`
    是中文绘图提示词，后续会由 `image_engine.py` 注入 ComfyUI 工作流。
    """
    director_sys = """你是一个专业的中文儿童互动绘本导演，同时熟悉 Z-Image/中文文生图模型的提示词写法。
请根据小朋友的选择构思下一幕，并严格输出一个标准 JSON 对象，不要输出 Markdown，不要添加解释。

JSON 必须包含以下字段：
{
    "narrator_text": "150字左右的中文生动旁白，适合儿童阅读，温暖、有画面感、有互动感",
    "story_scene": "中文绘图场景提示词",
    "story_action": "中文绘图动作提示词",
    "options": ["中文下一步选项1", "中文下一步选项2"]
}

绘图提示词要求：
1. story_scene 和 story_action 必须使用中文，不要再写英文提示词。
2. story_scene 描述环境、时间、氛围、光线、色彩、画面构图，例如：清晨的魔法森林小路，柔和阳光，发光小花，温暖明亮，儿童绘本插画。
3. story_action 描述主角当前动作、姿态、表情和与环境的互动，例如：主角开心地向前走，一只手轻轻挥动，脸上带着好奇微笑。
4. 不要在 story_scene 或 story_action 中重复主角外貌和服装；正式绘图流程会通过角色卡统一注入角色设定。
5. 每一幕只能围绕一个主角展开，不要生成双主角、群像或复杂危险画面。
6. 内容必须安全、温柔、童趣，避免暴力、血腥、恐怖、成人化、危险模仿。
7. 如果收到审核打回意见，请针对性修改，并保持 JSON 格式正确。"""

    actor_sys = """你正在扮演儿童绘本主角。
请结合当前的【场景环境】和【旁白内容】，说一句中文第一人称台词。
要求：50字以内，童真、温暖、积极，像孩子会说的话；不要恐吓、攻击或成人化表达。"""

    critic_sys = """你是儿童内容安全专家。
请审核旁白和台词是否适合儿童互动绘本。
重点检查：暴力、血腥、恐怖惊吓、成人暗示、危险模仿、歧视、羞辱、过度阴暗情绪。
如果安全，只回复 PASS。
如果不安全，回复 REJECT，并用中文简要说明需要修改的问题。"""

    critic_feedback = ""

    for attempt in range(max_retries):
        print(f"\n🎬 [LLM] 第 {attempt + 1} 次尝试生成剧情...")

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

        print("🗣️ 演员正在根据场景配音...")
        actor_user = f"【当前场景】：{story_scene}\n【当前旁白】：{narrator_text}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data["actor_dialogue"] = actor_dialogue

        print("🛡️ 评论家正在逐字审核...")
        critic_user = f"【旁白】：{narrator_text}\n【台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)

        if "PASS" in critic_verdict.upper():
            print("✅ 剧本完美！通过安全审核。")
            return data

        critic_feedback = critic_verdict
        print(f"⚠️ 触发拦截！评论家意见：{critic_feedback}")
        print("🔄 正在将意见反馈给导演进行重写...")

    print("❌ 达到最大尝试次数，生成失败。")
    return None
