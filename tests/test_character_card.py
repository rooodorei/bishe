"""角色卡模块测试辅助入口。

正式角色卡实现位于 `src/storybook_app/character_card.py`。
这个文件不再维护一份重复实现，而是直接重新导出正式函数，避免测试逻辑和正式逻辑不一致。

如果后续要写真正的单元测试，可以在这里添加 pytest 测试函数，例如：
- 测试输入“白色短发的小女孩”是否能识别出女孩和短发。
- 测试角色卡保存后能否再加载回来。
"""

from storybook_app.character_card import build_character_card, build_story_page_prompt, load_character_card, save_character_card


# 显式声明导出对象，方便其它测试脚本从这里导入时知道有哪些可用函数。
__all__ = [
    "build_character_card",
    "build_story_page_prompt",
    "save_character_card",
    "load_character_card",
]
