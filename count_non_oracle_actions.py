import os
import re
import json

def count_non_oracle_actions(root_dir="exec_output_llamatouch_RASSDroid_deepseek_06-30"):
    result = {}
    
    # 遍历根目录下的所有第一层目录（general和其他同级目录）
    for top_dir in os.listdir(root_dir):
        top_dir_path = os.path.join(root_dir, top_dir)
        
        # 跳过非目录文件
        if not os.path.isdir(top_dir_path):
            continue
            
        print(f"Processing top-level directory: {top_dir}")
        
        # 遍历第一层目录下的所有episode目录
        for episode_dir in os.listdir(top_dir_path):
            episode_path = os.path.join(top_dir_path, episode_dir)
            
            # 检查是否是目录（类似"84143002711104077"的目录）
            if not os.path.isdir(episode_path):
                continue
                
            print(f"  Processing episode: {episode_dir}")
            
            # 在episode目录下查找action目录
            action_dir = os.path.join(episode_path, "captured_data", "action")
            if not os.path.exists(action_dir):
                print(f"    Action directory not found in {episode_path}")
                continue
                
            # 初始化计数器
            action_count = 0
            
            # 遍历action目录下的所有.action文件
            for action_file in os.listdir(action_dir):
                if not re.match(r'\d+\.action$', action_file):
                    continue
                    
                # 读取文件内容
                file_path = os.path.join(action_dir, action_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                        
                        # 检查是否不以"Oracle"开头
                        if not first_line.startswith("Oracle"):
                            action_count += 1
                except Exception as e:
                    print(f"    Error reading {file_path}: {e}")
                    continue
                    
            # 记录结果（使用episode目录名作为key）
            result[episode_dir] = action_count
    
    # 输出JSON文件
    output_file = "action_counts.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    
    print(f"\nResults saved to {output_file}")
    return result

# 执行函数
count_non_oracle_actions()