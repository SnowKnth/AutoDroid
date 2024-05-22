
import os
import subprocess 

def getFullDirectory(prefix,file_start):
        # 假设你只知道目录前缀     
    # 扫描目录以获取文件名列表  
    filenames = os.listdir(prefix)  
    
    # 根据某些条件（比如文件名模式、创建时间等）筛选文件名  
    # 这里假设我们要找的文件名以"myfile"开头  
    matching_filenames = [fn for fn in filenames if fn.startswith(file_start)]  
    
    # 如果找到了匹配的文件名，选择第一个（或根据其他逻辑选择）  
    if matching_filenames:  
        complete_filename = matching_filenames[0]  
        file_path = os.path.join(prefix, complete_filename)  
        basename = os.path.basename(file_path)  
        print(basename)  # 输出匹配到的文件名  
        return file_path
    else:  
        print("没有找到匹配的文件名")
    


# Convert JSON

script_head = "python3 -m droidbot.start "
# 创建一个包含操作名称信息的字典对象
operations = {
    "b11": "Access website by URL",
    "b12": "Back button",
    "b21": "Add task",
    "b22": "Remove task",
    "b31": "Registration",
    "b32": "Login with valid credentials",
    "b41": "Search email by keywords",
    "b42": "Send email with valid data",
    "b51": "Calculate total bill with tip",
    "b52": "Split bill"
}
with open("params.txt","w") as fout_empty:
    fout_empty.write("")
    fout_empty.close
try:
    for category in ['a1', 'a2', 'a3', 'a4', 'a5']:
        cg_index =  category[1]
        for i in range(1,3):
            b_index = 'b'+cg_index+str(i)
            for j in range(1,6):
                app_json = 'a'+cg_index+str(j)
                script_file = "./c2d_script/"+category+"/"+b_index+"/base/"+app_json+"_drb.json"
                apk_category = getFullDirectory( "./c2d_apps/", category)+"/"
                apk_file = getFullDirectory( apk_category, app_json)
                output_dir = app_json+b_index
                # converted_sh = "python3 -m droidbot.start -a %s -o output/%s -is_emulator -script %s -policy manual\r\n echo \"\\nnext command\\n\" \n " % (apk_file.replace(" ", "\ "), output_dir, script_file)
                # cmd_sh = "python3 -m droidbot.start -a %s -o output/%s -is_emulator -script %s -policy manual " % (apk_file.replace(" ", "\ "), output_dir, script_file)
                task_index = "b"+cg_index+str(i)
                task = operations.get(task_index)
                converted_sh = "python3 start.py -a %s -o output/%s -is_emulator -script %s -task \"%s\" \n" % (apk_file.replace(" ", "\ "), output_dir, script_file, task)
                cmd_sh = "python3 start.py -a %s -o output/%s -is_emulator -script %s -task \"%s\" " % (apk_file.replace(" ", "\ "), output_dir, script_file, task)
                os.system(cmd_sh)
                with open("batch_exec.txt", 'a') as fout:
                    fout.write(converted_sh)
                fout.close
except KeyboardInterrupt:
    print("Program interrupted!")                
                
def getFullDirectory(prefix,file_start):
        # 假设你只知道目录前缀     
    # 扫描目录以获取文件名列表  
    filenames = os.listdir(prefix)  
    
    # 根据某些条件（比如文件名模式、创建时间等）筛选文件名  
    # 这里假设我们要找的文件名以"myfile"开头  
    matching_filenames = [fn for fn in filenames if fn.startswith(file_start)]  
    
    # 如果找到了匹配的文件名，选择第一个（或根据其他逻辑选择）  
    if matching_filenames:  
        complete_filename = matching_filenames[0]  
        file_path = os.path.join(prefix, complete_filename)  
        basename = os.path.basename(file_path)  
        print(basename)  # 输出匹配到的文件名  
    else:  
        print("没有找到匹配的文件名")
