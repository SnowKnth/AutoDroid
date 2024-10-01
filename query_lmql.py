import lmql

async def prompt_llm_with_history(task, history, ui_desc, ids):
    query_str = f'''
    """You are a smartphone assistant to help users complete tasks by interacting with mobile apps.
    Given a task, the previous UI actions, and the content of the current UI state, your job is to decide whether the task is already finished by the previous actions, and if not, decide which UI element in the current UI state should be interacted with.
    
    Task: {task}
    Previous UI actions: {history}
    Current UI State: {ui_desc}

    Your answer should always use the following format:
    
    1. Completing this task on a smartphone usually involves these steps: <?>.
    2. Analyses of the relations between the task and the previous UI actions and current UI state: <?>.
    3. Based on the previous actions, is the task already finished? <Y/N>. The next step should be <?/None>.
    4. Can the task be proceeded with the current UI state? <Y/N>. Fill in the blanks about the next one interaction:
       - id=<id number>
       - action=<tap/input>
       - input text=<text or N/A>
    
    - id=[ID] - action=[ACTION] - input text=[INPUT_TEXT]. """ 
    where ACTION in ["tap", "input", "N/A"] 
    and ID in {ids} 
    and len(TOKENS(INPUT_TEXT)) < 6

    return ID, ACTION, INPUT_TEXT
    '''

    result = await lmql.run(query_str, model="openai/gpt-3.5-turbo", decoder='argmax')
    return result



# import lmql
# import os
# import openai
# model=lmql.model("openai/gpt-3.5-turbo-instruct") # OpenAI API model
# # model=lmql.model("llama.cpp:<YOUR_WEIGHTS>.gguf") # llama.cpp model
# @lmql.query(model=model,decoder='argmax')
# def prompt_llm_with_history(task,history,ui_desc,ids):
#     '''lmql
#     """You are a smartphone assistant to help users complete tasks by interacting with mobile apps.Given a task, the previous UI actions, and the content of current UI state, your job is to decide whether the task is already finished by the previous actions, and if not, decide which UI element in current UI state should be interacted.
#         Task:{task}
#         Previous UI actions: {history}
#         Current UI State:{ui_desc}
#         Your answer should always use the following format:1. Completing this task on a smartphone usually involves these steps: <?>.\n2. Analyses of the relations between the task and the previous UI actions and current UI state: <?>.\n3. Based on the previous actions, is the task already finished? <Y/N>. The next step should be <?/None>.\n4. Can the task be proceeded with the current UI state? <Y/N>. Fill in the blanks about the next one interaction: - id=<id number> - action=<tap/input> - input text=<text or N/A>
#         - id=[ID] - action=[ACTION] - input text=[INPUT_TEXT]. """ where ACTION in ["tap", "input", "N/A"] and ID in {ids} and len(TOKENS(INPUT_TEXT))<6

#     return ID,ACTION,INPUT_TEXT
#     '''
