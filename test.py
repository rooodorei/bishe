import json
import time
import requests

# ComfyUI 的默认地址
SERVER_ADDRESS = "http://127.0.0.1:8188"

def generate_image(prompt_workflow, output_path="output_story.png"):
    # 1. 提交任务
    response = requests.post(f"{SERVER_ADDRESS}/prompt", json={"prompt": prompt_workflow})
    if response.status_code != 200:
        print(f"发送失败: {response.text}")
        return False
    
    prompt_id = response.json()['prompt_id']
    print(f"任务已提交，Prompt ID: {prompt_id} ")

    # 2. 轮询等待任务完成
    while True:
        # 查询历史记录接口
        history_res = requests.get(f"{SERVER_ADDRESS}/history/{prompt_id}")
        history_data = history_res.json()

        # 如果 prompt_id 出现在 history 中，说明生成完毕
        if prompt_id in history_data:
            print("生成完毕！正在获取图片...")
            # 3. 解析图片文件名
            # ComfyUI 可能一次生成多张，这里默认取第一张
            outputs = history_data[prompt_id]['outputs']
            for node_id in outputs:
                if 'images' in outputs[node_id]:
                    image_info = outputs[node_id]['images'][0]
                    filename = image_info['filename']
                    subfolder = image_info['subfolder']
                    folder_type = image_info['type']
                    
                    # 4. 下载并保存图片
                    img_url = f"{SERVER_ADDRESS}/view?filename={filename}&subfolder={subfolder}&type={folder_type}"
                    img_res = requests.get(img_url)
                    with open(output_path, "wb") as f:
                        f.write(img_res.content)
                    print(f"图片已成功保存至: {output_path}")
                    return True
        
        # 还没画完，等 2 秒再问
        time.sleep(2)

# ================= 使用测试 =================
if __name__ == "__main__":
    with open("bishe1 (1).json", "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 动态修改正向提示词 (你的节点是 6)
    new_story_prompt = "picture book style,masterpiece, best quality, highly detailed, anatomically correct, perfect body proportions"
    # 强烈建议保留基础的角色 trigger words，将剧情 prompt 拼在后面
    base_character_prompt = "girl, high quality, picture book, "
    workflow["6"]["inputs"]["text"] = base_character_prompt + new_story_prompt

    # 执行生图并保存
    generate_image(workflow, output_path="story_scene_1.png")