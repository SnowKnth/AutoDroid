
import os
import subprocess
from time import sleep 
import yaml

# 定义DroidTask和apks目录路径
droid_task_dir = './DroidTask'
apks_dir = './apks'

try:
# 遍历DroidTask目录的子目录
    sleep(3600*8)
    for app_title in os.listdir(droid_task_dir):
        app_dir = os.path.join(droid_task_dir, app_title)
        
        # 检查是否是目录
        if os.path.isdir(app_dir) and app_title != "calendar":##################
            # 遍历该目录下的task文件
            for filename in os.listdir(app_dir):
                if filename.startswith('task') and filename.endswith('.yaml'):
                    task_file_path = os.path.join(app_dir, filename)
                    
                    # 读取yaml文件内容
                    with open(task_file_path, 'r', encoding='utf-8') as file:
                        yaml_content = yaml.safe_load(file)
                    
                    # 获取task_name
                    task_name = yaml_content.get('task_name', None)
                    if task_name:
                        # 查找对应的apk文件
                        apk_file = None
                        for apk in os.listdir(apks_dir):
                            if app_title in apk.lower() and apk.endswith('.apk'):
                                apk_file = os.path.join(apks_dir, apk)
                                break
                        
                        # 如果找到对应的apk文件
                        if apk_file:
                            # ; cmd_sh = rf"python3 start.py -a {apk_file.replace(' ', '\ ')} -o output/{app_title} -is_emulator -task '{task_name}' -keep_env -keep_app"
                            cmd_sh = "python3 start.py -a %s -o output/%s -is_emulator -task \"%s\" -keep_env -keep_app" % (apk_file.replace(" ", "\ "), app_title,task_name)
                            converted_sh = " -a %s -o output/%s -is_emulator -task \"%s\" -keep_env -keep_app\n" % (apk_file.replace(" ", "\ "), app_title,task_name)
                            os.system(cmd_sh)
                            with open("batch_exec_droidtask.txt", 'a') as fout:
                                fout.write(converted_sh)
                            fout.close
                        else:
                            logging.info(f"No APK file found for {app_title}")
                    else:
                        logging.info(f"No task_name found in {task_file_path}")

except KeyboardInterrupt:
    logging.info("Program interrupted!")                
                
