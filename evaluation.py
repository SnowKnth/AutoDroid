import os
import yaml
import re

def extract_action_history(data):
    action_history = []

    for record in data['records']:
        choice = record['Choice']
        if choice == -1:
            break
        
        state = record['State']
        input_text = record['Input']
        
        # 根据 choice 值从 state 中查找相应的元素
        match = re.search(rf"(button|checkbox|p|input)( id={choice}).*?</\1>", state)
        if match:
            element = match.group(0)
            # 判断元素类型并构建相应的操作
            if "button" in element or "p" in element:
                action = re.sub(rf"( id={choice})","",rf"- TapOn: {element}")
            elif "checkbox" in element:
                action = re.sub(rf"( id={choice})","",rf"- Check: {element}")
            else:
                action = re.sub(rf"( id={choice})","",rf"- Tapon: {element} InputText: {input_text}")
            action_history.append(action)

    return "\n".join(action_history)

def traverse_directory(directory):
    result = {}

    # 遍历目录及其子目录
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.yaml'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
                    task_name = data['task_name']
                    action_history = extract_action_history(data)
                    result[task_name] = action_history

    return result


def traverse_and_compare(directory):
    """read task output .yaml file in output directory and compare records"""
    mismatched_files = []
    task_total = 0
    acc_task = 0
    step_total = 0
    acc_step = 0
    # 遍历目录及其子目录
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.yaml'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    try:
                        data = yaml.safe_load(f)
                        steps, right_steps = compare_records(file_path,data)
                        if steps > 0:
                            task_total += 1
                        if steps == right_steps and steps > 0:
                            acc_task += 1
                        step_total += steps
                        acc_step += right_steps
                        mismatched_files.append(file_path)
                    except yaml.YAMLError as e:
                        print(f"Error reading {file_path}: {e}")
    print(f"\nTask Accuracy: {acc_task}/{task_total} ({acc_task/task_total:.2%})")
    print(f"\nStep Accuracy: {acc_step}/{step_total} ({acc_step/step_total:.2%})")

    return mismatched_files


def compare_records(file_path, data):
    # 使用你需要遍历的根目录路径替换此处的 "DroidTask"
    steps = 0
    right_steps = 0
    directory_path = 'DroidTask'
    baseline_task_action_pair = traverse_directory(directory_path)
    
    task_name = data['task_name']
    action_history = extract_action_history(data)
    action_history_list = action_history.split('\n')
    baseline_action = baseline_task_action_pair.get(task_name)
    if baseline_action is not None:
        baseline_action_list = baseline_action.split('\n')
        
        for index, action in enumerate(baseline_action_list):
            steps += 1
            if index < len(action_history_list) and action_history_list[index] == action:
                right_steps += 1
    else:
        print(f"No baseline action found for task:{file_path} {task_name}")
    return steps, right_steps


traverse_and_compare('output')
# 打印结果字典
# for task_name, action_history in result_dict.items():
#     print(f"Task Name: {task_name}")
#     print(f"Action History:\n{action_history}\n")
