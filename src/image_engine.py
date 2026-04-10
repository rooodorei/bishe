# image_engine.py
import json
import requests
import time
import shutil
import os
from datetime import datetime
from config import COMFYUI_SERVER_ADDRESS, COMFYUI_INPUT_DIR

def log(step, message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step} | {message}")

def run_comfyui_task(workflow_json, output_name, task_name="未知任务"):
    try:
        res = requests.post(f"{COMFYUI_SERVER_ADDRESS}/prompt", json={"prompt": workflow_json})
        res.raise_for_status()
        prompt_id = res.json()['prompt_id']
    except Exception as e:
        log("❌ 错误", f"提交【{task_name}】失败，ComfyUI 没开吗？报错: {e}")
        return None
    
    while True:
        try:
            history = requests.get(f"{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}").json()
            if prompt_id in history:
                outputs = history[prompt_id]['outputs']
                for node_id in outputs:
                    if 'images' in outputs[node_id]:
                        img_info = outputs[node_id]['images'][0]
                        img_url = f"{COMFYUI_SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                        img_res = requests.get(img_url)
                        with open(output_name, "wb") as f:
                            f.write(img_res.content)
                        return output_name
            time.sleep(1)
        except:
            time.sleep(1)

def generate_full_story_page(session_id, child_features, story_action, story_scene):
    base_image_name = f"base_{session_id}.png"
    if not os.path.exists(base_image_name):
        print(f">>> 绘本[{session_id}]是新任务，正在生成专属定妆照...")
        with open("workflow_stage1_base.json", "r", encoding="utf-8") as f: 
            wf1 = json.load(f)
        wf1["3"]["inputs"]["text"] += f", ({child_features}:1.3), full body"
        print(f"🔍 [Stage 1 Prompt]: {wf1['3']['inputs']['text']}") # 显式输出
        run_comfyui_task(wf1, base_image_name, "阶段1:定妆照")
    else:
        print(f">>> 绘本[{session_id}]已有定妆照，直接跳过阶段 1。")



    with open("workflow_stage2_pose.json", "r", encoding="utf-8") as f: wf2 = json.load(f)
    wf2["1"]["inputs"]["text"] += f",a person {story_action}, full body, simple background"
    print(f"🔍 [Stage 2 Prompt]: {wf2['1']['inputs']['text']}") # 显式输出
    run_comfyui_task(wf2, "temp_pose.png", "阶段2:动作图")
    
    shutil.copy(base_image_name, os.path.join(COMFYUI_INPUT_DIR, "input_base.png"))
    shutil.copy("temp_pose.png", os.path.join(COMFYUI_INPUT_DIR, "input_pose.png"))
    
    with open("workflow_stage3_final.json", "r", encoding="utf-8") as f: wf3 = json.load(f)
    wf3["6"]["inputs"]["text"] += f",child, {story_scene}, high quality, detailed, colorful, cinematic lighting"
    print(f"🔍 [Stage 3 Prompt]: {wf3['6']['inputs']['text']}") # 显式输出
    wf3["8"]["inputs"]["image"] = "input_base.png" 
    wf3["14"]["inputs"]["image"] = "input_pose.png" 
    
    return run_comfyui_task(wf3, "final_storybook_page.png", "阶段3:最终绘本图")