import re
response = "Given the current state and options, the next step to effectively continue testing the 'Search for the new nike air max shoes on Nike.' feature would be to input your search term into the search bar. However, since the search bar is represented as an input field and not a button, you will need to simulate entering text into that field. Since you need to input 'Air Max shoes' into the search bar, you need to first interact with the input field (which is currently present as id=3). The action you want to perform is to select that input field to enter your search term. Thus, the recommended action ID is as follows: action id: 3"
# conversation += f"    Prompt:\n{prompt}\n" + f"    Response:\n{response}\n"
if 'action id' in response.lower():
    response = response.lower().split("action id")[1]    
match = re.search(r'\d+', response)

finish = 0
# 判断是否已经执行到后面的task了
if not match:
    print("Not match")