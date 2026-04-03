import json
import requests
import time
import shutil
import os

SERVER_ADDRESS = "http://127.0.0.1:8188"
COMFYUI_INPUT_DIR = r"D:\ComfyUI_windows_portable\ComfyUI\input" # 替换为你的真实路径

# 这是一个通用的发任务+等图片的函数
def run_comfyui_task(workflow_json, output_name):
    response = requests.post(f"{SERVER_ADDRESS}/prompt", json={"prompt": workflow_json})
    prompt_id = response.json()['prompt_id']
    
    while True:
        history = requests.get(f"{SERVER_ADDRESS}/history/{prompt_id}").json()
        if prompt_id in history:
            outputs = history[prompt_id]['outputs']
            for node_id in outputs:
                if 'images' in outputs[node_id]:
                    img_info = outputs[node_id]['images'][0]
                    img_url = f"{SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                    img_res = requests.get(img_url)
                    
                    # 将图片保存下来
                    with open(output_name, "wb") as f:
                        f.write(img_res.content)
                    return output_name
        time.sleep(1)

# ================= 终极生成流水线 =================
def generate_full_story_page(child_features, story_action, story_scene):
    print(">>> 阶段一：生成主角定妆照...")
    with open("workflow_stage1_base.json", "r", encoding="utf-8") as f:
        wf1 = json.load(f)
    # 修改 wf1 的 Prompt 节点 (假设节点是 6)
    wf1["6"]["inputs"]["text"] = f"1 child, {child_features}, full body, white background, picture book style"
    base_img_path = run_comfyui_task(wf1, "temp_base.png")
    
    print(">>> 阶段二：生成剧情动作图...")
    with open("workflow_stage2_pose.json", "r", encoding="utf-8") as f:
        wf2 = json.load(f)
    # 修改 wf2 的 Prompt 节点 (假设节点是 6)
    wf2["6"]["inputs"]["text"] = f"a person {story_action}, full body, simple background"
    pose_img_path = run_comfyui_task(wf2, "temp_pose.png")
    
    print(">>> 阶段三：合并！生成最终绘本画面...")
    # 把阶段一和二生成的图，丢进 ComfyUI 的 input 文件夹供读取
    shutil.copy(base_img_path, os.path.join(COMFYUI_INPUT_DIR, "input_base.png"))
    shutil.copy(pose_img_path, os.path.join(COMFYUI_INPUT_DIR, "input_pose.png"))
    
    with open("workflow_stage3_final.json", "r", encoding="utf-8") as f:
        wf3 = json.load(f)
    
    # 替换 Prompt 和图片路径 (注意替换为你 JSON 里的真实节点 ID)
    wf3["6"]["inputs"]["text"] = f"child, {story_scene}, high quality, picture book"
    wf3["10"]["inputs"]["image"] = "input_base.png" # IP-Adapter 节点
    wf3["14"]["inputs"]["image"] = "input_pose.png" # ControlNet 节点
    
    final_img_path = run_comfyui_task(wf3, "final_storybook_page.png")
    print(">>> 全部完成！最终图片已生成。")
    return final_img_path