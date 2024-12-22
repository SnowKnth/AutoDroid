import os
import sys
import time
import argparse
from droidbot.droidbot import DroidBot
from droidbot import input_manager
from droidbot import env_manager
from datetime import datetime
from tools import get_extracted_steps, get_reference_steps

import requests

from tools import (
    FINISHED,
    get_action_descv2,
    get_action_from_views_actions,
    parse_views,
)

####because 'AGENTENV_PATH' is set so environment can be found
sys.path.insert(0, os.environ.get("AGENTENV_PATH"))
from environment import AndroidController, PrepareApps

# config
AVD_NAME = "pixel_6a_api31"
TASK_METADATA_PATH = "../dataset/llamatouch_task_metadata.tsv"
# TASK_METADATA_URL = "https://raw.githubusercontent.com/LlamaTouch/LlamaTouch/main/dataset/llamatouch_task_metadata.tsv"
emulator_controller_args = {
        "snapshot" : "default_boot",
        "port" : "5554",        # If port is occupied, please switch to 5556, 5558... and so forth
        "no-window" : "true",  # Change this to "true" to run the emulator without GUI.
    }
first_n_episodes=int(os.environ.get("FIRST_N_EPISODES", 10))

# response = requests.get(TASK_METADATA_URL)
# with open(TASK_METADATA_PATH, "w") as f:
#     f.write(response.content)


def parse_args(extracted_info, ac, episode):
    """
    parse command line input
    generate options including host name, port number
    """
    parser = argparse.ArgumentParser(description="Start DroidBot to test an Android app.",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-d", action="store", dest="device_serial", required=False,
                        help="The serial number of target device (use `adb devices` to find)")
    
    #lccc-1
    parser.add_argument("-a", action="store", dest="apk_path",
                        help="The file path to target APK", default=extracted_info[0]['app'])
    parser.add_argument("-o", action="store", dest="output_dir", 
                        help="directory of output", default="drb_output/"+str(episode))
    parser.add_argument("-task", action="store", dest="task",
                        help="the task to execute, in natural language", default=extracted_info[0]['task'])
    # parser.add_argument("-step", action="store", dest="step",
                        # help="whether generation is required for this task", default=0)
    parser.add_argument("-extracted_info", action="store", dest="extracted_info",
                        help="The extracted information of test case steps", default=extracted_info)
    
    parser.add_argument("-ac", action="store", dest="ac",
                        help="Android Controller", default=ac)

    #lccc-2

    parser.add_argument("-script", action="store", dest="script_path",
                        help="Use a script to customize input for certain states.")
    parser.add_argument("-count", action="store", dest="count", default=input_manager.DEFAULT_EVENT_COUNT, type=int,
                        help="Number of events to generate in total. Default: %d" % input_manager.DEFAULT_EVENT_COUNT)
    parser.add_argument("-interval", action="store", dest="interval", default=input_manager.DEFAULT_EVENT_INTERVAL,
                        type=int,
                        help="Interval in seconds between each two events. Default: %d" % input_manager.DEFAULT_EVENT_INTERVAL)
    parser.add_argument("-timeout", action="store", dest="timeout", default=input_manager.DEFAULT_TIMEOUT, type=int,
                        help="Timeout in seconds, -1 means unlimited. Default: %d" % input_manager.DEFAULT_TIMEOUT)
    parser.add_argument("-debug", action="store_true", dest="debug_mode",
                        help="Run in debug mode (dump debug messages).")
    parser.add_argument("-keep_app", action="store_true", dest="keep_app", default=True,
                        help="Keep the app on the device after testing.")
    parser.add_argument("-keep_env", action="store_true", dest="keep_env",
                        help="Keep the test environment (eg. minicap and accessibility service) after testing.")
    parser.add_argument("-grant_perm", action="store_true", dest="grant_perm",
                        help="Grant all permissions while installing. Useful for Android 6.0+.")
    parser.add_argument("-is_emulator", action="store_true", dest="is_emulator",
                        help="Declare the target device to be an emulator, which would be treated specially by DroidBot.")
    parser.add_argument("-accessibility_auto", action="store_true", dest="enable_accessibility_hard",
                        help="Enable the accessibility service automatically even though it might require device restart\n(can be useful for Android API level < 23).")
    parser.add_argument("-ignore_ad", action="store_true", dest="ignore_ad",
                        help="Ignore Ad views by checking resource_id.")
    options = parser.parse_args()
    # print options
    return options

def explore(extracted_info, ac, episode):
    opts = parse_args(extracted_info, ac, episode)

    if not os.path.exists(opts.apk_path):
        print("APK does not exist.")########Stuck here
        return
    print(opts)
    print("-----------------------------")
    droidbot = DroidBot(
        app_path=opts.apk_path,
        device_serial=opts.device_serial,
        task=opts.task,
        # step=opts.step,
        extracted_info=opts.extracted_info,
        ac = opts.ac,
        is_emulator=opts.is_emulator,
        output_dir=opts.output_dir,
        env_policy=env_manager.POLICY_NONE,
        policy_name=input_manager.POLICY_STEPTASK,
        script_path=opts.script_path,
        event_interval=opts.interval,
        timeout=opts.timeout,
        event_count=opts.count,
        debug_mode=opts.debug_mode,
        keep_app=opts.keep_app,
        keep_env=opts.keep_env,
        grant_perm=opts.grant_perm,
        enable_accessibility_hard=opts.enable_accessibility_hard,
        ignore_ad=opts.ignore_ad)
    droidbot.start()
    
def pre_download_APK():
    device_serial = f"emulator-{emulator_controller_args['port']}"  # 设备序列号
    app = PrepareApps(device_serial)
    app.pull_installed_apps('llamatouch_apps', TASK_METADATA_PATH)


def run_on_agentenv():  

    ac = AndroidController(
        avd_name=AVD_NAME,
        emulator_controller_args=emulator_controller_args,
        local_output_path="exec_output",
        max_steps=15,
        instruction_fp=TASK_METADATA_PATH,
    )

    # setup AgentEnv: load emulator, connect to emulator, back to home.
    ac.set_up()
    
    for _ in range(first_n_episodes): # iterate through the first n episodes
        try:
            # get instruction from AgentEnv
            task_description, gr_path, app_short, episode = ac.get_instruction()
            if task_description is None: 
                break
            # if app_short not in ["Settings"]:
            #     continue

            print(f"Current instruction: {task_description}")
            
            # setup task environment if needed
            # print(f"setting up task {task_description}...")

            
            # go to the dropdown s
            # print(f"swipe up the screen")
            # ac.device.swipe(500, 1500, 500, 500) #upstairs, x then y
            
            # time.sleep(2)
            
            # 从dataset/llamatouch_dataset_0521数据集中提取apk，优先从end_no.activity中提取包名，其次从end_no.vh中提取，对apk进行检验；adb shell pm list packages；adb shell pm path <package_name>； adb pull /data/app/com.example.myapp-1/base.apk /path/to/save/base.apk； 然后初始化APK
            # subTasks = get_extracted_steps(task_description, app_short)
            if  (not 'webshopping' in gr_path):
                continue
            ac.setup_task(task_description) # some tasks need to setup preparation before execution
            ac.device.disconnect()
            similarTasks, subTasks = get_reference_steps(task_description, app_short, 3)
            ac.save_intructions(similarTasks, subTasks)
            
            explore(subTasks, ac, episode)
 
            # save the last environment state of an episode
            # ac.get_state() #这里需要吗
            # reset the environment for next task, reload_snapshot and reconnect using u2d
            ac.reset_env()

        except Exception as e:
            print(f"Error in task {task_description}: {e}")
            # remove content in folder os.path.join("exec_output", "captured_data")
            os.system(f"rm -r {os.path.join('exec_output', 'captured_data')}")
            import traceback
            traceback.print_exc()

            # reset the environment and go to next task
            ac.reset_env()
            continue
    
    # Execution finished, close AgentEnv：disconnect u2d and close emulator using subprocess.Popen(cmd)
    ac.tear_down()


if __name__ == "__main__":
    start_time = datetime.now()
    run_on_agentenv()
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time}")
    # pre_download_APK()
