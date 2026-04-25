"""角色卡模块的轻量测试入口。

正式角色卡实现位于 `src/storybook_app/character_card.py`，这里仅保留测试辅助。
"""

from storybook_app.character_card import build_character_card, build_story_page_prompt, load_character_card, save_character_card


__all__ = [
    "build_character_card",
    "build_story_page_prompt",
    "save_character_card",
    "load_character_card",
]
