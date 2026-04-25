"""角色卡与绘图提示词构建模块。

角色卡用于把用户输入的主角特征整理成稳定结构，后续每一页绘图都复用这些固定字段，
从而尽量保持同一个角色、同一套服装和同一配色。
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CharacterCard:
    """单个绘本会话的主角设定。"""

    raw_features: str
    role: str
    hair: str
    face: str
    clothes: str
    accessories: str
    colors: str
    style: str
    positive_prompt: str
    negative_prompt: str


# 下面四组词表用于从用户输入中提取可复用的视觉锚点。
COLOR_WORDS = [
    "红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "粉色", "白色", "黑色", "灰色", "棕色", "金色", "银色",
    "浅黄", "浅蓝", "浅绿", "深蓝", "深红", "彩虹色"
]

HAIR_WORDS = [
    "白色头发", "白发", "黑色头发", "黑发", "棕色头发", "棕发", "金色头发", "金发", "红色头发", "红发",
    "短发", "长发", "卷发", "双马尾", "马尾", "丸子头"
]

CLOTHES_WORDS = [
    "斗篷", "连衣裙", "裙子", "背带裤", "短裤", "长裤", "卫衣", "外套", "衬衫", "毛衣", "雨衣", "鞋子", "靴子",
    "运动鞋", "围巾", "帽子"
]

ACCESSORY_WORDS = ["发卡", "星星发卡", "书包", "小包", "眼镜", "围巾", "帽子", "手套", "徽章"]


def _collect_terms(text: str, terms: list[str]) -> list[str]:
    """返回 `terms` 中所有出现在 `text` 里的词。"""
    return [term for term in terms if term in text]


def _normalize_feature_text(text: str) -> str:
    """统一用户输入中的空白和分隔符，便于后续关键词提取。"""
    cleaned = re.sub(r"\s+", "，", text.strip())
    cleaned = cleaned.replace(",", "，").replace("、", "，")
    cleaned = re.sub(r"，+", "，", cleaned).strip("，")
    return cleaned


def build_character_card(child_features: str) -> CharacterCard:
    """根据用户输入构建角色卡。"""
    features = _normalize_feature_text(child_features)
    hair_terms = _collect_terms(features, HAIR_WORDS)
    color_terms = _collect_terms(features, COLOR_WORDS)
    clothes_terms = _collect_terms(features, CLOTHES_WORDS)
    accessory_terms = _collect_terms(features, ACCESSORY_WORDS)

    role = "可爱的儿童绘本主角"
    if "女孩" in features or "小女孩" in features:
        role = "可爱的小女孩"
    elif "男孩" in features or "小男孩" in features:
        role = "可爱的小男孩"
    elif "小动物" in features or "动物" in features:
        role = "拟人化的可爱小动物主角"

    hair = "，".join(dict.fromkeys(hair_terms)) or "发型清晰可辨，和用户输入保持一致"
    face = "圆脸，大眼睛，温柔微笑，儿童友好的表情"
    clothes = "，".join(dict.fromkeys(clothes_terms)) or "颜色明确、轮廓简单、适合儿童绘本复用的固定服装"
    accessories = "，".join(dict.fromkeys(accessory_terms)) or "不添加额外复杂配饰"
    colors = "，".join(dict.fromkeys(color_terms)) or "明亮温暖的固定配色"
    style = "儿童绘本画风，温暖明亮，干净线条，柔和光线，角色设计稿，高质量，可爱但不过度复杂"

    positive_prompt = (
        f"{style}，一个人，只有一个人，单个角色，角色定妆照，白色背景，全身，正对镜头，"
        f"{role}，用户输入特征：{features}，"
        f"固定外貌：{hair}，{face}，"
        f"固定服装：{clothes}，固定配饰：{accessories}，固定主色：{colors}，"
        "服装设计清晰，颜色块明确，角色轮廓完整，后续多页面绘本必须复用同一个角色设计，"
        "同一张脸，同一发型，同一套服装，同一配色，不换衣服，不改变标志性配饰"
    )

    negative_prompt = (
        "不同角色，多个人，多角色，双人，群像，换衣服，改变服装颜色，改变发色，额外复杂配饰，成人化，性感，恐怖，血腥，暴力，"
        "阴暗惊悚，多个主角，复杂背景，遮挡身体，裁切身体，低质量，变形，坏手，坏脸，文字，水印，logo"
    )

    return CharacterCard(
        raw_features=features,
        role=role,
        hair=hair,
        face=face,
        clothes=clothes,
        accessories=accessories,
        colors=colors,
        style=style,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
    )


def build_story_page_prompt(card: CharacterCard, story_action: str, story_scene: str) -> tuple[str, str]:
    """把角色卡和本页剧情合成为绘本页正负提示词。"""
    positive = (
        "儿童绘本页面插画，温暖明亮，高质量，干净线条，柔和光线，色彩柔和，故事感强，儿童友好，"
        "画面中只有一个主角，单个角色，不出现第二个主角，"
        f"同一个主角：{card.role}，固定外貌：{card.hair}，{card.face}，"
        f"始终穿着同一套固定服装：{card.clothes}，固定配饰：{card.accessories}，固定主色：{card.colors}，"
        "不要换衣服，不要改变服装颜色，不要增加新的帽子或复杂配饰，"
        f"动作：{story_action}，场景：{story_scene}，全身或中景构图，构图清晰，适合儿童互动绘本"
    )
    negative = (
        card.negative_prompt
        + "，不同服装，服装变化，错误服装颜色，缺少标志性服装，额外帽子，文字，水印，logo"
    )
    return positive, negative


def save_character_card(card: CharacterCard, output_path: str | Path) -> Path:
    """把角色卡保存成 JSON，方便调试和复查同一会话的角色设定。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(card), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_character_card(path: str | Path) -> CharacterCard:
    """从 JSON 文件恢复角色卡对象。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CharacterCard(**data)
