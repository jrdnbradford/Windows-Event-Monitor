import time
import json
import threading
import sys
from datetime import datetime, timedelta
from collections import defaultdict 

import win32evtlog


class Events_Object:
    def __init__(self, server, log_type, event_IDs):
        now = datetime.now()
        self.__start_timestamp = now.timestamp()
        self.__start_date = now.date()
        self.__thread_name = threading.current_thread().getName()
        self.__server_name = server
        self.__log_type = log_type
        self.__event_IDs = event_IDs
        self.__event_occurrence = defaultdict(int)
        self.__times_event_generated = defaultdict(list)
        self.__total_processed_events = 0

        with open("config.json", "r") as config:
            config_data_dict = json.loads(config.read())
            event_descriptions = config_data_dict["Event Descriptions"][self.__log_type]
            self.__event_descriptions = { # Dictionary comprehension
                int(event): event_descriptions[event] # Event IDs in json are strings
                    for event in event_descriptions
                        if int(event) in self.__event_IDs
            } 
        

    def __str__(self):
        comma_events = [str(event_ID) for event_ID in self.__event_IDs][0:-1]
        logs_str = ", ".join(comma_events) + ", and " + str(self.__event_IDs[-1])
        return f"Events_Object instance searching {self.__log_type} logs for {logs_str} on {self.__server_name}."
   
    def add_event_details(self, event_obj):
        """
        Increments event's occurrence and total processed 
        events, adds log generation timestamp to list.
        """
        self.__event_occurrence[event_obj.EventID] += 1
        self.__times_event_generated[event_obj.EventID].append(event_obj.TimeGenerated.timestamp())
        self.__total_processed_events += 1
        
    def get_num_of_event_occurrence(self, event_ID):
        return self.__event_occurrence[event_ID]

    def get_event_times_of_occurrence(self, event_ID):
        return self.__times_event_generated[event_ID]

    def get_total_processed_events(self):
        return self.__total_processed_events

    def get_event_description(self, event_ID):
        return self.__event_descriptions.get(event_ID)

    def get_server_name(self):
        return self.__server_name

    def get_log_type(self):
        return self.__log_type
    
    def get_thread_name(self):
        return self.__thread_name 

    def export_json(self):
        """Writes data from instance of this class to json file."""
        end_timestamp = datetime.now().timestamp()
        event_log_json_file = f"{self.__server_name}_{self.__log_type}_{end_timestamp}_logs.json"

        data_dict = { # Dictionary to be exported to json
            self.__server_name : {
                "Start Timestamp": self.__start_timestamp,
                "End Timestamp": end_timestamp,
                "Total Processed Events": self.__total_processed_events,
                "Log Type": self.__log_type,
                "Event IDs": { # Value built below
                    # 1111: {
                    #   "Total": int,
                    #   "Description": str or None,
                    #   "Timestamps": [floats or empty]
                    # }
                }               
            }
        }
        
        event_ID_key = data_dict[self.__server_name]["Event IDs"]
        try: # Build Event IDs dictionary value for data_dict
            for event_ID in self.__event_IDs:
                event_ID_key[event_ID] = {
                    "Total": self.__event_occurrence[event_ID], 
                    "Description": self.__event_descriptions.get(event_ID), # May not exist
                    "Timestamps": self.__times_event_generated[event_ID]
                }
        except KeyError as err:
            print(err)
                
        try: # Write to json
            with open(event_log_json_file, "w") as f:
                data = json.dumps(data_dict, indent = 4)
                f.write(data)
            print(f"Exported {self.__log_type} logs for {self.__server_name}.")
        except PermissionError as err:
            print(err)
                        
    def reset_all_event_occurrences(self):
        self.__event_occurrence = defaultdict(int)    

    def reset_all_event_times_of_occurrence(self):
        self.__times_event_generated = defaultdict(list)

    def reset_all_processed_events(self):
        self.__total_processed_events = 0


def main():
    try:
        with open("config.json", "r") as config:
            data = json.loads(config.read())
    except:
        print("config.json file not found in directory.\nExiting program.", )
        return

    global log_instances 
    log_instances = []

    threads = [] # Multithreading
    for server in data["Servers"]:
        for log_type in data["Servers"][server]:
            event_IDs = data["Servers"][server][log_type]
            thread = threading.Thread(target = monitor_events, args = [server, log_type, event_IDs])
            thread.daemon = True
            thread.name = f"{log_type}_{server}"
            threads.append(thread)
            thread.start()

    data = None

    try: # Runs concurrently with threads
        while True:
            has_dead_thread = False
            for thread in threads: # Check for thread failure
                if not thread.is_alive(): # Cleanup
                    has_dead_thread = True
                    print(f"{thread.name} thread failed.")
                    for log_instance in log_instances:
                        if log_instance.get_thread_name() == thread.name:
                            log_instance.export_json()
                    log_instances = [log_instance for log_instance in log_instances if log_instance.get_thread_name() != thread.name]
            if has_dead_thread: threads = [thread for thread in threads if thread.is_alive()]
            time.sleep(1)
    except KeyboardInterrupt: 
        print("\nKeyboard interrupt.")
    except Exception as err:
        print(err)
    finally: # Save necessary data before exit
        for log_instance in log_instances:
            log_instance.export_json()
        print("Exiting program.")
        sys.exit(0)


def monitor_events(server, log_type, event_IDs):
    """
    Monitors local or remote machine's specified logs for specified Windows 
    Events. This configuration is specified by the accompanying json file.
    """
    try:
        handle = win32evtlog.OpenEventLog(server, log_type)
        # total = win32evtlog.GetNumberOfEventLogRecords(handle)
    except:
        return
    
    print(f"Thread that monitors {log_type} logs on {server} started successfully.")
    flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    log_instance = Events_Object(server, log_type, event_IDs)
    log_instances.append(log_instance) # Global
    start = datetime.now()
    delta = timedelta(hours = 6)
    
    while True:
        try:
            events = win32evtlog.ReadEventLog(handle, flags, 0)  
        except: 
            return
          
        events_to_process = [event for event in events if event_fits_criteria(event, event_IDs, start)]
        for event in events_to_process:                                            
            log_instance.add_event_details(event)  
            print(f"""
# Event ID: {event.EventID} 
# Server: {server}
# Description: {log_instance.get_event_description(event.EventID)}
# Time: {event.TimeGenerated}
""")                      

        # Export after time specified by delta
        if datetime.now() >= start + delta:
            log_instance.export_json()   
            start = datetime.now()   
            
        
def event_fits_criteria(event, event_IDs, start_time):
    """Returns boolean."""
    return event.EventID in event_IDs and event.TimeGenerated > start_time     


if __name__ == "__main__": main()