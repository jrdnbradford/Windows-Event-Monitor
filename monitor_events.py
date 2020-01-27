"""Python 3-based multithreaded Windows Event Log monitoring program."""

import time
import json
import threading
import sys
from datetime import datetime, timedelta
from collections import defaultdict 

import win32evtlog


class Event_Monitor:
    """
    Class is an application that monitors Windows Event Logs.

    Parameter config_file (string): File containing necessary data

    Parameter retry_delta (datetime.timedelta): Kwarg that sets how
    often the program should attempt to respawn threads. Defaults to
    5 minutes.
    """
    def __init__(self, config_file, retry_delta = timedelta(minutes = 5)):
        try:
            with open(config_file, "r") as config:
                data = json.loads(config.read())
        except:
            print("Config file not found.\nExiting program.", )

        self._active_threads = []
        for server in data["Servers"]:
            for log_type in data["Servers"][server]:
                event_IDs = data["Servers"][server][log_type]
                thread = Monitor_Thread(server, log_type, event_IDs)
                self._active_threads.append(thread)
        self._threads_to_restart = []
        self._retry_delta = retry_delta
 
    def run(self):
        """
        Main thread of execution. run() ensures that spawned Monitor_Threads
        stay alive. If any are found dead, it attempts to start a new thread 
        with the dead Monitor_Thread's data in case the problem is temporary.

        Stoppable with Ctrl+C.
        """
        for t in self._active_threads: t.start()
        try: # Runs concurrently with threads
            while True:
                for t in self._active_threads:
                    if not t.is_alive():
                        self._threads_to_restart.append(t.respawn_thread(self._retry_delta))                  
                        t.failures += 1
                        t.acknowledged_failure = True
                # Don't remove threads that died AFTER iteration
                self._active_threads = [t for t in self._active_threads if not t.acknowledged_failure]
                
                for t in self._threads_to_restart: 
                    if not t._failure_printed_to_console:
                        print(f"{t.name} failed. Will attempt restart in {self._retry_delta}.")
                        t._failure_printed_to_console = True
                    
                    if t.restart_time < datetime.now():
                        print(f"Attempting to restart {t.name}.")
                        t._failure_printed_to_console = False
                        t.restart_time = None
                        t.start()
                        self._active_threads.append(t)
                # Remove threads that have respawned
                self._threads_to_restart = [t for t in self._threads_to_restart if t.restart_time != None]
                time.sleep(1)

        except KeyboardInterrupt: 
            print("\nKeyboard interrupt.")
        except Exception as err:
            print(err)
        finally: # Save necessary data before exit
            for t in self._active_threads:
                t.export_json()
            for t in self._threads_to_restart:
                t.export_json()
            print("Exiting program.")
            sys.exit(0)


class Monitor_Thread(threading.Thread):
    """
    Subclass of Thread that processes and holds data from Windows Event Logs.
    """
    def __init__(self, server, log_type, event_IDs):
        threading.Thread.__init__(self, target = self.monitor_events, args = [server, log_type, event_IDs])
        now = datetime.now()
        self._start_timestamp = now.timestamp()
        self._start_date = now.date()
        self._server_name = server
        self._log_type = log_type
        self._event_IDs = event_IDs
        self._event_occurrence = defaultdict(int)
        self._times_event_generated = defaultdict(list)
        self._total_processed_events = 0
        self.daemon = True
        self.name = f"{self._log_type}_{self._server_name}"
        self._failure_printed_to_console = False
        self.failures = 0
        self.restart_time = None
        self.acknowledged_failure = False

        with open("config.json", "r") as config:
            config_data_dict = json.loads(config.read())
            event_descriptions = config_data_dict["Event Descriptions"][self._log_type]
            self._event_descriptions = { # Dictionary comprehension
                int(event): event_descriptions[event] # Event IDs in json are strings
                    for event in event_descriptions
                        if int(event) in self._event_IDs
            } 
    
    def event_fits_criteria(self, event, event_IDs, start_time):
        return event.EventID in event_IDs and event.TimeGenerated > start_time  

    def respawn_thread(self, delta):
        """
        Copies relevant data from dead thread and adds it to a new one.

        Parameter delta (datetime.timedelta): timedelta that sets how long
        from now to respawn the thread.
        
        Returns thread.
        """        
        server = self._server_name
        log_type = self._log_type
        event_IDs = self._event_IDs
        new_thread = Monitor_Thread(server, log_type, event_IDs)

        new_thread._start_timestamp = self._start_timestamp
        new_thread._start_date = self._start_date
        new_thread._event_occurrence = self._event_occurrence
        new_thread._times_event_generated = self._times_event_generated
        new_thread._total_processed_events = self._total_processed_events
        new_thread.failures = self.failures
        new_thread.restart_time = datetime.now() + delta
        return new_thread

    def monitor_events(self, server, log_type, event_IDs):
        """
        Monitors local or remote machine's logs for Windows Events. 
        This configuration is specified by the json file provided via
        the config_file parameter when initializing the Event_Monitor
        class.
        """
        try:
            handle = win32evtlog.OpenEventLog(server, log_type)
            # total = win32evtlog.GetNumberOfEventLogRecords(handle)
        except Exception as err:
            print(err)
            self.failures += 1
            return
        
        print(f"Thread that monitors {log_type} logs on {server} started successfully.")
        flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        start = datetime.now()
        # Perhaps this should be initialized in Event_Monitor
        delta = timedelta(hours = 6) # Sets how often thread data is exported
        
        while True:
            try:
                events = win32evtlog.ReadEventLog(handle, flags, 0)  
            except Exception as err:
                print(err)
                self.failures += 1
                return
            
            events_to_process = [event for event in events if self.event_fits_criteria(event, event_IDs, start)]
            for event in events_to_process:                                            
                self.add_event_details(event)  
                print("---------")
                print(f"Event ID: {event.EventID}")
                print(f"Server: {server}")
                print(f"Description: {self.get_event_description(event.EventID)}")
                print(f"Time: {event.TimeGenerated}") 
                print("---------")

            # Export after time specified by delta
            if datetime.now() >= start + delta:
                self.export_json()   
                start = datetime.now()   

    def add_event_details(self, event_obj):
        """
        Increments event's occurrence and total processed 
        events, adds log generation timestamp to list.
        """
        self._event_occurrence[event_obj.EventID] += 1
        self._times_event_generated[event_obj.EventID].append(event_obj.TimeGenerated.timestamp())
        self._total_processed_events += 1
        
    def get_num_of_event_occurrence(self, event_ID):
        return self._event_occurrence[event_ID]

    def get_event_times_of_occurrence(self, event_ID):
        return self._times_event_generated[event_ID]

    def get_total_processed_events(self):
        return self._total_processed_events

    def get_event_description(self, event_ID):
        return self._event_descriptions.get(event_ID)

    def get_server_name(self):
        return self._server_name

    def get_log_type(self):
        return self._log_type
    
    def get_thread_name(self):
        return self.name 

    def reset_all_event_occurrences(self):
        self._event_occurrence = defaultdict(int)    

    def reset_all_event_times_of_occurrence(self):
        self._times_event_generated = defaultdict(list)

    def reset_all_processed_events(self):
        self._total_processed_events = 0  

    def export_json(self):
        """Writes data from instance of this class to json file."""
        end_timestamp = datetime.now().timestamp()
        event_log_json_file = f"{self._server_name}_{self._log_type}_{end_timestamp}_logs.json"

        data_dict = { # Dictionary to be exported to json
            self._server_name: {
                "Start Timestamp": self._start_timestamp,
                "End Timestamp": end_timestamp,
                "Total Processed Events": self._total_processed_events,
                "Log Type": self._log_type,
                "Event IDs": { # Value built below
                    # 1111: {
                    #   "Total": int,
                    #   "Description": str or None,
                    #   "Timestamps": [floats or empty]
                    # }
                }               
            }
        }
        
        event_ID_key = data_dict[self._server_name]["Event IDs"]
        try: # Build Event IDs dictionary value for data_dict
            for event_ID in self._event_IDs:
                event_ID_key[event_ID] = {
                    "Total": self._event_occurrence[event_ID], 
                    "Description": self._event_descriptions.get(event_ID), # May not exist
                    "Timestamps": self._times_event_generated[event_ID]
                }
        except KeyError as err:
            print(err)
                
        try: # Write to json
            with open(event_log_json_file, "w") as f:
                data = json.dumps(data_dict, indent = 4)
                f.write(data)
            print(f"Exported {self._server_name} {self._log_type} logs.")
        except PermissionError as err:
            print(err) 