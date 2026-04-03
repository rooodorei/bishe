import json
import requests
import time
import shutil
import os
from datetime import datetime

# ================= 配置区 =================
SERVER_ADDRESS = "http://127.0.0.1:8188"
COMFYUI_INPUT_DIR = r"C:/Cworkspace/ComfyUI-aki-v3/ComfyUI/input" # 请替换为你的真实路径
# ==========================================

def log(step, message):
    """自定义日志打印函数，带时间戳，方便排错"""
    current_time = datetime.now().strftime("%H:%M:%S")
    print(f"[{current_time}] {step} | {message}")

def run_comfyui_task(workflow_json, output_name, task_name="未知任务"):
    """通用的 ComfyUI 任务提交流水线"""
    log("提交任务", f"正在将【{task_name}】发送至 ComfyUI...")
    start_time = time.time()
    
    try:
        response = requests.post(f"{SERVER_ADDRESS}/prompt", json={"prompt": workflow_json})
        response.raise_for_status() # 检查HTTP请求是否成功
        prompt_id = response.json()['prompt_id']
        log("排队中", f"【{task_name}】已进入队列，Prompt ID: {prompt_id}")
    except Exception as e:
        log("❌ 错误", f"提交【{task_name}】失败，请检查 ComfyUI 是否已启动！错误信息: {e}")
        return None
    
    # 轮询等待
    wait_count = 0
    while True:
        try:
            history = requests.get(f"{SERVER_ADDRESS}/history/{prompt_id}").json()
            if prompt_id in history:
                log("渲染完成", f"【{task_name}】计算完毕！正在下载图片...")
                outputs = history[prompt_id]['outputs']
                for node_id in outputs:
                    if 'images' in outputs[node_id]:
                        img_info = outputs[node_id]['images'][0]
                        img_url = f"{SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                        img_res = requests.get(img_url)
                        
                        # 保存图片
                        with open(output_name, "wb") as f:
                            f.write(img_res.content)
                        
                        elapsed_time = round(time.time() - start_time, 1)
                        log("✅ 成功", f"【{task_name}】已保存为 {output_name} (耗时: {elapsed_time}秒)")
                        return output_name
            
            # 每等待2秒打印一次点号，表示程序活着
            wait_count += 1
            if wait_count % 3 == 0:
                print(f"   ... 【{task_name}】正在努力渲染中 ({wait_count * 2}秒) ...")
            time.sleep(2)
            
        except Exception as e:
            log("❌ 错误", f"查询【{task_name}】进度时断开连接: {e}")
            time.sleep(2) # 发生网络小波动时重试

# ================= 终极生成流水线 =================
def generate_full_story_page(child_features, story_action, story_scene):
    print("\n" + "="*60)
    print(f"🚀 [新故事生成任务启动] 特征:{child_features} | 动作:{story_action}")
    print("="*60 + "\n")
    
    total_start_time = time.time()

    # ---------------- 阶段一 ----------------
    print(">>> [阶段 1/3]: 准备主角定妆照...")
    if not os.path.exists("temp_base.png"):
        log("阶段一", "未检测到现有定妆照，开始全新生成...")
        with open("workflow_stage1_base.json", "r", encoding="utf-8") as f:
            wf1 = json.load(f)
        wf1["3"]["inputs"]["text"] += f" , {child_features}"
        base_img_path = run_comfyui_task(wf1, "temp_base.png", task_name="主角定妆照")
    else:
        log("阶段一", "检测到已存在定妆照，跳过生成 (节约时间) ⚡")
        base_img_path = "temp_base.png"



    # ---------------- 阶段二 ----------------
    print("\n>>> [阶段 2/3]: 解析剧本，生成骨骼动作参考图...")
    with open("workflow_stage2_pose.json", "r", encoding="utf-8") as f:
        wf2 = json.load(f)
    wf2["1"]["inputs"]["text"] += f", a person {story_action}"
    pose_img_path = run_comfyui_task(wf2, "temp_pose.png", task_name="骨骼动作图")



    # ---------------- 阶段三 ----------------
    print("\n>>> [阶段 3/3]: 生成最终绘本画面...")
    log("数据转移", "正在将参考图送入 ComfyUI 引擎...")
    shutil.copy(base_img_path, os.path.join(COMFYUI_INPUT_DIR, "input_base.png"))
    shutil.copy(pose_img_path, os.path.join(COMFYUI_INPUT_DIR, "input_pose.png"))
    
    with open("workflow_stage3_final.json", "r", encoding="utf-8") as f:
        wf3 = json.load(f)
    
    # 请注意替换为你 JSON 里的真实节点 ID
    wf3["6"]["inputs"]["text"] += f", {story_scene}"
    wf3["8"]["inputs"]["image"] = "input_base.png" 
    wf3["14"]["inputs"]["image"] = "input_pose.png" 
    
    final_img_path = run_comfyui_task(wf3, "final_storybook_page.png", task_name="最终绘本画面")
    




    # ---------------- 总结 ----------------
    total_elapsed = round(time.time() - total_start_time, 1)
    print("\n" + "="*60)
    print(f"🎉 [任务圆满完成] 最终图片已生成: {final_img_path}")
    print(f"⏱️ 整个页面生成总耗时: {total_elapsed} 秒")
    print("="*60 + "\n")
    
    return final_img_path

# 测试运行
if __name__ == "__main__":
    # 模拟从大模型传过来的三个变量
    test_features = "girl, red  hair, blue dress"
    test_action = "jumping joyfully"
    test_scene = "jumping on mushrooms"
    
    # 确保你有对应的 JSON 文件后取消下面这行的注释
    generate_full_story_page(test_features, test_action, test_scene)