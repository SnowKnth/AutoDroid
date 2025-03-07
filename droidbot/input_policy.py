import sys
import json
import re
import logging
import random
from abc import abstractmethod
import yaml
import copy
import requests
import ast
import ipdb

from .input_event import *
from .utg import UTG
import time
from .input_event import ScrollEvent
# from memory.memory_builder import Memory
import tools
import pdb
import os
from query_lmql import prompt_llm_with_history
from openai import OpenAI
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Max number of restarts
MAX_NUM_RESTARTS = 5
# Max number of steps outside the app
MAX_NUM_STEPS_OUTSIDE = 1000
MAX_NUM_STEPS_OUTSIDE_KILL = 1000
# Max number of replay tries
MAX_REPLY_TRIES = 5

# Some input event flags
EVENT_FLAG_STARTED = "+started"
EVENT_FLAG_START_APP = "+start_app"
EVENT_FLAG_STOP_APP = "+stop_app"
EVENT_FLAG_EXPLORE = "+explore"
EVENT_FLAG_NAVIGATE = "+navigate"
EVENT_FLAG_TOUCH = "+touch"

# Policy taxanomy
POLICY_NAIVE_DFS = "dfs_naive"
POLICY_GREEDY_DFS = "dfs_greedy"
POLICY_NAIVE_BFS = "bfs_naive"
POLICY_GREEDY_BFS = "bfs_greedy"
POLICY_REPLAY = "replay"
POLICY_MANUAL = "manual"
POLICY_MONKEY = "monkey"
POLICY_TASK = "task"
POLICY_STEPTASK = "steptask"
POLICY_NONE = "none"
POLICY_MEMORY_GUIDED = "memory_guided"  # implemented in input_policy2
FINISHED = "task_completed"
MAX_SCROLL_NUM = 7
USE_LMQL = False

class InputInterruptedException(Exception):
    pass

def safe_dict_get(view_dict, key, default=None):
    return_itm = view_dict[key] if (key in view_dict) else default
    if return_itm == None:
        return_itm = ''
    return return_itm

class InputPolicy(object):
    """
    This class is responsible for generating events to stimulate more app behaviour
    It should call AppEventManager.send_event method continuously
    """

    def __init__(self, device, app):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.device = device
        self.app = app
        self.action_count = 0
        self.master = None

    def start(self, input_manager):
        """
        start producing events
        :param input_manager: instance of InputManager
        """
        self.action_count = 0
        start_time = 0
        while input_manager.enabled and self.action_count < input_manager.event_count:
            try:
                # # make sure the first event is go to HOME screen
                # # the second event is to start the app
                # if self.action_count == 0 and self.master is None:
                #     event = KeyEvent(name="HOME")
                # elif self.action_count == 1 and self.master is None:
                #     event = IntentEvent(self.app.get_start_intent())
                if self.action_count == 0 and self.master is None:
                    event = KillAppEvent(app=self.app)
                else:
                    event = self.generate_event(input_manager)
                
                if event == None or event == FINISHED:
                    end_time = time.time()
                    last_time = end_time - start_time
                    self.logger.info(
                        "Have finish the search and the action number is %s/logger_info.txt" % self.action_count)  # Todo: how to get info string
                    self.logger.info("save output_file is %s" % input_manager.output_dir)
                    info_str = "Have finished the search and the action number is " + str(self.action_count)
                    time_str = "Lasting time is " + str(last_time)
                    if input_manager.output_dir is not None:
                        logger_info_file_name = "%s/logger_info.txt" % (input_manager.output_dir)
                        logger_info_file = open(logger_info_file_name, "w")
                        logger_info_file.writelines(info_str)
                        logger_info_file.writelines("\n")
                        logger_info_file.writelines(time_str)
                        logger_info_file.close()
                    break
                input_manager.add_event(event)#output event and its views(.png) into disk
            except KeyboardInterrupt:
                break
            except InputInterruptedException as e:
                self.logger.warning("stop sending events: %s" % e)
                break
            # except RuntimeError as e:
            #     self.logger.warning(e.message)
            #     break
            except Exception as e:
                self.logger.warning("exception during sending events: %s" % e)
                import traceback
                traceback.print_exc()
                continue
            self.action_count += 1
        # if cannot finish the search with the action_max_count
        if self.action_count >= input_manager.event_count:
            self.logger.info("Cannot finish the search within action number is %s" % input_manager.event_count)
            self.logger.info("save output_file is %s" % self.output_dir)
            info_str = "Cannot finish the search within action number is " + str(input_manager.event_count)
            end_time = time.time()
            last_time = end_time - start_time
            time_str = "last time is " + str(last_time)
            if input_manager.output_dir is not None:
                logger_info_file_name = "%s/logger_info.txt" % (input_manager.output_dir)
                logger_info_file = open(logger_info_file_name, "w")
                logger_info_file.writelines(info_str)
                logger_info_file.writelines("\n")
                logger_info_file.writelines(time_str)
                logger_info_file.close()
        else:
            # since the time_limit  is up and cannot completion
            self.logger.info("Reach the time limit or event == FINISHED, and the action number is %s" % self.action_count)
            self.logger.info("save output_file is %s" % input_manager.output_dir)
            info_str = 'Reach the time limit and the action number is' + str(self.action_count)
            end_time = time.time()
            last_time = end_time - start_time
            time_str = "last time is " + str(last_time)
            if input_manager.output_dir is not None:
                logger_info_file_name = "%s/logger_info.txt" % (input_manager.output_dir)
                logger_info_file = open(logger_info_file_name, "w")
                logger_info_file.writelines(info_str)
                logger_info_file.writelines("\n")
                logger_info_file.writelines(time_str)
                logger_info_file.close()
        self.logger.info("time cost:", time.time() - start_time)

    @abstractmethod
    def generate_event(self, input_manager):
        """
        generate an event
        @return:
        """
        pass


class NoneInputPolicy(InputPolicy):
    """
    do not send any event
    """

    def __init__(self, device, app):
        super(NoneInputPolicy, self).__init__(device, app)

    def generate_event(self):
        """
        generate an event
        @return:
        """
        return None


class UtgBasedInputPolicy(InputPolicy):
    """
    state-based input policy
    """

    def __init__(self, device, app, random_input):
        super(UtgBasedInputPolicy, self).__init__(device, app)
        self.random_input = random_input
        self.script = None
        self.master = None
        self.script_events = []
        self.last_event = None
        self.last_state = None
        self.current_state = None
        self.current_operation = None
        self.utg = UTG(device=device, app=app, random_input=random_input)
        self.script_event_idx = 0
        if self.device.humanoid is not None:
            self.humanoid_view_trees = []
            self.humanoid_events = []
        self.script_target_view = None

    def generate_event(self, input_manager):
        """
        generate an event
        @return:
        """

        # Get current device state
        self.current_state = self.device.get_current_state()
        if self.current_state is None: #这里相当于两个事件（包括Key_BACK）到达一个可获得的状态，在input_event.py中是否要封装复合事件从而能同时包含两个事件
            import time
            time.sleep(5)
            if  isinstance(self, StepTaskPolicy):
                return 0, KeyEvent(name="BACK")
            else:
                return KeyEvent(name="BACK")

        if self.last_event is not None:#对应finish==-1(跳过)的情况
            self.__update_utg()#update utg in memory, also export to utg.json ; output states(.png and .json) here

        # update last view trees for humanoid
        if self.device.humanoid is not None:
            self.humanoid_view_trees = self.humanoid_view_trees + [self.current_state.view_tree]
            if len(self.humanoid_view_trees) > 4:
                self.humanoid_view_trees = self.humanoid_view_trees[1:]

        event = None

        # if the previous event in operation in the script is not finished, continue
        if len(self.script_events) > self.script_event_idx:
            event = self.script_events[self.script_event_idx].get_transformed_event(self)
            self.script_event_idx += 1

        # if the previous operation is finished or firstly start, first try matching a state defined in the script
        if event is None and self.script is not None:
            operation = self.script.get_operation_based_on_state_norepeat(self.current_state)
            if operation is not None:
                self.script_events = operation.events
                # restart script
                event = self.script_events[0].get_transformed_event(self)
                self.script_event_idx = 1
                import time
                time.sleep(3)
        # no operation matched in the state for script
        if event is None:
            if isinstance(self, TaskPolicy):
                old_state, event = self.generate_event_based_on_utg(input_manager)
            elif isinstance(self, StepTaskPolicy):
                old_state = None
                finish, event = self.generate_event_based_on_utg(input_manager)
            else:
                old_state = None
                event = self.generate_event_based_on_utg(input_manager)
            # import time
            # time.sleep(3)
        else:
            old_state = None
        
        # update last events for humanoid
        if self.device.humanoid is not None:
            self.humanoid_events = self.humanoid_events + [event]
            if len(self.humanoid_events) > 3:
                self.humanoid_events = self.humanoid_events[1:]

        self.last_state = self.current_state if old_state is None else old_state
        self.last_event = event
        if isinstance(self, StepTaskPolicy):
            return finish, event
        else:
            return event

    def __update_utg(self):
        self.utg.add_transition(self.last_event, self.last_state, self.current_state) #add utg in memory, also export to utg.json ; also export to states(.png and .json)

    @abstractmethod
    def generate_event_based_on_utg(self, input_manager):
        """
        generate an event based on UTG
        :return: InputEvent
        """
        pass


class UtgNaiveSearchPolicy(UtgBasedInputPolicy):
    """
    depth-first strategy to explore UFG (old)
    """

    def __init__(self, device, app, random_input, search_method):
        super(UtgNaiveSearchPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.explored_views = set()
        self.state_transitions = set()
        self.search_method = search_method

        self.last_event_flag = ""
        self.last_event_str = None
        self.last_state = None

        self.preferred_buttons = ["yes", "ok", "activate", "detail", "more", "access",
                                  "allow", "check", "agree", "try", "go", "next"]

    def generate_event_based_on_utg(self):
        """
        generate an event based on current device state
        note: ensure these fields are properly maintained in each transaction:
          last_event_flag, last_touched_view, last_state, exploited_views, state_transitions
        @return: InputEvent
        """
        self.save_state_transition(self.last_event_str, self.last_state, self.current_state)

        if self.device.is_foreground(self.app):
            # the app is in foreground, clear last_event_flag
            self.last_event_flag = EVENT_FLAG_STARTED
        else:
            number_of_starts = self.last_event_flag.count(EVENT_FLAG_START_APP)
            # If we have tried too many times but the app is still not started, stop DroidBot
            if number_of_starts > MAX_NUM_RESTARTS:
                raise InputInterruptedException("The app cannot be started.")

            # if app is not started, try start it
            if self.last_event_flag.endswith(EVENT_FLAG_START_APP):
                # It seems the app stuck at some state, and cannot be started
                # just pass to let viewclient deal with this case
                self.logger.info("The app had been restarted %d times.", number_of_starts)
                self.logger.info("Trying to restart app...")
                pass
            else:
                start_app_intent = self.app.get_start_intent()

                self.last_event_flag += EVENT_FLAG_START_APP
                self.last_event_str = EVENT_FLAG_START_APP
                return IntentEvent(start_app_intent)

        # select a view to click
        view_to_touch = self.select_a_view(self.current_state)

        # if no view can be selected, restart the app
        if view_to_touch is None:
            stop_app_intent = self.app.get_stop_intent()
            self.last_event_flag += EVENT_FLAG_STOP_APP
            self.last_event_str = EVENT_FLAG_STOP_APP
            return IntentEvent(stop_app_intent)

        view_to_touch_str = view_to_touch['view_str']
        if view_to_touch_str.startswith('BACK'):
            result = KeyEvent('BACK')
        else:
            result = TouchEvent(view=view_to_touch)

        self.last_event_flag += EVENT_FLAG_TOUCH
        self.last_event_str = view_to_touch_str
        self.save_explored_view(self.current_state, self.last_event_str)
        return result

    def select_a_view(self, state):
        """
        select a view in the view list of given state, let droidbot touch it
        @param state: DeviceState
        @return:
        """
        views = []
        for view in state.views:
            if view['enabled'] and len(view['children']) == 0:
                views.append(view)

        if self.random_input:
            random.shuffle(views)

        # add a "BACK" view, consider go back first/last according to search policy
        mock_view_back = {'view_str': 'BACK_%s' % state.foreground_activity,
                          'text': 'BACK_%s' % state.foreground_activity}
        if self.search_method == POLICY_NAIVE_DFS:
            views.append(mock_view_back)
        elif self.search_method == POLICY_NAIVE_BFS:
            views.insert(0, mock_view_back)

        # first try to find a preferable view
        for view in views:
            view_text = view['text'] if view['text'] is not None else ''
            view_text = view_text.lower().strip()
            if view_text in self.preferred_buttons \
                    and (state.foreground_activity, view['view_str']) not in self.explored_views:
                self.logger.info("selected an preferred view: %s" % view['view_str'])
                return view

        # try to find a un-clicked view
        for view in views:
            if (state.foreground_activity, view['view_str']) not in self.explored_views:
                self.logger.info("selected an un-clicked view: %s" % view['view_str'])
                return view

        # if all enabled views have been clicked, try jump to another activity by clicking one of state transitions
        if self.random_input:
            random.shuffle(views)
        transition_views = {transition[0] for transition in self.state_transitions}
        for view in views:
            if view['view_str'] in transition_views:
                self.logger.info("selected a transition view: %s" % view['view_str'])
                return view

        # no window transition found, just return a random view
        # view = views[0]
        # self.logger.info("selected a random view: %s" % view['view_str'])
        # return view

        # DroidBot stuck on current state, return None
        self.logger.info("no view could be selected in state: %s" % state.tag)
        return None

    def save_state_transition(self, event_str, old_state, new_state):
        """
        save the state transition
        @param event_str: str, representing the event cause the transition
        @param old_state: DeviceState
        @param new_state: DeviceState
        @return:
        """
        if event_str is None or old_state is None or new_state is None:
            return
        if new_state.is_different_from(old_state):
            self.state_transitions.add((event_str, old_state.tag, new_state.tag))

    def save_explored_view(self, state, view_str):
        """
        save the explored view
        @param state: DeviceState, where the view located
        @param view_str: str, representing a view
        @return:
        """
        if not state:
            return
        state_activity = state.foreground_activity
        self.explored_views.add((state_activity, view_str))


class UtgGreedySearchPolicy(UtgBasedInputPolicy):
    """
    DFS/BFS (according to search_method) strategy to explore UFG (new)
    """

    def __init__(self, device, app, random_input, search_method):
        super(UtgGreedySearchPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.logger = logging.getLogger('Log2File')
        self.search_method = search_method

        self.preferred_buttons = ["yes", "ok", "activate", "detail", "more", "access",
                                  "allow", "check", "agree", "try", "go", "next"]

        self.__nav_target = None
        self.__nav_num_steps = -1
        self.__num_restarts = 0
        self.__num_steps_outside = 0
        self.__event_trace = ""
        self.__missed_states = set()
        self.__random_explore = False

    def generate_event_based_on_utg(self, input_manager):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        current_state = self.current_state
        self.logger.info("Current state: %s" % current_state.state_str)
        if current_state.state_str in self.__missed_states:
            self.__missed_states.remove(current_state.state_str)

        if current_state.get_app_activity_depth(self.app) < 0:
            # If the app is not in the activity stack
            start_app_intent = self.app.get_start_intent()

            # It seems the app stucks at some state, has been
            # 1) force stopped (START, STOP)
            #    just start the app again by increasing self.__num_restarts
            # 2) started at least once and cannot be started (START)
            #    pass to let viewclient deal with this case
            # 3) nothing
            #    a normal start. clear self.__num_restarts.

            if self.__event_trace.endswith(EVENT_FLAG_START_APP + EVENT_FLAG_STOP_APP) \
                    or self.__event_trace.endswith(EVENT_FLAG_START_APP):
                self.__num_restarts += 1
                self.logger.info("The app had been restarted %d times.", self.__num_restarts)
            else:
                self.__num_restarts = 0

            # pass (START) through
            if not self.__event_trace.endswith(EVENT_FLAG_START_APP):
                if self.__num_restarts > MAX_NUM_RESTARTS:
                    # If the app had been restarted too many times, enter random mode
                    msg = "The app had been restarted too many times. Entering random mode."
                    self.logger.info(msg)
                    self.__random_explore = True
                else:
                    # Start the app
                    self.__event_trace += EVENT_FLAG_START_APP
                    self.logger.info("Trying to start the app...")
                    return IntentEvent(intent=start_app_intent)

        elif current_state.get_app_activity_depth(self.app) > 0:
            # If the app is in activity stack but is not in foreground
            self.__num_steps_outside += 1

            if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE:
                # If the app has not been in foreground for too long, try to go back
                if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE_KILL:
                    stop_app_intent = self.app.get_stop_intent()
                    go_back_event = IntentEvent(stop_app_intent)
                else:
                    go_back_event = KeyEvent(name="BACK")
                self.__event_trace += EVENT_FLAG_NAVIGATE
                self.logger.info("Going back to the app...")
                return go_back_event
        else:
            # If the app is in foreground
            self.__num_steps_outside = 0

        # Get all possible input events
        possible_events = current_state.get_possible_input()

        if self.random_input:
            random.shuffle(possible_events)

        if self.search_method == POLICY_GREEDY_DFS:
            possible_events.append(KeyEvent(name="BACK"))
        elif self.search_method == POLICY_GREEDY_BFS:
            possible_events.insert(0, KeyEvent(name="BACK"))

        # get humanoid result, use the result to sort possible events
        # including back events
        if self.device.humanoid is not None:
            possible_events = self.__sort_inputs_by_humanoid(possible_events)

        # If there is an unexplored event, try the event first
        for input_event in possible_events:
            if not self.utg.is_event_explored(event=input_event, state=current_state):
                self.logger.info("Trying an unexplored event.")
                self.__event_trace += EVENT_FLAG_EXPLORE
                return input_event

        target_state = self.__get_nav_target(current_state)
        if target_state:
            navigation_steps = self.utg.get_navigation_steps(from_state=current_state, to_state=target_state)
            if navigation_steps and len(navigation_steps) > 0:
                self.logger.info("Navigating to %s, %d steps left." % (target_state.state_str, len(navigation_steps)))
                self.__event_trace += EVENT_FLAG_NAVIGATE
                return navigation_steps[0][1]

        if self.__random_explore:
            self.logger.info("Trying random event.")
            random.shuffle(possible_events)
            return possible_events[0]

        # If couldn't find a exploration target, stop the app
        stop_app_intent = self.app.get_stop_intent()
        self.logger.info("Cannot find an exploration target. Trying to restart app...")
        self.__event_trace += EVENT_FLAG_STOP_APP
        return IntentEvent(intent=stop_app_intent)

    def __sort_inputs_by_humanoid(self, possible_events):
        if sys.version.startswith("3"):
            from xmlrpc.client import ServerProxy
        else:
            from xmlrpclib import ServerProxy
        proxy = ServerProxy("http://%s/" % self.device.humanoid)
        request_json = {
            "history_view_trees": self.humanoid_view_trees,
            "history_events": [x.__dict__ for x in self.humanoid_events],
            "possible_events": [x.__dict__ for x in possible_events],
            "screen_res": [self.device.display_info["width"],
                           self.device.display_info["height"]]
        }
        result = json.loads(proxy.predict(json.dumps(request_json)))
        new_idx = result["indices"]
        text = result["text"]
        new_events = []

        # get rid of infinite recursive by randomizing first event
        if not self.utg.is_state_reached(self.current_state):
            new_first = random.randint(0, len(new_idx) - 1)
            new_idx[0], new_idx[new_first] = new_idx[new_first], new_idx[0]

        for idx in new_idx:
            if isinstance(possible_events[idx], SetTextEvent):
                possible_events[idx].text = text
            new_events.append(possible_events[idx])
        return new_events

    def __get_nav_target(self, current_state):
        # If last event is a navigation event
        if self.__nav_target and self.__event_trace.endswith(EVENT_FLAG_NAVIGATE):
            navigation_steps = self.utg.get_navigation_steps(from_state=current_state, to_state=self.__nav_target)
            if navigation_steps and 0 < len(navigation_steps) <= self.__nav_num_steps:
                # If last navigation was successful, use current nav target
                self.__nav_num_steps = len(navigation_steps)
                return self.__nav_target
            else:
                # If last navigation was failed, add nav target to missing states
                self.__missed_states.add(self.__nav_target.state_str)

        reachable_states = self.utg.get_reachable_states(current_state)
        if self.random_input:
            random.shuffle(reachable_states)

        for state in reachable_states:
            # Only consider foreground states
            if state.get_app_activity_depth(self.app) != 0:
                continue
            # Do not consider missed states
            if state.state_str in self.__missed_states:
                continue
            # Do not consider explored states
            if self.utg.is_state_explored(state):
                continue
            self.__nav_target = state
            navigation_steps = self.utg.get_navigation_steps(from_state=current_state, to_state=self.__nav_target)
            if len(navigation_steps) > 0:
                self.__nav_num_steps = len(navigation_steps)
                return state

        self.__nav_target = None
        self.__nav_num_steps = -1
        return None


class UtgReplayPolicy(InputPolicy):
    """
    Replay DroidBot output generated by UTG policy
    """

    def __init__(self, device, app, replay_output):
        super(UtgReplayPolicy, self).__init__(device, app)
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.logger = logging.getLogger('Log2File')
        self.replay_output = replay_output

        import os
        event_dir = os.path.join(replay_output, "events")
        self.event_paths = sorted([os.path.join(event_dir, x) for x in
                                   next(os.walk(event_dir))[2]
                                   if x.endswith(".json")])
        # skip HOME and start app intent
        self.device = device
        self.app = app
        self.event_idx = 2
        self.num_replay_tries = 0
        self.utg = UTG(device=device, app=app, random_input=None)
        self.last_event = None
        self.last_state = None
        self.current_state = None
        self.__num_steps_outside = 0

    def generate_event(self, input_manager):
        """
        generate an event based on replay_output
        @return: InputEvent
        """
        import time

            
            
        while self.event_idx < len(self.event_paths) and self.num_replay_tries < MAX_REPLY_TRIES:
            self.num_replay_tries += 1
            current_state = self.device.get_current_state()
            if current_state is None:
                time.sleep(5)
                self.num_replay_tries = 0
                return KeyEvent(name="BACK")
            elif current_state.get_app_activity_depth(self.app) < 0:
                # If the app is not in the activity stack
                start_app_intent = self.app.get_start_intent()
                return IntentEvent(start_app_intent)
                # pass (START) through


            elif current_state.get_app_activity_depth(self.app) > 0:
                # If the app is in activity stack but is not in foreground
                self.__num_steps_outside += 1

                if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE:
                    # If the app has not been in foreground for too long, try to go back
                    if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE_KILL:
                        stop_app_intent = self.app.get_stop_intent()
                        go_back_event = IntentEvent(stop_app_intent)
                    else:
                        go_back_event = KeyEvent(name="BACK")
                    return go_back_event
            else:
                # If the app is in foreground
                self.__num_steps_outside = 0
                
                
            curr_event_idx = self.event_idx
            self.__update_utg()
            while curr_event_idx < len(self.event_paths):
                event_path = self.event_paths[curr_event_idx]   
                with open(event_path, "r") as f:
                    curr_event_idx += 1

                    try:
                        event_dict = json.load(f)
                    except Exception as e:
                        self.logger.info("Loading %s failed" % event_path)
                        continue

                    if event_dict["start_state"] != current_state.state_str:
                        logging.info('overlooked event %s,%s,%s,%s and continued matching (first event is with index 0)\n' % (curr_event_idx,event_path,event_dict["start_state"],current_state.state_str))
                        time.sleep(4)
                        continue
                    if not self.device.is_foreground(self.app):
                        # if current app is in background, bring it to foreground
                        component = self.app.get_package_name()
                        if self.app.get_main_activity():
                            component += "/%s" % self.app.get_main_activity()
                        return IntentEvent(Intent(suffix=component))
                    
                    self.logger.info("Replaying %s" % event_path)
                    self.event_idx = curr_event_idx
                    self.num_replay_tries = 0
                    # return InputEvent.from_dict(event_dict["event"])
                    event = InputEvent.from_dict(event_dict["event"])
                    self.last_state = self.current_state
                    self.last_event = event
                    return event                    

            time.sleep(5)

        # raise InputInterruptedException("No more record can be replayed.")
    def __update_utg(self):
        self.utg.add_transition(self.last_event, self.last_state, self.current_state)


class ManualPolicy(UtgBasedInputPolicy):
    """
    manually explore UFG
    """

    def __init__(self, device, app):
        super(ManualPolicy, self).__init__(device, app, False)
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.logger = logging.getLogger('Log2File')

        self.__first_event = True

    def generate_event_based_on_utg(self, input_manager):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        if self.__first_event:
            self.__first_event = False
            self.logger.info("Trying to start the app...")
            start_app_intent = self.app.get_start_intent()
            return IntentEvent(intent=start_app_intent)
        else:
            return ManualEvent()


class TaskPolicy(UtgBasedInputPolicy):

    def __init__(self, device, app, random_input, task, use_memory=False, debug_mode=False):
        super(TaskPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.task = task

        self.__nav_target = None
        self.__nav_num_steps = -1
        self.__num_restarts = 0
        self.__num_steps_outside = 0
        self.__event_trace = ""
        self.__missed_states = set()
        self.__random_explore = random_input
        self.__action_history = []
        self.__thought_history = []
        self.use_memory = use_memory
        # if use_memory:
        #     self.memory = Memory(app_name=self.app.app_name, app_output_path=self.device.output_dir)
        if self.use_memory:
            self.similar_ele_path, self.similar_ele_function, self.similar_ele_statement = self.get_most_similar_element()
            if not self.similar_ele_function:
                self.use_memory = False
                self.logger.info('=============\nWarning: Did not find the memory of this app, the app memory is disabled\n=============')
            else:
                self.logger.info(f'============\nFound element: {self.similar_ele_statement}\nPath: {self.similar_ele_path}\nFunction: {self.similar_ele_function}\n============')
                self.state_ele_memory = {}  # memorize some important states that contain elements of insight

    def get_most_similar_element(self):
        """
        an example of return value for calendar app:  
        similar_ele_path: ["<button text='More options'></button>", '<button>Settings</button>', '<button>Reminder sound<br>Default (Pixie Dust)</button>']
        similar_ele_desc: 'task: change the reminder sound for calendar events to "Adara" on a smartphone.'
        similar_ele: '<checkbox checked=False>Adara</checkbox>'
        """
        from InstructorEmbedding import INSTRUCTOR
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        model = INSTRUCTOR('hkunlp/instructor-xl')
        task_embedding = model.encode('task: ' + self.task).reshape(1, -1)

        with open('memory/node_filtered_elements.json') as file:
            ele_statements = json.load(file)
        with open('memory/element_description.json') as file:#根据state
            ele_functions = json.load(file)
        with open('memory/embedded_elements_desc.json') as file:
            embeddings = json.load(file)
        app_name = self.device.output_dir.split('/')[-1]
        if app_name not in embeddings.keys():
            return None, None, None
        app_embeddings = embeddings[app_name]

        # similarities = {}
        max_similarity, similar_ele_idx = -9999, -9999
        for state_str, elements in app_embeddings.items():
            # if the target element is in the first ui, no onclick is needed
            # if ele_statements[app_name][state_str]['path'] == []:
            #     continue
            # similarities[state_str] = []
            for idx, ele in enumerate(elements):
                if ele:
                    npele = np.array(ele).reshape(1, -1)
                    similarity = cosine_similarity(task_embedding, npele)[0][0]
                else:
                    similarity = -9999
                # similarities[state_str].append(similarity)
                if similarity > max_similarity:
                    max_similarity = similarity
                    similar_ele_idx = idx
                    similar_state_str = state_str

        similar_ele = ele_statements[app_name][similar_state_str]['elements'][similar_ele_idx]
        similar_ele_path = ele_statements[app_name][similar_state_str]['path']
        similar_ele_desc = ele_functions[app_name][similar_state_str][similar_ele_idx]
        del model
        return similar_ele_path, similar_ele_desc, similar_ele
    
    def _scroll_to_top(self, scroller, all_views_for_mark, old_state=None):
        prefix_scroll_event = []
        if old_state is None:
            old_state = self.current_state 
        for _ in range(MAX_SCROLL_NUM):  # first scroll up to the top
            self.device.send_event(ScrollEvent(view=scroller, direction="UP"))
            scrolled_state = self.device.get_current_state()
            self.utg.add_transition(ScrollEvent(view=scroller, direction="UP"), old_state, scrolled_state)
            old_state = scrolled_state
            state_prompt, scrolled_candidate_actions, scrolled_views, _ = scrolled_state.get_described_actions()
            scrolled_new_views = []  # judge whether there is a new view after scrolling
            for scrolled_view in scrolled_views:
                if scrolled_view not in all_views_for_mark:
                    scrolled_new_views.append(scrolled_view)
                    all_views_for_mark.append(scrolled_view)
            if len(scrolled_new_views) == 0:
                break

            prefix_scroll_event.append(ScrollEvent(view=scroller, direction="UP"))
        return prefix_scroll_event


    def generate_event_based_on_utg(self, input_manager):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        current_state = self.current_state
        self.logger.info("Current state: %s" % current_state.state_str)
        if current_state.state_str in self.__missed_states:
            self.__missed_states.remove(current_state.state_str)

        if current_state.get_app_activity_depth(self.app) < 0:
            # If the app is not in the activity stack
            start_app_intent = self.app.get_start_intent()

            # It seems the app stucks at some state, has been
            # 1) force stopped (START, STOP)
            #    just start the app again by increasing self.__num_restarts
            # 2) started at least once and cannot be started (START)
            #    pass to let viewclient deal with this case
            # 3) nothing
            #    a normal start. clear self.__num_restarts.

            if self.__event_trace.endswith(EVENT_FLAG_START_APP + EVENT_FLAG_STOP_APP) \
                    or self.__event_trace.endswith(EVENT_FLAG_START_APP):
                self.__num_restarts += 1
                self.logger.info("The app had been restarted %d times.", self.__num_restarts)
            else:
                self.__num_restarts = 0

            # pass (START) through
            if not self.__event_trace.endswith(EVENT_FLAG_START_APP):
                if self.__num_restarts > MAX_NUM_RESTARTS:
                    # If the app had been restarted too many times, enter random mode
                    msg = "The app had been restarted too many times. Entering random mode."
                    self.logger.info(msg)
                    self.__random_explore = True
                else:
                    # Start the app
                    self.__event_trace += EVENT_FLAG_START_APP
                    self.logger.info("Trying to start the app...")
                    # self.__action_history = [f'- start the app {self.app.app_name}']
                    self.__action_history = [f'- launchApp {self.app.app_name}']
                    self.__thought_history = [f'launch the app {self.app.app_name} to finish the task {self.task}']
                    return None, IntentEvent(intent=start_app_intent)

        elif current_state.get_app_activity_depth(self.app) > 0:
            # If the app is in activity stack but is not in foreground
            self.__num_steps_outside += 1

            if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE:
                # If the app has not been in foreground for too long, try to go back
                if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE_KILL:
                    stop_app_intent = self.app.get_stop_intent()
                    go_back_event = IntentEvent(stop_app_intent)
                else:
                    go_back_event = KeyEvent(name="BACK")
                self.__event_trace += EVENT_FLAG_NAVIGATE
                self.logger.info("Going back to the app...")
                self.__action_history.append('- go back')
                self.__thought_history.append('the app has not been in foreground for too long, try to go back')
                return None, go_back_event
        else:
            # If the app is in foreground
            self.__num_steps_outside = 0
        
        
        scrollable_views = current_state.get_scrollable_views()#self._get_scrollable_views(current_state)
        
        if len(scrollable_views) > 0:
            '''
            if there is at least one scroller in the screen, we scroll each scroller many times until all the screens after scrolling have been recorded, you do not need to read
            '''
            # self.logger.info(scrollable_views)

            actions_dict = {}
            whole_state_views, whole_state_actions, whole_state_strs = [], [], []

            # state_strs = [current_state.state_str]
            state_prompt, current_candidate_actions, current_views, _ = current_state.get_described_actions()
            all_views_for_mark = copy.deepcopy(current_views)  # just for judging whether the screen has been scrolled up to the top

            for scrollerid in range(len(scrollable_views)):
                scroller = scrollable_views[scrollerid]
                # prefix_scroll_event = []
                actions_dict[scrollerid] = []

                prefix_scroll_event = self._scroll_to_top(scroller, all_views_for_mark)
                
                # after scrolling to the top, update the current_state
                top_state = self.device.get_current_state()
                state_prompt, top_candidate_actions, top_views, _ = top_state.get_described_actions()
                all_views_without_id, all_actions = top_views, top_candidate_actions

                too_few_item_time = 0

                for _ in range(MAX_SCROLL_NUM):  # then scroll down to the bottom
                    whole_state_strs.append(top_state.state_str)  # record the states from the top to the bottom
                    self.device.send_event(ScrollEvent(view=scroller, direction="DOWN"))
                    scrolled_state = self.device.get_current_state()
                    state_prompt, scrolled_candidate_actions, scrolled_views, _ = scrolled_state.get_described_actions()
                    
                    scrolled_new_views = []
                    for scrolled_view_id in range(len(scrolled_views)):
                        scrolled_view = scrolled_views[scrolled_view_id]
                        if scrolled_view not in all_views_without_id:
                            scrolled_new_views.append(scrolled_view)
                            all_views_without_id.append(scrolled_view)
                            all_actions.append(prefix_scroll_event + [ScrollEvent(view=scroller, direction="DOWN"), scrolled_candidate_actions[scrolled_view_id]])
                    # self.logger.info('found new views:', scrolled_new_views)
                    if len(scrolled_new_views) == 0:
                        break
                    
                    prefix_scroll_event.append(ScrollEvent(view=scroller, direction="DOWN"))

                    if len(scrolled_new_views) < 2:
                        too_few_item_time += 1
                    if too_few_item_time >= 2:
                        break

                    self.utg.add_transition(ScrollEvent(view=scroller, direction="DOWN"), top_state, scrolled_state)
                    top_state = scrolled_state
                
                # filter out the views that have been added to the whole_state by scrolling other scrollers
                for all_view_id in range(len(all_views_without_id)):
                    view = all_views_without_id[all_view_id]
                    if view not in whole_state_views:
                        whole_state_views.append(view)
                        whole_state_actions.append(all_actions[all_view_id])
                
                all_views_for_mark = []
                _ = self._scroll_to_top(scroller, all_views_for_mark, top_state)
            # self.logger.info(whole_state_views)
            action, candidate_actions, target_view, thought = self._get_action_from_views_actions(
                views=whole_state_views, candidate_actions=whole_state_actions, state_strs=whole_state_strs, action_history=self.__action_history, thought_history=self.__thought_history)

            if isinstance(action, list):  # the screen has to be scrolled first
                last_state = None
                for eventid in range(len(action) - 1):
                    self.device.send_event(action[eventid])
                    last_state = self.device.get_current_state()
                    # self.__action_history.append(current_state.get_action_desc(action[eventid]))
                self.__action_history.append(current_state.get_action_descv2(action[-1], target_view))
                self.__thought_history.append(thought)
                return last_state, action[-1]
            '''
            end for dealing with scrollers
            '''
        else:
            action, candidate_actions, target_view, thought = self._get_action_from_views_actions(
                current_state=current_state, action_history=self.__action_history, thought_history=self.__thought_history, state_strs=current_state.state_str)
        
        if action == FINISHED:
            return None, FINISHED
        if action is not None:
            self.__action_history.append(current_state.get_action_descv2(action, target_view))
            self.__thought_history.append(thought)
            return None, action

        if self.__random_explore:
            self.logger.info("Trying random event.")
            action = random.choice(candidate_actions)
            self.__action_history.append(current_state.get_action_descv2(action, target_view))
            self.__thought_history.append('random trying')
            return None, action

        # If couldn't find a exploration target, stop the app
        stop_app_intent = self.app.get_stop_intent()
        self.logger.info("Cannot find an exploration target. Trying to restart app...")
        self.__action_history.append('- stop the app')
        self.__thought_history.append("couldn't find a exploration target, stop the app")
        self.__event_trace += EVENT_FLAG_STOP_APP
        return None, IntentEvent(intent=stop_app_intent)
    
    def _save2yaml(self, file_name, state_prompt, idx, state_str, inputs='null'): 
        """Save and update the execution result in file like 'change the event reminder sound of Calendar app to adara.yaml (save wxd)'"""
        if not os.path.exists(file_name):
            tmp_data = {
            'task_name': self.task,
            'step_num': 0,
            'records': []
            }
            with open(file_name, 'w', encoding='utf-8') as f:
                yaml.dump(tmp_data, f)

        with open(file_name, 'r', encoding='utf-8') as f:
            old_yaml_data = yaml.safe_load(f)
        
        new_records = old_yaml_data['records']
        new_records.append(
                {'State': state_prompt,
                'Choice': idx,
                'Input': inputs,
                'state_str': state_str}
            )
        # import pdb;pdb.set_trace()
        data = {
            'task_name': self.task,
            'step_num': len(list(old_yaml_data['records'])),
            'records': new_records
        }
        with open(file_name, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
            
    def _make_prompt_lmql(self, state_prompt, action_history, is_text, state_str, view_text=None, thought_history=None, use_thoughts=False):
        if self.use_memory:
            # if isinstance(state_str, list):
            #     if len(state_str) == 1:
            #         state_str = state_str[0]
            #     else:
            #         state_str = self.memory.hash_state(state_prompt)
            # new_state_prompt = self.f(action_history, state_prompt, state_str)
            # if new_state_prompt !z= None and new_state_prompt != 'no_description':
            #     state_prompt = new_state_prompt
            if len(action_history) <= len(self.similar_ele_path):
                current_ui_id = len(action_history) - 1
                new_state_prompt = tools.insert_onclick_into_prompt(state_prompt, self.similar_ele_path[current_ui_id], self.similar_ele_function)
                if new_state_prompt != state_prompt:  # current state contains an element of insight
                    self.state_ele_memory[state_str] = new_state_prompt
                state_prompt = new_state_prompt
            # elif state_str in self.state_ele_memory.keys():
            #     state_prompt = self.state_ele_memory[state_str]

        if use_thoughts:
            history_with_thought = []
            for idx in range(len(action_history)):
                history_with_thought.append(action_history[idx] + ' Reason: ' + thought_history[idx])
        else:
            history_with_thought = action_history


        return '\n'.join(history_with_thought),state_prompt
    
    def _make_prompt(self, state_prompt, action_history, is_text, state_str, view_text=None, thought_history=None, use_thoughts=False):
        if self.use_memory:
            # if isinstance(state_str, list):
            #     if len(state_str) == 1:
            #         state_str = state_str[0]
            #     else:
            #         state_str = self.memory.hash_state(state_prompt)
            # new_state_prompt = self.f(action_history, state_prompt, state_str)
            # if new_state_prompt !z= None and new_state_prompt != 'no_description':
            #     state_prompt = new_state_prompt
            if len(action_history) <= len(self.similar_ele_path):
                current_ui_id = len(action_history) - 1
                new_state_prompt = tools.insert_onclick_into_prompt(state_prompt, self.similar_ele_path[current_ui_id], self.similar_ele_function)
                if new_state_prompt != state_prompt:  # current state contains an element of insight
                    self.state_ele_memory[state_str] = new_state_prompt
                state_prompt = new_state_prompt
            # elif state_str in self.state_ele_memory.keys():
            #     state_prompt = self.state_ele_memory[state_str]

        if use_thoughts:
            history_with_thought = []
            for idx in range(len(action_history)):
                history_with_thought.append(action_history[idx] + ' Reason: ' + thought_history[idx])
        else:
            history_with_thought = action_history

        introduction = '''You are a smartphone assistant to help users complete tasks by interacting with mobile apps.Given a task, the previous UI actions, and the content of current UI state, your job is to decide whether the task is already finished by the previous actions, and if not, decide which UI element in current UI state should be interacted.'''
        task_prompt = 'Task: ' + self.task
        history_prompt = 'Previous UI actions: \n' + '\n'.join(history_with_thought)
        full_state_prompt = 'Current UI state: \n' + state_prompt
        request_prompt = '''Your answer should always use the following format:1. Completing this task on a smartphone usually involves these steps: <?>.\n2. Analyses of the relations between the task and the previous UI actions and current UI state: <?>.\n3. Based on the previous actions, is the task already finished? <Y/N>. The next step should be <?/None>.\n4. Can the task be proceeded with the current UI state? <Y/N>. Fill in the blanks about the next one interaction: - id=<id number> - action=<tap/input> - input text=<text or N/A>'''
        prompt = introduction + '\n' + task_prompt + '\n' + history_prompt + '\n' + full_state_prompt + '\n' + request_prompt
        return prompt
    
    def _extract_input_text(self, string, start='Text: ', end=' Thought'):
        start_index = string.find(start) + len(start)   # Find the location of 'start'
        if start_index == -1:
            start_index = 0
        end_index = string.find(end)                   # Find the location of 'end'
        substring = string[start_index:end_index] if end_index != -1 else string[start_index:]
        return substring
    
    def _extract_input_textv2(self, string):
        if string[:11] == 'InputText: ':
            return string[11:]
        else:
            return string
    
    def _get_text_view_description(self, view):
        content_description = safe_dict_get(view, 'content_description', default='')
        view_text = safe_dict_get(view, 'text', default='')

        view_desc = f"<input class='&'>#</input>"#.replace('&', view_class)#.replace('#', text)
        if view_text:
            view_desc = view_desc.replace('#', view_text)
        else:
            view_desc = view_desc.replace('#', '')
        if content_description:
            view_desc = view_desc.replace('&', content_description)
        else:
            view_desc = view_desc.replace(" class='&'", "")
        return view_desc

    def _get_action_from_views_actions(self, action_history, thought_history, views=None, candidate_actions=None, state_strs=None, current_state=None):
        '''
        get action choice from LLM based on a list of views and corresponding actions
        '''
        if current_state:
            state_prompt, candidate_actions, _, _ = current_state.get_described_actions()
            state_str = current_state.state_str
            if USE_LMQL:#seems useless,somehow the same with self._make_prompt
                history, state_prompt = self._make_prompt_lmql(state_prompt, action_history, is_text=False, state_str=state_str,
                                                      thought_history=thought_history)  
            else:
                prompt = self._make_prompt(state_prompt, action_history, is_text=False, state_str=state_str, thought_history=thought_history)
        else:
            views_with_id = []
            for id in range(len(views)):
                views_with_id.append(tools.insert_id_into_view(views[id], id))
            state_prompt = '\n'.join(views_with_id)
            state_str = tools.hash_string(state_prompt)
            if USE_LMQL:
                history, state_prompt = self._make_prompt_lmql(state_prompt, action_history, is_text=False, state_str=state_str,
                                                      thought_history=thought_history)  
            else:
                prompt = self._make_prompt(state_prompt, action_history, is_text=False, state_str=state_str, thought_history=thought_history)

        # ids = [str(idx) for idx, i in enumerate(candidate_actions)]
        ids = str([i for i in range(len(candidate_actions))])
        
        if USE_LMQL:
            idx, action_type, input_text=prompt_llm_with_history(task=self.task, history=history, ui_desc=state_prompt, ids=ids)
        else:
            self.logger.info('********************************** prompt: **********************************')
            self.logger.info(prompt)
            self.logger.info('********************************** end of prompt **********************************')
            response = tools.query_gpt(prompt)
            
            self.logger.info(f'response: {response}')
            idx, action_type, input_text = tools.extract_action(response)
        # import pdb;pdb.set_trace()
        file_name = self.device.output_dir +'/'+ self.task.replace('"', '_').replace("'", '_') + '.yaml' #str(str(time.time()).replace('.', ''))
        idx = int(idx)
        if idx == -1:
            return FINISHED, None, None, None
        selected_action = candidate_actions[idx]
        
        selected_view_description = tools.get_item_properties_from_id(ui_state_desc=state_prompt, view_id=idx)
        thought = ''# tools.get_thought(response)

        if isinstance(selected_action, SetTextEvent):
            if input_text != "N/A" and input_text != None:
                selected_action.text = input_text.replace('"', '').replace(' ', '-') # by wxd. Should the second replace happen here?
                if len(selected_action.text) > 30:  # heuristically disable long text input
                    selected_action.text = ''
            else:
                selected_action.text = ''
            self._save2yaml(file_name, state_prompt, idx, state_strs, inputs=selected_action.text)
        else:
            self._save2yaml(file_name, state_prompt, idx, state_strs, inputs='null')
        return selected_action, candidate_actions, selected_view_description, thought

    def _insert_predictions_into_state_prompt(self, state_prompt, current_state_item_descriptions):
        state_prompt_list = state_prompt.split('>\n')
        item_list = []
        for view_desc in state_prompt_list:
            if view_desc[0] == ' ':
                view_desc = view_desc[1:]
            if view_desc[-1] != '>':
                view_desc = view_desc + '>'
            view_desc_without_id = tools.get_view_without_id(view_desc)
            if view_desc_without_id in current_state_item_descriptions.keys():
                prediction = 'title=' + current_state_item_descriptions[view_desc_without_id]
                view_desc_list = view_desc.split(' ', 2)
                if len(view_desc_list) > 2:  # for example, <button id=3 class='More options' checked=False></button>
                    inserted_view = view_desc_list[0] + ' ' + view_desc_list[1] + ' ' + prediction + ' ' + view_desc_list[2]
                else:  # for example, <p id=4>June</p>
                    latter_part = view_desc_list[1].split('>', 1)
                    inserted_view = view_desc_list[0] + ' ' + latter_part[0] + ' ' + prediction + '>' + latter_part[1]
                if inserted_view[-1] != '>':
                    inserted_view += '>'
                item_list.append(inserted_view)
            else:
                item_list.append(view_desc)
        return '\n'.join(item_list)

    def _get_item_prediction(self, action_history, state_prompt, state_str):
        '''
        find the most match history_state in memory_graph based on action_history. 
        match the current items in device_state with the history items in history_state, 
        return the predicted screen after touching the item
        if can not find the device_state not in action_history, return None, can decide whether to explore
        '''
        def parse_history_views(history):
            parsed_views = []
            for history_action in history:
                history_action_list = history_action.split(': ', 1)
                if 'launchApp' in history_action:
                    return []
                latter_part = history_action_list[1]
                if ' InputText:' in latter_part:
                    target_view = latter_part.split(' InputText:', 1)[0]
                elif ' Reason:' in latter_part:
                    target_view = latter_part.split(' Reason:', 1)[0]
                else:
                    target_view = latter_part
                parsed_views.append(target_view)
            return parsed_views
        
        action_history = parse_history_views(action_history[1:])  # ignore the first action, which is launching the app
        
        # search the current state str in memory based on history actions
        current_state_str = self.memory.get_first_state_str()
        next_state_str = None
        for actionid in range(0, len(action_history)):
            actioned_view = action_history[actionid]  #action_history[actionid].rsplit('.', 1)[0]
            next_state_str = self.memory.get_successor_by_node_edge(current_state_str, actioned_view)
            current_state_str = next_state_str
            # the past actions have lead to a state that does not exist in the memory
            if next_state_str == None:
                break
        if next_state_str == None:
            current_state_str = state_str
        # now, current_state_str is the current device state string, we should add all its successors' information into the items on this device state
        current_state_item_descriptions = self.memory.get_predictions_of_items(current_state_str)
        # import pdb;pdb.set_trace()
        if current_state_item_descriptions is None:
            return 'no_description'  # there is no description of the current state, either it is the leaf node or it was not explored
        # import pdb;pdb.set_trace()
        return self._insert_predictions_into_state_prompt(state_prompt, current_state_item_descriptions)

####because 'AGENTENV_PATH' is set so environment can be found
sys.path.insert(0, os.environ.get("AGENTENV_PATH"))
from environment import AndroidController

class StepTaskPolicy(UtgBasedInputPolicy):

    def __init__(self, device, app, random_input,  extracted_info, api, addiAC: AndroidController, step=0):
        super(StepTaskPolicy, self).__init__(device, app, random_input)
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{addiAC.emulator_controller.avd_name}")
        # 创建一个 FileHandler，并指定日志文件路径
        from datetime import datetime
        # 获取当前日期和时间
        current_date = datetime.now()
        # 格式化为字符串（例如：YYYY-MM-DD）
        date_string = current_date.strftime("%Y-%m-%d_%H-%M-%S")
        file_handler = logging.FileHandler(f'log/{addiAC.emulator_controller.avd_name}_{date_string}.log')

        # 设置日志格式
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        # 将 FileHandler 添加到 logger
        self.logger.addHandler(file_handler)
        
        self.__nav_target = None
        self.__nav_num_steps = -1
        self.step = step 
        self.task = "start"
        self.extracted_info = extracted_info # extracted_info[-1]中的status为-1，为额外增添的步骤，直接调用LLM用于判断该function是否已完成；其余正常步骤status=1，先使用match方法，再用LLM
        self.attempt_count = 0
        self.max_attempt_count = 3 # 每个step的重试次数
        self.__num_restarts = 0
        self.__num_steps_outside = 0
        self.__event_trace = ""
        self.__missed_states = set()
        self.__random_explore = random_input
        self.__action_history = []
        self.api = api
        self.addiAC = addiAC
        self.conversation = ""
        self.function_guide_before_looking_after = False
        self.function_guide_after_looking_after = True #
        self.update_steps_before_looking_after_in_functional_guide = False
        self.update_steps_after_looking_after_in_functional_guide = True
        self.update_steps_after_looking_after_matching = True
        self.scrollable = False
        self.scroll_first = False
    

    # 同时触发多个事件保存状态的情况处理
    #StepTaskPolicy # ??? 判断finish是否完成的逻辑有问题，目前是生成下一步动作判断是否完成，实际结合动作后的界面信息判断是否完成是否更好？
    def start(self, input_manager):
        """
        start producing events
        :param input_manager: instance of InputManager
        """
        self.action_count = 0
        # max_step = len(self.extracted_info)*3
        self.addiAC.max_steps = 20 # 与AgengEnv实验保持一致
        max_extra_step = 15 # after generated steps are finished, the extra steps to finish the task
        continuous_fail_count = 0
        
        self.device.key_press('HOME')

        while input_manager.enabled:#input_manager.event_count:
            try:
                if self.action_count == 0 and self.master is None:
                    event = KillAppEvent(app=self.app)
                    condition = "Event"
                    finish = 0
                else:
                    #StepTaskPolicy 先忽略system enter 和 layout
                    if ("system enter" in self.task.lower()) or ("layout" in self.task.lower()):
                        finish = -1                        
                    else:
                        #考虑self.last_event is None的情况？？？？？
                        s = time.time()
                        
                        finish, event = self.generate_event(input_manager)#产生事件的程序
                        condition = "Event"
                
                # vh1 = self.device.droidbot_app.get_views_tree()
                # vh2 = self.addiAC.device.get_viewhierachy()
                # snapshot_path1 = self.device.take_screenshot()  
                # snapshot_image_data2 = self.addiAC.device.get_screenshot()              
                # def read_image_from_path(image_path):
                #     # 从路径中读取图片
                #     with open(image_path, 'rb') as f:
                #         image_data = f.read()
                #     return image_data
                # def compare_images(image_data1, image_data2):
                #     # 比较两张图片的数据是否相同
                #     return image_data1 == image_data2
                # snapshot_image_data1 = read_image_from_path(snapshot_path1)
                # width1 = self.device.get_width()
                # height1 = self.device.get_height()
                # width2,height2 = self.addiAC.device.get_screen_size()
                # get_top_activity_name2 = self.addiAC.device.get_top_activity_name()
                # get_top_activity_name1 = self.device.get_top_activity_name()
                # get_installed_apps1 = self.device.adb.get_installed_apps()
                # get_installed_apps2 = self.addiAC.device.get_installed_apps()
                # ipdb.set_trace()
                # if compare_images(snapshot_image_data2, snapshot_image_data1):
                #     self.logger.info("Images are equivalent.\n")
                # else:
                #     self.logger.info("Images are not equivalent.\n")
                
                # if (vh1!=vh2):
                #     self.logger.info("vh1 != vh2\n")
                # else:
                #     self.logger.info("vh1 == vh2\n")

                # if (width1!=width2 or height1 != height2):
                #     self.logger.info("width or height != width1:{width1} width2:{width2}  height1:{height1}  height2:{height2}\n")
                # else:
                #     self.logger.info("width or height == \n")

                # if (get_top_activity_name1!=get_top_activity_name2):
                #     self.logger.info(f"get_top_activity_name1 {get_top_activity_name1} != {get_top_activity_name2}\n")
                # else:
                #     self.logger.info("get_top_activity_name1 == \n")

                # if (get_installed_apps1!=get_installed_apps2):
                #     self.logger.info(f"get_installed_apps1 {get_installed_apps1} != {get_installed_apps2}\n")
                # else:
                #     self.logger.info("get_installed_apps1 == \n")

                # get_top_activity_name = self.device.get_top_activity_name()
                
                #finish -1,0,1分别表示什么：0表示不进入下个subtask；1表示当前subtask经执行后完成；-1表示当前subtask 经generate_event判断已完成且不需要执行
                if finish != -1: # 需要执行事件
                    if not (self.action_count == 0 and event.event_type == "kill_app" ):
                        raw_views = self.addiAC.get_state() # State includes more than "view_hierarchy_json"; save view hierarchy, screenshot, top activity name in local
                        self.addiAC.device.disconnect()

                    if self.step > 0: #修正event以外的事件类型，0对应的是task-‘start’ 
                        if (self.extracted_info[self.step-1]['event_or_assertion'] != 'Event') and (finish == 1): #???这里finish==1表示什么
                            condition = "in the state" ##### ??? by wxd, how can condition be considered, add_event(...) definition may need to be modified
                            if "not in the state" in self.task:
                                condition = "not in the state"
                        if self.task.split()[0].lower() == "clear":
                            condition = "Clear" 
                    
                    input_manager.add_event(event, send_event=True) # execute, maybe set_text_enter and set_text should be divided to execute, and observe and memorize effect of every action. So Eliminate dead action
                    
                    if not (self.action_count == 0 and event.event_type == "kill_app" ):
                        self.addiAC.save_chat(self.conversation)
                        self.conversation = ""
                    if event.event_type == "key":
                        if event.name == "BACK":
                            self.addiAC.post_action(
                                "action_type: PRESS_BACK, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''"
                            )
                        elif event.name == "ENTER":
                            self.addiAC.post_action(
                                "action_type: PRESS_ENTER, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''"
                            )
                    elif event.event_type == "click":
                        tl, br = event.view["bounds"]
                        self.addiAC.tap(tl, br) # also save action in file
                    elif event.event_type == "long_click":
                        tl, br = event.view["bounds"]
                        self.addiAC.long_press(tl, br)
                    elif event.event_type == "swipe":
                        act = f"action_type: dual_point, touch_point: [{event.start_x}, {event.start_y}], lift_point: [{event.end_x}, {event.end_y}], typed_text: ''"
                        self.addiAC.post_action(act)
                    elif event.event_type == "set_text":
                        tl, br = event.view["bounds"]
                        self.addiAC.tap(tl, br)
                        # time.sleep(5)
                        raw_views = self.addiAC.get_state() # State includes more than "view_hierarchy_json"; save view hierarchy, screenshot, top activity name and agent action in local
                        self.addiAC.device.disconnect()
                        self.addiAC.text(event.text)
                        # time.sleep(5)
                    elif event.event_type == "set_text_and_enter":
                        tl, br = event.view["bounds"]
                        self.addiAC.tap(tl, br)
                        # time.sleep(5)
                        raw_views = self.addiAC.get_state() # State includes more than "view_hierarchy_json"; save view hierarchy, screenshot, top activity name and agent action in local
                        self.addiAC.device.disconnect()
                        self.addiAC.text(event.text)
                        # time.sleep(5)
                        raw_views = self.addiAC.get_state() # State includes more than "view_hierarchy_json"; save view hierarchy, screenshot, top activity name and agent action in local
                        self.addiAC.device.disconnect()
                        self.addiAC.post_action(
                                "action_type: PRESS_ENTER, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''"
                            )
                    elif event.event_type == "intent":
                        self.addiAC.intent(event.get_intent_str())
                    elif event.event_type == "kill_app":
                        kill_intent = event.get_intent_str()
                        if kill_intent is not None:
                            self.addiAC.intent(event.get_intent_str())
                        # self.addiAC._backtohome()
                    elif event.event_type in ("oracle"):
                        self.addiAC.intent(event.get_event_str(self.current_state))           
                    else:
                        raise Exception(f"Error action event type: {event.event_type}")

                        
                    
                    self.attempt_count += 1
                    continuous_fail_count = 0
                    time.sleep(8)
                if (finish != 0) or (self.attempt_count >= self.max_attempt_count): #finish != 0（即 1或-1表示正常完成或跳过）表该条task已完成，或超出最大次数；否则，finish == 0 表示function未完成，继续尝试；
                    if  self.step < len(self.extracted_info): #是否继续下一条task
                        self.step += 1
                        self.task = self.extracted_info[self.step-1]['task']
                        self.attempt_count = 0
                    elif finish == -1: #添加最后一个事件为task_complete事件
                        raw_views = self.addiAC.get_state() 
                        self.addiAC.device.disconnect()
                        self.addiAC.post_action( "action_type: STATUS_TASK_COMPLETE, touch_point: [-1.0, -1.0], lift_point: [-1.0, -1.0], typed_text: ''")
                        break
                    elif self.attempt_count >= max_extra_step or (self.addiAC.episode_done() and self.attempt_count >= 3):
                        break
                    else: #finish可能==1(当触发input事件时)或 self.max_attempt_count< self.attempt_count <= max_extra_step
                        continue
                        
                
                self.logger.info(f'StepTaskPolicy start(action_count[{self.action_count}]): finish [{finish}] / condition[{condition}] / event[{event}] / task[{self.task}] / attempt_count[{self.attempt_count}]')

            except KeyboardInterrupt:
                break
            except InputInterruptedException as e:
                self.logger.warning("stop sending events: %s" % e)
                break
            except Exception as e:
                self.logger.exception("exception during generating and sending events: %s" % e)
                import traceback
                traceback.print_exc()
                continuous_fail_count += 1
                if continuous_fail_count <= 10:
                    continue
                else:
                    break
            self.action_count += 1
        

    def generate_event_based_on_utg(self, input_manager):
        """
        generate an event based on current UTG
        @return: InputEvent
        """
        current_state = self.current_state
        self.logger.info("Current state: %s" % current_state.state_str)
        if current_state.state_str in self.__missed_states:
            self.__missed_states.remove(current_state.state_str)

        if current_state.get_app_activity_depth(self.app) < 0:
            # If the app is not in the activity stack
            start_app_intent = self.app.get_start_intent()

            # It seems the app stucks at some state, has been
            # 1) force stopped (START, STOP)
            #    just start the app again by increasing self.__num_restarts
            # 2) started at least once and cannot be started (START)
            #    pass to let viewclient deal with this case
            # 3) nothing
            #    a normal start. clear self.__num_restarts.

            if self.__event_trace.endswith(EVENT_FLAG_START_APP + EVENT_FLAG_STOP_APP) \
                    or self.__event_trace.endswith(EVENT_FLAG_START_APP):
                self.__num_restarts += 1
                self.logger.info("The app had been restarted %d times.", self.__num_restarts)
            else:
                self.__num_restarts = 0

            # pass (START) through
            if not self.__event_trace.endswith(EVENT_FLAG_START_APP):
                if self.__num_restarts > MAX_NUM_RESTARTS:
                    # If the app had been restarted too many times, enter random mode
                    msg = "The app had been restarted too many times. Entering random mode."
                    self.logger.info(msg)
                    self.__random_explore = True
                else:
                    # Start the app
                    self.__event_trace += EVENT_FLAG_START_APP
                    self.logger.info("Trying to start the app...")
                    if self.app.app_name is not None:
                        self.__action_history = [f'- start the app {self.app.app_name}']
                    else:
                        appName = (self.extracted_info[0]['app'].split("/"))[1].split(".")[0]
                        self.__action_history = [f'- start the app {appName}']
                    return 1, IntentEvent(intent=start_app_intent)

        elif current_state.get_app_activity_depth(self.app) > 0:
            # If the app is in activity stack but is not in foreground
            self.__num_steps_outside += 1

            if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE:
                # If the app has not been in foreground for too long, try to go back
                if self.__num_steps_outside > MAX_NUM_STEPS_OUTSIDE_KILL:
                    stop_app_intent = self.app.get_stop_intent()
                    go_back_event = IntentEvent(stop_app_intent)
                else:
                    go_back_event = KeyEvent(name="BACK") #????????????????? by wxd;已经在后台了再back有用吗
                self.__event_trace += EVENT_FLAG_NAVIGATE
                self.logger.info("Going back to the app...")
                self.__action_history.append('- go back')
                return 1, go_back_event
        else:
            # If the app is in foreground
            self.__num_steps_outside = 0
            
        scrollable_views = []    
        if self.scroll_first:    
            scrollable_views = current_state.get_scrollable_views()#self._get_scrollable_views(current_state)       
        if len(scrollable_views) > 0:
            '''
            if there is at least one scroller in the screen, we scroll each scroller many times until all the screens after scrolling have been recorded, you do not need to read
            '''

            actions_dict = {}
            whole_state_views, whole_state_actions, whole_state_strs = [], [], []

            # state_strs = [current_state.state_str]
            state_prompt, current_candidate_actions, current_views, _ = current_state.get_described_actions(add_enter_back=False)
            all_views_for_mark = copy.deepcopy(current_views)  # just for judging whether the screen has been scrolled up to the top

            for scrollerid in range(len(scrollable_views)):
                scroller = scrollable_views[scrollerid]
                # prefix_scroll_event = []
                actions_dict[scrollerid] = []

                prefix_scroll_event = self._scroll_to_top(scroller, all_views_for_mark)
                
                # after scrolling to the top, update the current_state
                top_state = self.device.get_current_state()
                state_prompt, top_candidate_actions, top_views, _ = top_state.get_described_actions(add_enter_back=False)
                all_views_without_id, all_actions = top_views, top_candidate_actions

                too_few_item_time = 0

                for _ in range(MAX_SCROLL_NUM):  # then scroll down to the bottom
                    whole_state_strs.append(top_state.state_str)  # record the states from the top to the bottom
                    self.device.send_event(ScrollEvent(view=scroller, direction="DOWN"))
                    scrolled_state = self.device.get_current_state()
                    state_prompt, scrolled_candidate_actions, scrolled_views, _ = scrolled_state.get_described_actions(add_enter_back=False)
                    
                    scrolled_new_views = []
                    for scrolled_view_id in range(len(scrolled_views)):
                        scrolled_view = scrolled_views[scrolled_view_id]
                        if scrolled_view not in all_views_without_id:
                            scrolled_new_views.append(scrolled_view)
                            all_views_without_id.append(scrolled_view)
                            all_actions.append(prefix_scroll_event + [ScrollEvent(view=scroller, direction="DOWN"), scrolled_candidate_actions[scrolled_view_id]])

                    if len(scrolled_new_views) == 0:
                        break
                    
                    prefix_scroll_event.append(ScrollEvent(view=scroller, direction="DOWN"))

                    if len(scrolled_new_views) < 2:
                        too_few_item_time += 1
                    if too_few_item_time >= 2:
                        break

                    self.utg.add_transition(ScrollEvent(view=scroller, direction="DOWN"), top_state, scrolled_state)
                    top_state = scrolled_state
                
                # filter out the views that have been added to the whole_state by scrolling other scrollers
                for all_view_id in range(len(all_views_without_id)):
                    view = all_views_without_id[all_view_id]
                    if view not in whole_state_views:
                        whole_state_views.append(view)
                        whole_state_actions.append(all_actions[all_view_id])
                
                    
                all_views_for_mark = []
                _ = self._scroll_to_top(scroller, all_views_for_mark, top_state)
            
            # whole_state_views.append(f"<button id={len(whole_state_views)}> press enter key: only choose when the current task only contains press enter operation</button>")
            # whole_state_views.append(f"<button id={len(whole_state_views)}>go back</button>") # len(view_descs) 在添加press enter后已经+1
            whole_state_actions.append(KeyEvent(name='ENTER'))
            whole_state_actions.append(KeyEvent(name='BACK')) 
            # self.logger.info(whole_state_views)
            finish, action, candidate_actions = self._get_action_with_LLM(
                views=whole_state_views, candidate_actions=whole_state_actions, state_strs=whole_state_strs, action_history=self.__action_history)

            if isinstance(action, list):  # the screen has to be scrolled first
                last_state = None
                for eventid in range(len(action) - 1):
                    self.device.send_event(action[eventid])
                    last_state = self.device.get_current_state()
                    # self.__action_history.append(current_state.get_action_desc(action[eventid]))
                self.__action_history.append(current_state.get_action_desc(action[-1]))

                return finish, action[-1]
            '''
            end for dealing with scrollers
            '''
        else:
            finish, action, candidate_actions = self._get_action_with_LLM(
                current_state=current_state, action_history=self.__action_history, state_strs=current_state.state_str)
     
        
        # #StepTaskPolicy status=-1表示使用LLM方法，status=1表示先使用match方法
        # if self.extracted_info[self.step-1]['status'] == -1:
        #     finish, action, candidate_actions = self._get_action_with_LLM(current_state, self.__action_history)
        # else: #先尝试match方法，再尝试LLM
        #     finish, action, candidate_actions = self._get_action_with_match(current_state, self.__action_history)
        #     if action is None:
        #         if self.task.split()[0].lower() != "identify":
        #             self.extracted_info[self.step-1]['status'] = -1
        #         finish, action, candidate_actions = self._get_action_with_LLM(current_state, self.__action_history)

        if action is not None:
            desc = current_state.get_action_desc(action)
            if desc != "":
                self.__action_history.append(desc) # - TapOn: <input>Search or type web address</input>.'''; by wxd 实际上是个SetTextEnterEvent, 生成的描述有问题
            self.logger.info(f"StepTaskPolicy action: [ {action} ] desc: [ {desc} ] task: [ {self.task}]")
            return finish, action

        if (finish != -1) and (self.__random_explore):
            self.logger.info("Trying random event.")
            action = random.choice(candidate_actions)
            self.__action_history.append(current_state.get_action_desc(action))
            return finish, action

        if (finish == -1):
            return finish, action
        
        # If couldn't find a exploration target, stop the app
        stop_app_intent = self.app.get_stop_intent()
        self.logger.info("Cannot find an exploration target. Trying to restart app...")
        self.__action_history.append('- stop the app')
        self.__event_trace += EVENT_FLAG_STOP_APP
        return finish, IntentEvent(intent=stop_app_intent)
    
    def _save2yaml(self, file_name, state_prompt, idx, state_str, inputs='null'): 
        """Save and update the execution result in file like 'change the event reminder sound of Calendar app to adara.yaml (save wxd)'"""
        if not os.path.exists(file_name):
            tmp_data = {
            'task_name': self.task,
            'step_num': 0,
            'records': []
            }
            with open(file_name, 'w', encoding='utf-8') as f:
                yaml.dump(tmp_data, f)

        with open(file_name, 'r', encoding='utf-8') as f:
            old_yaml_data = yaml.safe_load(f)
        
        new_records = old_yaml_data['records']
        new_records.append(
                {'State': state_prompt,
                'Choice': idx,
                'Input': inputs,
                'state_str': state_str}
            )
        # import pdb;pdb.set_trace()
        data = {
            'task_name': self.task,
            'step_num': len(list(old_yaml_data['records'])),
            'records': new_records
        }
        with open(file_name, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
    
    def _scroll_to_top(self, scroller, all_views_for_mark, old_state=None):
        prefix_scroll_event = []
        if old_state is None:
            old_state = self.current_state 
        for _ in range(MAX_SCROLL_NUM):  # first scroll up to the top
            self.device.send_event(ScrollEvent(view=scroller, direction="UP"))
            scrolled_state = self.device.get_current_state()
            self.utg.add_transition(ScrollEvent(view=scroller, direction="UP"), old_state, scrolled_state)
            old_state = scrolled_state
            state_prompt, scrolled_candidate_actions, scrolled_views, _ = scrolled_state.get_described_actions()
            scrolled_new_views = []  # judge whether there is a new view after scrolling
            for scrolled_view in scrolled_views:
                if scrolled_view not in all_views_for_mark:
                    scrolled_new_views.append(scrolled_view)
                    all_views_for_mark.append(scrolled_view)
            if len(scrolled_new_views) == 0:
                break

            prefix_scroll_event.append(ScrollEvent(view=scroller, direction="UP"))
        return prefix_scroll_event


    def _query_llm(self, prompt):
        client = OpenAI(api_key=os.environ["OPENAI_APIKEY"], base_url=os.environ["OPENAI_BASEURL"])
        retry = 0
        completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system", "content": "You are a test expert in testing app functions"
                    
                    },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            # "gpt-3.5-turbo" points to "gpt-3.5-turbo-0125"
            # model="gpt-4-0125-preview",
            # model="gpt-4o-2024-05-13",
            # model="gpt-4o",
            model="deepseek-chat",
            # model="gpt-3.5-turbo",
            # model="gpt-3.5-turbo-ca",
            temperature=0,
            seed=0x1110,
            timeout=60,
            stream=False
        )
        res = completion.choices[0].message.content
        return res
    
    # def _query_llm(self, prompt):
    #     # messages=[{"role": "user", "content": prompt}]
    #     response = self.query_gpt(prompt)
    #     # real_ans = response['choices'][0]['message']['content']
    #     return real_ans
          
    def convert(self, identifier):
        special_word_dict = {
            'Sign_in':'sign in',
            'sign_up':'sign up',
            'sign_in':'sign in',
            'signin':'sign in',
            'Sign_up':'sign up',
            'signup':'sign up',
            'Log_In':'log in',
            'Log_in':'log in',
            'login':'log in',
            '%':'percent',
            '#':'number',
            'et':'edit text',
            'edittext':'edit text',
            'btn':'button',
            'bt':'button',
            'tv':'text view',
            'textview':'text view',
            'fab':'',
            '&':'and'
        }
        identifier = identifier.replace("\"","").replace("ICST","icst") 
   
        for text in identifier.split(" "):
            if text in special_word_dict:
                identifier = identifier.replace(text, special_word_dict[text])
    
    
        splitted = re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1' , identifier)).split() 

   
        text_feature_without_camel_case = '' 
        for revised_text in splitted:
            if '.com' in revised_text:
                revised_text = revised_text.split(".com")[0] + ".com" 
            if 'S.' in revised_text: # for a35
                revised_text = 'Smith'
            revised_text = revised_text.lower()
            if revised_text in special_word_dict:
                revised_text = special_word_dict[revised_text]
            text_feature_without_camel_case += revised_text + " "
    
        text_feature = text_feature_without_camel_case.replace("_"," ").replace("-", " ").replace("\\b", "").replace("todo", "to do").replace("$", "").replace(".0","").replace("sample.","sample").replace("to,", "to"). replace("do.", "do").strip()
    
        for text in text_feature.split(" "):
            if text in special_word_dict:
                text_feature = text_feature.replace(text, special_word_dict[text])
    
        return text_feature

    # 判断当前action和task是否匹配,event事件采用全匹配，assertion采用子集匹配
    def if_action(self, now_action):#now_action:Event Object
        KEY_TouchEvent = "click"
        KEY_LongTouchEvent = "long_click"
        KEY_SwipeEvent = "swipe"
        KEY_ScrollEvent = "scroll"
        KEY_SetTextEvent = "set_text"
        self.logger.info(f'StepTaskPolicy if_action candidate: {now_action}, {type(now_action)}')        
        #例 Edit a view "log in password" with "research"
        flag = 1
        input = ""

        #action = Edit
        action = self.task.split()[0].lower()
        self.logger.info(f'StepTaskPolicy if_action action: {action}')
        if hasattr(now_action, 'event_type'):
            event_type = now_action.event_type
            self.logger.info(f'StepTaskPolicy if_action action:  event_type: {event_type}')

        if action == "click" or action == "swipe":
            if event_type != KEY_TouchEvent:
                return 0, input
        elif action == "edit":
            if event_type != KEY_SetTextEvent:
                return 0, input
        elif action == "long":
            if event_type != KEY_LongTouchEvent:
                return 0, input
        elif action == "identify":
            condition = self.task.split("\"")[-1]
            if "not" in condition:
                condition = False
            else:
                condition = True

        if hasattr(now_action, 'view'):
            view = now_action.view
            clickable = view['clickable']
            editable = view['editable']
            long_clickable = view['long_clickable']
            self.logger.info(f'StepTaskPolicy if_action action:  clickable: {clickable} editable:{editable} long_clickable: {long_clickable}')
        else:
            return 0, input
        
        candidate_text = ""
        candidate_id = ""
        candidate_content_desc = ""
        str_view = ""
        if view['text']:
            candidate_text = view['text']
            try:
                number = int(float(candidate_text))
                if number == float(candidate_text):
                    candidate_text = str(number)
            except ValueError:
                self.logger.info("Invalid number format")
            str_view = self.convert(candidate_text)
        if view['content_description']:
            candidate_content_desc = view['content_description']
            if (str_view != ""):
                str_view += ", "
            str_view += self.convert(candidate_content_desc)
        if view['resource_id']:
            candidate_id = view['resource_id']
            if (str_view != ""):
                str_view += ", "
            candidate_id = candidate_id.split("/")[-1]
            str_view += self.convert(candidate_id)
        if str_view == "":
            return 0, input
        
        str_view_task = self.task.split("\"")[1].lower()
        self.logger.info(f'StepTaskPolicy if_action task: {str_view_task} item: {str_view}')

        if action != "identify":
            if (str_view_task != str_view):    #???这里采用严格匹配
                return 0, input
        else:
            if (str_view_task not in str_view):  #???这里采用严格子集匹配而不是语义匹配
                return 0, input
        
        if "with" in self.task:
            input = self.task.split("with")[1].split("\"")[1]
        # elif action == "clear":
        #     input = "0"
        return flag, input
    
    # 使用迁移匹配的方法寻找对应事件    
    def _get_action_with_match(self, current_state, action_history):
        finish = 0
        selected_action = None
        action = self.task.split()[0].lower()
        condition = self.task.split("\"")[-1]
        if action == "identify":
            view_descs, candidate_actions = current_state.get_described_actions_assertion() #???需要修改
        else:
            view_descs, candidate_actions, _, _ = current_state.get_described_actions() #???需要修改，连接词语义不准确
        state_desc = '\n'.join(view_descs)

        #system enter / back
        if "system" in self.task:
            if "back" in self.task:
                self.logger.info(f'StepTaskPolicy _get_action_with_match candidate: system back')
                return 1, candidate_actions[-1], candidate_actions
            else:
                return 1, selected_action, candidate_actions
        self.logger.info(f'StepTaskPolicy _get_action_with_match candidate: {len(view_descs)}——{len(candidate_actions)}——{self.task}')
        
        for idx in range(0, len(candidate_actions)):
            desc = state_desc.split("("+str(idx)+")")[0]
            if idx > 0:
                desc = desc.split("("+str(idx-1)+")")[1]
            desc = desc.replace('\n', '')
            desc += "("+str(idx)+")"
            self.logger.info(f'StepTaskPolicy _get_action_with_match candidate: {idx}——{desc}——{self.task}')
            #if_action判断当前候选action是否匹配
            flag, text = self.if_action(candidate_actions[idx])
            if flag == 1: # ??? flag等于1就一定finish=1吗，是否需要看呈现出来的页面
                finish = 1
                self.logger.info(action)
                selected_action = candidate_actions[idx]
                if (action == "swipe"):
                    mid_x = (selected_action.view['bounds'][0][0] + selected_action.view['bounds'][1][0])/2
                    mid_y = (selected_action.view['bounds'][0][1]+ selected_action.view['bounds'][1][1])/2
                    fix_x = 1000/2
                    selected_action = SwipeEvent(start_x=mid_x, start_y=mid_y, start_view=selected_action.view, end_x=mid_x+fix_x, end_y=mid_y)
                self.logger.info(type(selected_action), selected_action)
                
                if text != "":
                    selected_action.text = text
                if action != "identify":
                    return finish, selected_action, candidate_actions
                elif "not" in condition: #not in the state
                    return 0, selected_action, candidate_actions 
                else:
                    return finish, selected_action, candidate_actions #in the state

        if (action == "identify") and ("not" in condition):
            selected_action = candidate_actions[0]
            selected_action.event_type = "oracle/" + condition
            selected_action.view['text'] = self.task
            return 1,  selected_action, candidate_actions
        
        return finish, selected_action, candidate_actions

    def remove_duplicate_lines(self, state_prompt, history_prompt):
        # 将两个文本字符串分割成行的列表
        state_lines = state_prompt.split('\n')
        new_state_lines = []
        # 遍历 state_prompt 中的每一行
        for line in state_lines:
            _line = line.split("that")[0].strip()
            if "can" in line:
                _line_action = line.split("can")[1].split("(")[0].strip()
            else:
                _line_action = ""
            if ("-" in _line):
                _line = _line.split("-")[1].strip()
                _line = _line_action + " " + _line
            # 如果这一行不在 history_prompt 中，则添加到新列表中                
            if ((_line not in history_prompt) and ("checked" not in _line)) or ("sign" in _line.lower()) or ("register" in _line.lower()):
                new_state_lines.append(line)
            else:
                self.logger.info(f'StepTaskPolicy duplicate: {_line}')
        new_state_prompt = '\n'.join(new_state_lines)
        return new_state_prompt
    
    def _get_after_task(self):
        desc = ""
        for i in range(self.step, len(self.extracted_info)-1): #最后一条task用于验证整个function是否完成，不包含len(self.extracted_info)-1
            desc += f" -subtask {i+1}: {self.extracted_info[i]['task']}\n" 
        if desc != "":
            return desc
        else:
            return "None subtask exists\n"
    
    
    def _get_unfinished_task(self): # 含当前task
        desc = ""
        for i in range(self.step-1, len(self.extracted_info)-1):
            desc += f" -subtask {i+1}: {self.extracted_info[i]['task']}\n" 
        if desc != "":
            return desc
        else:
            return "None unfinished subtask exists\n"
    
    def _get_finished_task(self):
        desc = ""
        for i in range(0, self.step-1):
            desc += f" -subtask {i+1}: {self.extracted_info[i]['task']}\n" 
        if desc != "":
            return desc
        else:
            return "None finished subtask exists\n"
    
    # def _get_task_with_after_matching(self, index):
    #     desc = ""
    #     for i in range(index, len(self.extracted_info)-1):
    #         desc += f" -subtask {i+1}: {self.extracted_info[i]['task']}\n" 
    #     return desc
    
    #添加Assertion: 对于crash的识别； 对于Identify an element的处理,是多探索几次？还是快速返回yes/no
    #back的处理，back时已执行子步骤是否要回退；广告的识别和插入处理；动态加载页面的处理;提示内容采用图像segment和识别来增强纯vh的方法（再发一篇）
    def _get_action_with_LLM(self, action_history, current_state=None, views=None, candidate_actions=None, state_strs=None):
        
        app = self.extracted_info[self.step-1]['app'].split("/")[1].split(".")[0] # 'app': 'apps/a13.apk'    ???extracted_info:dict中的example_email/example_password是做什么用的
        func = self.extracted_info[self.step-1]['function'] #function分成多条task, 最后一条task用于验证整个function是否完成
        event_or_assertion = self.extracted_info[self.step-1]['event_or_assertion']
        activity = self.device.get_top_activity_name()
        
        if current_state:
             view_descs, candidate_actions, _, _ = current_state.get_described_actions()
             state_str = current_state.state_str
        else:
            views_with_id = []
            for id in range(len(views)):
                views_with_id.append(tools.insert_id_into_view(views[id], id))
            view_descs = '\n'.join(views_with_id)
            state_str = tools.hash_string(view_descs)
             
        if "system back" in self.task: 
            return 1, candidate_actions[-1], candidate_actions
        
        history_prompt = 'Completed Actions (do not repeat these when deciding next action): \n\'\'\'\n' + ';\n '.join(action_history) + "\n'''"
        state_prompt = f'Current activity for the current state is {activity}. \nCurrent State with Available UI Views and Actions (with Action ID):\n \'\'\'\n' + (view_descs) + "\n'''"
        state_prompt = self.remove_duplicate_lines(state_prompt, history_prompt) #这里要删除什么？？？没看懂
        

        # First, determine whether the task has already been completed. ？？？这个和提示动作的prompt考虑合并？？？
        task_prompt = f"I am working on a functional test case containing multi-subtasks for the '{func}' feature in the '{app}' app. I've completed some actions and reached the current state. My current subtask is to '{self.task}'. Here is a summary of the actions I have performed:\n'''" + ';\n '.join(action_history)+".'''" #后续加app名称、当前界面显示内容（如何基于hierarchy总结相互关系）用于辅助判断是否完成；是否使用全部历史信息还是仅当前步骤的历史信息，对应关系是个难点，目前使用的是全部历史信息，self.task是否要包含当前步骤之前的所有步骤来进行综合判断; zyk没有加当前状态信息
        question = f"Based on the actions I have taken and current state reached so far, I would like to confirm whether I have successfully completed the current '{self.task}' subtask. Please provide a 'yes' or 'no' answer to indicate whether, based on performed actions and current state, I have completed '{self.task}' successfully? Please provide an answer in 'yes' or 'no'  with brief analysis for this answer. Please format the response as a JSON object with the following keys: 'answer_yes_or_no'(str, 'yes'or'no') 'analysis'(str)" 
        identify_prompt = ""
        if event_or_assertion == "Assertion" and "not" not in self.task and self.step != len(self.extracted_info):
            identify_prompt = f"If your answer is yes, please find the corresponding element related to the assertion '{self.task}'. Please think step by step in additional analysis for finding element and only return the element action's ID. Please supplement the JSON response object with the following key: 'action_id'(int). If element action can be found in the current state, choose the action id as action_id; if no proper element action can be found in the current state, set action_id as -1.\n"
        if event_or_assertion == "Assertion" and "not" in self.task and self.step != len(self.extracted_info):
            identify_prompt = f"If your answer is no, please find the element in the state contradictory to '{self.task}' . Please think step by step in analysis for finding element and only return the element action's ID. Please supplement the JSON response object with the following key: 'action_id'(int). If element action can be found in the current state, choose the action id as action_id; if no proper element action can be found in the current state, set* action_id as -1.\n"
        prompt = f'{task_prompt}\n{state_prompt}\n{question}{identify_prompt}' #zyk的版本里没有state_prompt
        self.logger.info("\n-------------------------prompt asking whether subtask has been completed----------------------------------\n")
        
        
        retries = 0
        max_retries = 10
        constraints = {
            "answer_yes_or_no":{
                "required": True,
                "type":str,
                "value_constraints": lambda value: value in ("yes", "no")
            },
            "analysis": {
                "required": True,
                "type": str
            }, 
            "action_id": {
                "required": False,
                "type": int,
                "value_constraints": lambda value: value >= -1                           
            }, 
        }
        step = None
        # if (identify_prompt != ""):           
        response, step, retries = tools.get_json_dict_response(prompt, max_retries, constraints)
        # else:
        #     self.logger.info("-----------------------\n"+prompt)
        #     response = tools.query_gpt(prompt)
        #     self.logger.info("-----------------------\n"+response)
        self.logger.info("\n-------------------------end prompt----------------------------------\n")
        self.conversation += f"-------------------------prompt asking whether subtask has been completed:-------------------------\n{prompt}\n" + f"-------------------------Response:-------------------------\n{response}\n"
        if "action_id" in step:
            action_id = step['action_id']

        if (step["answer_yes_or_no"] == "yes" and (event_or_assertion != "Assertion" or self.step == len(self.extracted_info))):
            finish = -1 #-1表示完成跳过，不需要执行操作
            self.logger.info(f"Seems the task is completed. Press Enter to continue...")
            return finish, None, candidate_actions
        elif step["answer_yes_or_no"] == "yes" and event_or_assertion == "Assertion" and self.step != len(self.extracted_info):
            if "not" not in self.task:
                if action_id != -1:
                    finish = 1
                    selected_action = candidate_actions[action_id]
                    if not isinstance(selected_action, KeyEvent):
                        selected_action = OracleEvent(
                            x=selected_action.x,
                            y=selected_action.y,
                            view=selected_action.view,
                            condition = self.task,
                            assert_accept = True
                        )
                    return finish, selected_action, candidate_actions
                elif self.attempt_count == 0: # 需要找到但是没找到且找了n次应该记录Assertion无效，这里对应n-1;目前设为找1次(Assertion是否要找3次？)
                    finish = 1
                    selected_action = OracleEvent(
                        condition = self.task,
                        assert_accept = False
                    )
                    return finish, selected_action, candidate_actions
                else: # 继续寻找直到找到或满3次
                    pass
            else: # not in the state, 不需要找
                finish = 1
                selected_action = OracleEvent(
                        condition = self.task,
                        assert_accept = True
                    )
                return finish, selected_action, candidate_actions
        elif  event_or_assertion == "Assertion" and self.step != len(self.extracted_info): #回答是no的情况
            if "not" not in self.task:# 回答是no的情况的子情况，需要找到但是没找到且找了3次应该记录Assertion无效，这里对应2 (Assertion是否要找3次？)
                if self.attempt_count == 2: 
                    finish = 1
                    selected_action = OracleEvent(
                        condition = self.task,
                        assert_accept = False
                    )
                    return finish, selected_action, candidate_actions
            else: # not in the state
                # if action_id != -1:#不需要存在但是却存在了，认为assertion失效；if action_id == -1:针对not 回答是 no，认为需要存在,但是action_id == -1对应不存在造成矛盾，认为assertion失效
                finish = 1
                selected_action = OracleEvent(
                    condition = self.task,
                    assert_accept = False
                )
                return finish, selected_action, candidate_actions

                    
                  

        # Second, if not finished, then provide the next action.
        
        if self.task.split()[0].lower() == "identify": #对于Assertion的处理
            # identify
            task_prompt = f"I have performed some actions and reached the current state in the current app. Now, I want to '{self.task}', but I couldn't find the corresponding element. Therefore, I need to perform new actions to navigate to a new page for inspection. Based on the actions I have already executed, please suggest the action ID that I might perform next. Please think step by step in analysis and return the action's ID. Please format the response as a JSON object with the following keys: 'analysis'(str), 'action_id'(int). If next action can be found in the current state, choose the action id as action_id; if no proper action can be found in the current state, set action_id as -1.\n"
            prompt = f'{task_prompt}\n{history_prompt}\n{state_prompt}'
        else:
            # event
            task_prompt = f"I am working on a functional test case containing multi-subtasks for the '{func}' feature in the '{app}' app. I've completed some actions and reached the current state. My current subtask is to '{self.task}', and I need to decide the next step that will effectively advance the testing process." #{app}需要改成真实名字，目前类似‘a13’这种，且需要添加对于app的整体介绍
            update_following_steps_str = ""
            whole_function_guide_str = ""
            if self.function_guide_before_looking_after:
                whole_function_guide_str = f"otherwise, if next action according to wholeFunction '{func}'  can be found in the current state, choose the action id as action_id and set 'subtask_or_wholeFunction_guided' as 'wholeFunction'; no matter according to subtask or wholeFunction, "
            if self.update_steps_before_looking_after_in_functional_guide and self.function_guide_before_looking_after:
                update_following_steps_str = f"Question 2:\nNow with above Completed Actions, these subtasks are seen as done: \n\'\'\'{self._get_finished_task()}\'\'\' If next action is found according to wholeFunction '{func}' in the current state, please review the following list of future subtasks and determine how they should be updated based on the current state and action_id choice. \nFuture subtasks: \n\'\'\'{self._get_unfinished_task()}\'\'\'  If next action is found according to wholeFunction, update future subtasks (including current selected action) using comprehensive step-by-step guide containing multi-substeps(i.e. subtasks). If the substep is an event, please use the 'Event' type; Please format the response (response2) as another JSON array of objects following response1 with the following keys: 'step_number'(int, starting from {self.step}), 'event_or_assertion'(str, 'Event'), 'task'(str). Note that future tasks shouldn't be updated and response2 shouldn't output if next action is found according to current subtask.\n<End Question 2>\n"
            question = f"<Question 1>:\nGiven these options, which action (identified by the Action ID in current state) should I perform next to effectively continue current subtask  '{self.task}'? Please do not suggest any actions that I have already completed. Please think step by step in analysis and only return the action's ID. Please format the response (response1) as a JSON object with the following keys: 'analysis'(str), 'action_id'(int), 'subtask_or_wholeFunction_guided'(str, choose from 'subtask' or 'wholeFunction'). If current subtask '{self.task}' only contains 'press enter operation', set action_id as -2 and 'subtask_or_wholeFunction_guided' as subtask. If next action corresponding to current subtask '{self.task}' can be found in the current state, choose the action id as action_id and set 'subtask_or_wholeFunction_guided' as subtask; {whole_function_guide_str}if no proper action can be found in the current state, set action_id as -1 and 'subtask_or_wholeFunction_guided' as 'none'.\n<End Question 1>\n{update_following_steps_str}"
            # tips = f"Here are a few tips that might help you with your action selection: Please consider that some apps may require login to access main features, but this is not always the case. If considering the login process, please ensure all necessary steps like entering email, password, and then confirming sign-in are included in the recommendation. If you are unsure which action to choose, consider scrolling down to access further features of the app." #去掉关于login的;这里没有把生成的步骤全部列出来是为了在生成的过程中保持一定的自适应性，因为最初合成的步骤不一定和当前用例完全匹配; scroll down目前的处理不奏效
            prompt = f'{task_prompt}\n{history_prompt}\n{state_prompt}\n{question}'
        self.logger.info("\n-------------------------prompt asking for next step----------------------------------\n")
        
        retries = 0
        max_retries = 10
        step = None
        step_list = None
        constraints = {
            "analysis": {
                "required": True,
                "type": str
            }, 
            "action_id": {
                "required": True,
                "type": int,
                "value_constraints": lambda value: value >= -1                           
            }, 
            "subtask_or_wholeFunction_guided": {
                "required": True,
                "type": str,
                "value_constraints": lambda value: value in ("subtask", "wholeFunction", 'none')
            }
        }
        if self.update_steps_before_looking_after_in_functional_guide:
            constraints_for_list = {
                "step_number": {
                    "type": int,
                    "value_constraints": lambda value, index: value == self.step + index
                },
                "event_or_assertion": {
                    "type": str,
                    "value_constraints": lambda value, index: value in ('Event', 'Assertion')
                },
                "task": {
                    "type": str,
                    "value_constraints": lambda value, index: True  # 无特殊约束
                }
            }
            constraints_list = [constraints, constraints_for_list]
            response, step, step_list, retries = tools.get_json_dict_then_list_response(prompt, max_retries, constraints_list)
            if step_list is not None and step_list != []:
                self.extracted_info = tools.update_reference_steps(self.extracted_info, step_list, self.step)
        else:
            response, step, retries = tools.get_json_dict_response(prompt, max_retries, constraints)
        self.logger.info("\n-------------------------end prompt----------------------------------\n")
        self.conversation += f"-------------------------prompt asking for next step:-------------------------\n{prompt}\n" + f"-------------------------Response:-------------------------\n{response}\n"
        if retries == max_retries:
            self.logger.info("Error: Unable to extract next action after maximum retries. Return no action")
            self.conversation += "Error: Unable to extract next action after maximum retries. Return no action\n"
            match = -1
        else:
            match = step['action_id']
            
            
 
        finish = 0
        # 判断是否已经执行到后面的task了，这个要列出全部吗？列出前n个？  假如执行到后面了,这个时候要重新调整测试接下来步骤的整体描述！;没有到后面的话，应该让从整体任务看是否要选择某个组件；还是没找到合适组件的话，再选择back或scroll(实现一个scrollable的判别器)而不是默认back（加上动作生效的diff判断反馈给模型），其他时候是否要怎样重新调整测试接下来步骤的整体描述！
        if match == -1 and self.step <= len(self.extracted_info)-1:
            scroll_str = ""
            if self.scrollable:
                scroll_str = " or -3 (corresponding to scroll up)"
            update_following_steps_str = ""
            if self.function_guide_after_looking_after and self.update_steps_after_looking_after_in_functional_guide:
                update_following_steps_str = f"If Condition 3 happens, now with above Completed Actions, these subtasks are seen as done: \n{self._get_finished_task()} If next action is found according to wholeFunction '{func}' in the current state, please review the following list of future subtasks and determine how they should be updated based on the current state and action_id choice. \nFuture subtasks: \n{self._get_unfinished_task()} If next action is found according to wholeFunction and future subtasks should be updated, update future subtasks (including current selected action) using comprehensive step-by-step guide containing multi-substeps(i.e. subtasks). If the substep is an event, please use the 'Event' type; Please format the response (response2) as another JSON array of objects following response1 with the following keys: 'step_number'(int, starting from {self.step}), 'event_or_assertion'(str, 'Event'), 'task'(str). Note that future tasks shouldn't be updated and response2 shouldn't output if next action is chosen as action_id of -1 or -3."
            if self.update_steps_after_looking_after_matching:
                update_following_steps_str_after_matching= f"If Condition 1 happens, now with above Completed Actions, these subtasks are seen as done: \n{self._get_finished_task()} -the subtask you choose with subtask_id is also seen as done. \nPlease review the list of future subtasks after the subtask you choose with subtask_id, and determine how they should be updated based on the current state. If next action is found according to wholeFunction and future subtasks should be updated, update future subtasks using comprehensive step-by-step guide containing multi-substeps(i.e. subtasks). If the substep is an event, please use the 'Event' type; Please format the response (response2) as another JSON array of objects following response1 with the following keys: 'step_number'(int, starting from {self.step}), 'event_or_assertion'(str, 'Event'), 'task'(str). Note that future tasks shouldn't be updated and response2 shouldn't output if next action is chosen as action_id of -1 or -3."

            whole_function_guide_str = ""
            if self.function_guide_after_looking_after:
                whole_function_guide_str = f"In condition 2, decide which action (identified by the Action ID) in current state should I perform next to effectively continue wholeFunction '{func}'? Please do not suggest any actions that I have already completed. Please think step by step in analysis and only return the action's ID. If next action according to wholeFunction '{func}'  can be found in the current state (Contidition 3), choose the action id as action_id."
            task_background_prompt = f"I am working on a functional test case containing multi-subtasks for the '{func}' feature in the '{app}' app. I've completed some actions and reached the current state.\n"
            question = f"<Question 1>\nPlease review the following list of future subtasks and determine whether any has already been completed. Future subtasks (not include current subtask):\n\'\'\'\n{self._get_after_task()}\'\'\'\nPlease format the response (response1) as a JSON object with the following keys: 'analysis'(str), 'subtask_id'(int). If any subtasks have been completed (Condition 1), please put the ID of the last subtask that was completed into subtask_id; if none has been completed (Condition 2), put -1 into subtask_id. {whole_function_guide_str} In Condition 2, add action_id into JSON response (response1) with key: 'action_id'(int) and when no action_id can be chosen, choose action_id of -1 (corresponding to go back){scroll_str} to continue testing whole function. In Condition 1, don't include action_id in response1.\n{update_following_steps_str_after_matching}\n{update_following_steps_str}"
            prompt = f'{history_prompt}\n{state_prompt}\n{task_background_prompt}{question}' #zyk的版本里没有state_prompt
            self.logger.info("\n-------------------------prompt asking whether any future subtask has been done ----------------------------------\n")

            retries = 0
            max_retries = 10
            step = None
            step_list = None
            constraints = {
                "analysis": {
                    "required": True,
                    "type": str
                }, 
                "action_id": {
                    "required": True,
                    "type": int,
                    "value_constraints": lambda value: value >= -3                         
                }, 
                "subtask_id": {
                    "required": True,
                    "type": int,
                    "value_constraints": lambda value: value >= -1                           
                }, 
            }
            if self.update_steps_after_looking_after_in_functional_guide or self.update_steps_after_looking_after_matching:
                constraints_for_list = {
                    "step_number": {
                        "type": int,
                        "value_constraints": lambda value, index: value == self.step + index
                    },
                    "event_or_assertion": {
                        "type": str,
                        "value_constraints": lambda value, index: value in ('Event', 'Assertion')
                    },
                    "task": {
                        "type": str,
                        "value_constraints": lambda value, index: True  # 无特殊约束
                    }
                }
                constraints_list = [constraints, constraints_for_list]
                response, step, step_list, retries = tools.get_json_dict_then_list_response(prompt, max_retries, constraints_list)
                if step_list != []:
                    self.extracted_info = tools.update_reference_steps(self.extracted_info, step_list, self.step)
            else:

                response, step, retries = tools.get_json_dict_response(prompt, max_retries, constraints)
            self.logger.info("\n-------------------------end prompt----------------------------------\n")
            self.conversation += f"-------------------------prompt asking whether any future subtask has been done:-------------------------\n{prompt}\n" + f"-------------------------Response:-------------------------\n{response}\n"
            if retries == max_retries:
                self.logger.info("Error: Unable to extract next action after maximum retries. Return no action")
                self.conversation += "Error: Unable to extract next action after maximum retries. Return no action\n"
                match = -1
            # match = step['action_id']

            
            if match == -1: #???这里self.step要不要回退呢，目前没有回退；有可能是self.step-1 步造成的错误呢！！！回退机制的设计!!!
                selected_action = candidate_actions[-1] # back, -1 denotes the end one
                return finish, selected_action, candidate_actions
            elif step['subtask_id'] == -1:
                if step['action_id'] != -2: # -3,-1或>=0; -3表示scroll down
                    selected_action = candidate_actions[step['action_id']] # back, -1 denotes the end one
                else: #-2表示发生意外情况，选择back
                    selected_action = candidate_actions[-1]
                return finish, selected_action, candidate_actions
            else: #找到了匹配的子步骤
                finish = -1 # 这里，也看到了当前显示界面，所以没必要再确认一次； self.step = idx已经设定了，后面finish=-1会再向前多挪一个 (这样直接跳转到已完成subtask的下一个subtask)
                idx = step['subtask_id']
                self.step = idx
                return finish, None, candidate_actions

        
        idx = match
        self.logger.info(f"StepTaskPolicy _get_action_with_LLM return action id: {idx}")

        selected_action = candidate_actions[idx]
        next_step_ask = "" # if no next step in extracted_info exisits, next_step_ask will be empty string and nothing will insert into question
        if self.step <= len(self.extracted_info)-1:
            next_step = self.extracted_info[self.step]['task']
            next_step_ask = f'If "{next_step}" contains "press enter" action explicitly, set "press_enter" as "true" and set "goto_next_step" as "true". '
        # 提取action的text
        if (isinstance(selected_action, SetTextEvent)) and (self.task.split()[0].lower() != "clear"):
            view_text = current_state.get_view_desc(selected_action.view) #get_view_desc需要修改
            question = f'I have chosen the action of "{view_text}". So I need to type something into the edit box. Just put the text that need enter into "text_need_enter". {next_step_ask} If "{self.task}" contains "press enter" action explicitly , set "press_enter" as "true". In other conditions, set "press_enter" and "goto_next_step"  as default value "False". Answer using json object format including following keys: "text_need_enter"(str), "press_enter"(true or false) and "goto_next_step"(true or false).'
            #prompt = f'{task_prompt}\n{state_prompt}\n{question}'
            prompt = f'{task_prompt}\n{history_prompt}\n{state_prompt}\n{question}' # zyk版本里没有state_prompt
            if ("email" in view_text.lower()) and (self.extracted_info[0]['example_email'] != ""):
                response = "\"" + self.extracted_info[0]['example_email'] + "\""
            elif ("password" in view_text.lower()) and (self.extracted_info[0]['example_password'] != ""):
                response = "\"" + self.extracted_info[0]['example_password'] + "\""
            elif "with" in self.task:
                response =  self.task.split("with")[1]
            else:
                self.logger.info("\n-------------------------prompt asking for text input in  SetTextEvent----------------------------------\n")
                
                retries = 0
                max_retries = 10
                constraints = {
                    "text_need_enter": {
                        "required": True,
                        "type": str
                    }, 
                    "press_enter": {
                        "required": True,
                        "type": bool,
                        "value_constraints": lambda value: value in (True, False)                           
                    }, 
                    "goto_next_step": {
                        "required": True,
                        "type": bool,
                        "value_constraints": lambda value: value in (True, False)  
                    }
                }
                step = None
                response, step, retries = tools.get_json_dict_response(prompt, max_retries, constraints)
                self.conversation += f"-------------------------prompt asking for text input in  SetTextEvent:-------------------------\n{prompt}\n" + f"-------------------------Response:-------------------------\n{response}\n"
                if retries == max_retries:
                    self.logger.info("Error: Unable to extract text_need_enter after maximum retries.")
                    self.conversation += "Error: Unable to extract text_need_enter after maximum retries. Return no action\n"
                    return 0, None, candidate_actions
                self.logger.info("\n-------------------------end prompt----------------------------------\n")
                selected_action.text = step["text_need_enter"]
                if step["press_enter"] : # press_enter=True的话认为当前子task会完成； 假如这个假设不正确，那么应该在函数开头判断是完成的时候再向后self.step += 1（可能需要修改）
                    finish = 1
                    if step["goto_next_step"]:
                        self.step += 1
                    # 使用 SetTextEvent 的属性快速生成 SetTextEnterEvent
                    selected_action = SetTextEnterEvent(
                        x=selected_action.x,
                        y=selected_action.y,
                        view=selected_action.view,
                        text=selected_action.text
                    )
                elif step["goto_next_step"]:
                    self.conversation += "Error: In SetTextEvent, goto_next_step is true but press_enter is false. Please check the response. Return no action\n"
                    self.logger.info("Error: In SetTextEvent, goto_next_step is true but press_enter is false. Please check the response. Return no action\n")
                    return 0, None, candidate_actions
        self.logger.info(f"StepTaskPolicy _get_action_with_LLM finish: {finish}; selected_action: {selected_action}\n")
        
        file_name = self.device.output_dir +'/'+ self.task.replace('"', '_').replace("'", '_') + '.yaml' 
        if isinstance(selected_action, SetTextEvent):
            self._save2yaml(file_name, state_prompt, idx, state_strs, inputs=selected_action.text)
        else:
            self._save2yaml(file_name, state_prompt, idx, state_strs, inputs='null')
        return finish, selected_action, candidate_actions
        # except:
        #     import traceback
        #     traceback.print_exc()
        #     return None, candidate_actions

