@echo off
cd /d D:\BIRETOS\projects\biretos-automation

REM 1. Collect all experience data (training pairs)
C:\Users\eugene\AppData\Local\Programs\Python\Python311\python.exe -X utf8 scripts\pipeline_v2\collect_all_experience.py >> downloads\training_v2\auto_trigger.log 2>&1

REM 2. Check thresholds and trigger fine-tune if ready
C:\Users\eugene\AppData\Local\Programs\Python\Python311\python.exe -X utf8 scripts\pipeline_v2\auto_pipeline_hook.py >> downloads\training_v2\auto_trigger.log 2>&1
