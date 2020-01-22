"""Python 3-based multithreaded Windows Event monitoring program."""

import time
import json
import threading
import sys
from datetime import datetime, timedelta
from collections import defaultdict 

import win32evtlog


class Event_Monitor:
    """
    Class is an application that monitors Windows Event Logs specified by
    parameter config_file (string).
    """
    def __init__(self, config_file):
        try:
            with open(config_file, "r") as config:
                data = json.loads(config.read())
        except:
            print("Config file not found in directory.\nExiting program.", )

        self._threads = []
        for server in data["Servers"]:
            for log_type in data["Servers"][server]:
                event_IDs = data["Servers"][server][log_type]
                thread = Monitor_Thread(server, log_type, event_IDs)
                self._threads.append(thread)
 
    def run(self):
        for thread in self._threads: thread.start()
        try: # Runs concurrently with threads
            while True:
                has_dead_thread = False
                for thread in self._threads: # Check for thread failure
                    if not thread.is_alive(): # Cleanup
                        has_dead_thread = True
                        print(f"{thread.name} thread failed.")
                        thread.export_json()
                        # self._threads = [thread for thread in self._threads if thread.is_alive()]
                if has_dead_thread: 
                    self._threads = [thread for thread in self._threads if thread.is_alive()]
                time.sleep(1)
        except KeyboardInterrupt: 
            print("\nKeyboard interrupt.")
        except Exception as err:
            print(err)
        finally: # Save necessary data before exit
            for thread in self._threads:
                thread.export_json()
            print("Exiting program.")
            sys.exit(0)


class Monitor_Thread(threading.Thread):
    """
    Subclass of Thread that processes and holds data from Windows Event Logs.
    """
    def __init__(self, server, log_type, event_IDs):
        threading.Thread.__init__(self, args= [server, log_type, event_IDs])
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

        with open("config.json", "r") as config:
            config_data_dict = json.loads(config.read())
            event_descriptions = config_data_dict["Event Descriptions"][self._log_type]
            self._event_descriptions = { # Dictionary comprehension
                int(event): event_descriptions[event] # Event IDs in json are strings
                    for event in event_descriptions
                        if int(event) in self._event_IDs
            } 
    
    def run(self):
        """Overwritten method that sets target for Monitor_Thread."""
        self.monitor_events(self._server_name, self._log_type, self._event_IDs)
    
    def event_fits_criteria(self, event, event_IDs, start_time):
        """Returns boolean."""
        return event.EventID in event_IDs and event.TimeGenerated > start_time  

    def monitor_events(self, server, log_type, event_IDs):
        """
        Monitors local or remote machine's specified logs for specified Windows 
        Events. This configuration is specified by the json file provided via
        the config_file parameter when initializing the Event_Monitor class.
        """
        try:
            handle = win32evtlog.OpenEventLog(server, log_type)
            # total = win32evtlog.GetNumberOfEventLogRecords(handle)
        except:
            return
        
        print(f"Thread that monitors {log_type} logs on {server} started successfully.")
        flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        start = datetime.now()
        delta = timedelta(hours = 6) # Sets how often thread data is exported
        
        while True:
            try:
                events = win32evtlog.ReadEventLog(handle, flags, 0)  
            except: 
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
            print(f"Exported {self._log_type} logs for {self._server_name}.")
        except PermissionError as err:
            print(err) 