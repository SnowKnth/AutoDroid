import os

def count_files_and_directories_recursive(directory):
    # 初始化计数
    num_files = 0
    num_dirs = 0

    # 遍历目录
    for root, dirs, files in os.walk(directory):
        num_dirs += len(dirs)
        num_files += len(files)

    return num_files, num_dirs

def count_files_and_directories_at_depth(directory, target_depth=2):
    num_files = 0
    num_dirs = 0

    for root, dirs, files in os.walk(directory):
        # 计算当前深度：去除开头的directory部分，然后数路径分隔符
        current_depth = root[len(directory):].count(os.sep)
        
        if current_depth == target_depth - 1:
            # 当前目录是目标深度的父目录，统计其直接子目录和文件
            num_dirs += len(dirs)
            num_files += len(files)
        elif current_depth >= target_depth:
            # 超过目标深度，停止遍历这个分支
            del dirs[:]  # 清空子目录列表，停止向下遍历

    return num_files, num_dirs

def count_files_and_directories(directory):
    num_files = 0
    num_dirs = 0

    for item in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, item)):
            num_dirs += 1
        else:
            num_files += 1

    return num_files, num_dirs

def count_files_and_directories(directory):
    num_files = 0
    num_dirs = 0

    for item in os.listdir(directory):
        if os.path.isdir(os.path.join(directory, item)):
            num_dirs += 1
        else:
            num_files += 1

    return num_files, num_dirs

if __name__ == "__main__":
    # 指定目录路径
    
    # directory_path = "/data/wxd/LlamaTouch/RASSDroid/exec_output_deepseek_oracle_03-30_1-250"
    # directory_path = "/data/wxd/LlamaTouch/RASSDroid/exec_output_deepseek_oracle_03-30_251-495"
    # directory_path = "/data/wxd/LlamaTouch/RASSDroid/exec_output_deepseek_oracle_04-13_251-495"
    directory_path = "/data/wxd/LlamaTouch/RASSDroid/exec_output_llamatouch_RASSDroid_deepseek_06-30"
    
    
    
    # directory_path = "/data/wxd/LlamaTouch/RASSDroid/exec_output_llamatouch_autodroid_deepseek_scroll_text_04-05_1-495"
    # directory_path = "/data/wxd/LlamaTouch/AutoDroid/exec_output_llamatouch_autodroid_deepseek_with_sleep_5s"

    # 调用函数统计文件和文件夹数量
    # file_count, dir_count = count_files_and_directories(directory_path)
    
    file_count, dir_count = count_files_and_directories_at_depth(directory_path, target_depth=2)

    # 输出结果
    print(f"文件数量: {file_count}")
    print(f"文件夹数量: {dir_count}")