python3 start.py -a ../Data_AutoDroid/apks/com.simplemobiletools.calendar_3.4.2-118_minAPI16.apk -o output/calendar -is_emulator 
-task "create a event of laundry at 11:00am on 2024-3-29" -keep_env -keep_app

    -a ../Data_AutoDroid/apks/com.simplemobiletools.calendar_3.4.2-118_minAPI16.apk -o output/calendar -is_emulator 
    -task "change the event reminder sound of Calendar app to adara" -keep_env -keep_app

python3 -m droidbot.start -a ../Data_AutoDroid/apks/com.simplemobiletools.calendar_3.4.2-118_minAPI16.apk -o output/calendar -is_emulator -policy replay -replay_output DroidTask/calendar/ 
