import os
import sys
import time
import argparse
import logging
from droidbot.droidbot import DroidBot
from droidbot import input_manager
from droidbot import env_manager
from datetime import datetime    
sys.path.insert(0, os.environ.get("AGENTENV_PATH"))
from environment import AndroidController, PrepareApps
TASK_METADATA_PATH = "../dataset/llamatouch_task_metadata.tsv"
if __name__ == "__main__":
    avd_name, port, AgentEnv_output_dir =  "Copy3_of_p6a", "5556", "exec_output"
    emulator_controller_args = {
        "snapshot" : "default_boot",
        "port" : port,        # If port is occupied, please switch to 5556, 5558... and so forth
        "no-window" : "true",  # Change this to "true" to run the emulator without GUI.
    }
    ac = AndroidController(
        avd_name=avd_name,
        emulator_controller_args=emulator_controller_args,
        local_output_path=AgentEnv_output_dir,
        max_steps=20,
        instruction_fp=TASK_METADATA_PATH,
    )
    for index in range(495):
        task_description, gr_path, app_short, episode, full_path = ac.get_instruction() 
        apk_path =f"llamatouch_apps/{app_short}.apk"
        if not os.path.exists(apk_path):
            print(f"APK does not exist:{index};{apk_path}")########Stuck here