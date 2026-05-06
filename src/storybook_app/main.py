"""FastAPI 后端入口。

这个模块是整个后端的调度中心，主要负责把前端请求转换成具体业务流程：

1. 用户与故事管理：注册、登录、列出和删除用户自己的绘本故事。
2. 文本生成接口：调用 `llm_engine.py` 生成旁白、台词、动作提示词、场景提示词和选项。
3. 数据持久化：调用 `database.py` 保存绘本会话、剧情节点、图片 URL 和分支关系。
4. 图片生成接口：调用 `image_engine.py` 使用 ComfyUI 生成绘本页。
5. 静态资源：挂载前端页面和生成图片目录，让浏览器可以直接访问。

运行方式示例：
`uv run uvicorn storybook_app.main:app --app-dir src --reload --port 8000`
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import FRONTEND_DIR, IMAGE_OUTPUT_DIR
from .database import (
    add_page_node,
    create_storybook,
    create_user,
    delete_storybook,
    get_all_nodes,
    get_page,
    get_storybook_info,
    get_user_by_id,
    get_user_by_username,
    init_db,
    list_storybooks,
    rebuild_llm_context,
    update_page_image,
    user_owns_storybook,
)
from .image_engine import generate_full_story_page # 切回正式绘图引擎
# from .test_image_engine import generate_full_story_page
from .llm_engine import generate_script_turn, get_llm_settings, set_llm_settings


app = FastAPI(title="儿童绘本生成系统 - 多用户剧情树版")
init_db()

# JWT 配置。生产环境应通过环境变量设置稳定且足够复杂的密钥。
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "storybook-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = int(os.getenv("JWT_EXPIRE_SECONDS", str(60 * 60 * 24 * 7)))


class AuthRequest(BaseModel):
    """注册/登录请求体。"""

    username: str
    password: str


class InitRequest(BaseModel):
    """创建新绘本的请求体。"""

    child_features: str
    theme: str
    title: str | None = None


class NextTurnRequest(BaseModel):
    """生成下一幕剧情的请求体。"""

    session_id: str
    parent_page_id: int
    user_choice: str


class RenderRequest(BaseModel):
    """渲染图片的请求体。"""

    page_id: int


class LLMSettingsRequest(BaseModel):
    """切换大语言模型配置的请求体。"""

    model_name: str
    base_url: str
    api_key: str | None = None


def hash_password(password: str) -> str:
    """使用随机盐和 SHA-256 保存密码摘要。"""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    """校验用户密码。"""
    try:
        salt, expected = password_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, expected)


def _b64url_encode(data: bytes) -> str:
    """返回 JWT 使用的无填充 Base64URL 字符串。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """解码 JWT 使用的无填充 Base64URL 字符串。"""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user_id: int) -> str:
    """创建带签名和过期时间的 JWT。"""
    now = int(time.time())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {"sub": str(user_id), "iat": now, "exp": now + JWT_EXPIRE_SECONDS}

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_token(token: str) -> int | None:
    """校验 JWT 签名与有效期，成功时返回用户 ID。"""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_signature = hmac.new(JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_signature = _b64url_decode(signature_b64)
        if not hmac.compare_digest(actual_signature, expected_signature):
            return None

        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != JWT_ALGORITHM:
            return None

        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["sub"])
    except Exception:
        return None


def get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    """从 Authorization 头读取并校验当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def ensure_story_owner(user_id: int, session_id: str) -> None:
    """确认指定故事属于当前用户。"""
    if not user_owns_storybook(user_id, session_id):
        raise HTTPException(status_code=403, detail="无权访问这个故事")


@app.post("/api/register")
async def register(req: AuthRequest):
    """注册新用户。"""
    username = req.username.strip()
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少需要 2 个字符")
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="密码至少需要 4 个字符")
    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    user_id = create_user(username, hash_password(req.password))
    token = create_token(user_id)
    return {"token": token, "user": {"id": user_id, "username": username}}


@app.post("/api/login")
async def login(req: AuthRequest):
    """登录用户。"""
    user = get_user_by_username(req.username.strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user["id"])
    return {"token": token, "user": {"id": user["id"], "username": user["username"]}}


@app.get("/api/me")
async def me(current_user: Annotated[dict, Depends(get_current_user)]):
    """返回当前登录用户。"""
    return {"user": current_user}


@app.post("/api/logout")
async def logout():
    """退出登录。JWT 由前端删除，本接口保留用于统一交互流程。"""
    return {"ok": True}


@app.get("/api/settings/llm")
async def get_llm_settings_api(current_user: Annotated[dict, Depends(get_current_user)]):
    """返回当前运行时使用的大语言模型配置。"""
    return get_llm_settings()


@app.post("/api/settings/llm")
async def update_llm_settings_api(
    req: LLMSettingsRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """切换当前运行时使用的大语言模型配置。"""
    if not req.model_name.strip():
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    if not req.base_url.strip():
        raise HTTPException(status_code=400, detail="接口地址不能为空")
    return set_llm_settings(req.model_name, req.base_url, req.api_key)


@app.get("/api/storybooks")
async def storybooks(current_user: Annotated[dict, Depends(get_current_user)]):
    """列出当前用户的全部绘本故事。"""
    return {"stories": list_storybooks(current_user["id"])}


@app.delete("/api/storybooks/{session_id}")
async def remove_storybook(session_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """删除当前用户的某个绘本故事。"""
    if not delete_storybook(current_user["id"], session_id):
        raise HTTPException(status_code=404, detail="故事不存在或无权删除")
    return {"ok": True}


@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """创建新绘本并生成根节点剧情。"""
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"

    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    create_storybook(session_id, req.theme, req.child_features, current_user["id"], req.title)
    page_id = add_page_node(
        session_id,
        0,
        0,
        "开始冒险",
        turn_data["narrator_text"],
        turn_data["actor_dialogue"],
        turn_data["story_action"],
        turn_data["story_scene"],
        turn_data["options"],
    )

    return {
        "session_id": session_id,
        "page_id": page_id,
        "narrator_text": turn_data["narrator_text"],
        "actor_dialogue": turn_data["actor_dialogue"],
        "options": turn_data["options"],
    }


@app.post("/api/next_turn_text")
async def next_turn_text(req: NextTurnRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """根据用户选择生成新的剧情分支节点。"""
    ensure_story_owner(current_user["id"], req.session_id)

    page = get_page(req.parent_page_id)
    if not page or page["session_id"] != req.session_id:
        raise HTTPException(status_code=404, detail="找不到当前故事节点")

    features, memory_list, current_path = rebuild_llm_context(req.parent_page_id)
    if not features:
        raise HTTPException(status_code=404, detail="找不到时间线")

    turn_data = generate_script_turn(features, "\n".join(memory_list), req.user_choice)
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    depth = current_path[-1]["depth"] + 1 if current_path else 1
    page_id = add_page_node(
        req.session_id,
        req.parent_page_id,
        depth,
        req.user_choice,
        turn_data["narrator_text"],
        turn_data["actor_dialogue"],
        turn_data["story_action"],
        turn_data["story_scene"],
        turn_data["options"],
    )

    return {
        "page_id": page_id,
        "narrator_text": turn_data["narrator_text"],
        "actor_dialogue": turn_data["actor_dialogue"],
        "options": turn_data["options"],
    }


@app.post("/api/render_image")
async def render_image(req: RenderRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    """为指定剧情节点生成图片并写回数据库。"""
    page = get_page(req.page_id)
    if not page:
        raise HTTPException(status_code=404, detail="找不到节点")

    book = get_storybook_info(page["session_id"])
    if not book:
        raise HTTPException(status_code=404, detail="找不到故事")
    ensure_story_owner(current_user["id"], book["session_id"])

    img_path = generate_full_story_page(
        page["session_id"],
        book["features"],
        page["action_prompt"],
        page["scene_prompt"],
    )
    if not img_path:
        raise HTTPException(status_code=500, detail="图片生成失败")

    final_img_name = f"node_{req.page_id}.png"
    final_img_path = IMAGE_OUTPUT_DIR / final_img_name

    if final_img_path.exists():
        final_img_path.unlink()
    os.replace(img_path, final_img_path)

    image_url = f"/images/{final_img_name}"
    update_page_image(req.page_id, image_url)

    return {"image_url": image_url}


@app.get("/api/get_timeline/{session_id}")
async def get_timeline(session_id: str, current_user: Annotated[dict, Depends(get_current_user)]):
    """返回一个绘本会话的所有节点，用于前端绘制剧情树。"""
    ensure_story_owner(current_user["id"], session_id)
    book = get_storybook_info(session_id)
    nodes = get_all_nodes(session_id)
    if not book or not nodes:
        raise HTTPException(status_code=404, detail="无记录")
    return {
        "session_id": book["session_id"],
        "title": book["title"],
        "theme": book["theme"],
        "features": book["features"],
        "nodes": nodes,
    }


app.mount("/images", StaticFiles(directory=IMAGE_OUTPUT_DIR), name="images")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
