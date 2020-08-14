import json
import threading
from datetime import datetime
from collections import defaultdict

import win32evtlog



class Monitor_Thread(threading.Thread):
    """
    Subclass of Thread that processes and holds data from Windows Event Logs.

    Parameter server (string): Specifies hostname.

    Parameter log_type (string): Specifies log to check for events. Possible values
    include "System", "Security", etc.

    Parameter event_IDs (list): Specifies event IDs to monitor in log_type, as integers.
    """
    def __init__(self, server, log_type, event_IDs):
        super().__init__(target = self.monitor_events, args = [server, log_type, event_IDs])
        now = datetime.now()
        self.initial_start_timestamp = now.timestamp()
        self.latest_start = now
        self.start_date = now.date()
        self.server_name = server
        self.log_type = log_type
        self.event_IDs = event_IDs
        self.event_occurrence = defaultdict(int)
        self.times_event_generated = defaultdict(list)
        self.total_processed_events = 0
        self.daemon = True
        self.name = f"{self.log_type}_{self.server_name}"
        self.failure_printed_to_console = False
        self.failures = 0
        self.restart_time = None
        self.acknowledged_failure = False

        with open("config.json", "r") as config:
            config_data_dict = json.loads(config.read())
            event_descriptions = config_data_dict["Event Descriptions"][self.log_type]
            self.event_descriptions = { # Dictionary comprehension
                int(event): event_descriptions[event] # Event IDs in json are strings
                    for event in event_descriptions
                        if int(event) in self.get_event_IDs()
            }


    def event_fits_criteria(self, event):
        return event.EventID in self.get_event_IDs() and event.TimeGenerated > self.latest_start


    def respawn_thread(self, delta):
        """
        Copies relevant data from dead thread and adds it to a new one.

        Parameter delta (datetime.timedelta): timedelta that sets how long
        from now to respawn the thread.

        Returns thread.
        """
        new_thread = Monitor_Thread(self.server_name, self.log_type, self.event_IDs)

        now = datetime.now()
        new_thread.latest_start = now
        new_thread.initial_start_timestamp = self.initial_start_timestamp
        new_thread.start_date = self.start_date
        new_thread.event_occurrence = self.event_occurrence
        new_thread.times_event_generated = self.times_event_generated
        new_thread.total_processed_events = self.total_processed_events
        new_thread.failures = self.failures
        new_thread.restart_time = now + delta
        self = None

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
            self.add_thread_failure()
            return

        print(f"Thread that monitors {log_type} logs on {server} started successfully.")
        flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        while True:
            try:
                events = win32evtlog.ReadEventLog(handle, flags, 0)
            except Exception as err:
                print(err)
                self.add_thread_failure()
                return

            events_to_process = [event for event in events if self.event_fits_criteria(event)]
            for event in events_to_process:
                self.add_event_details(event)
                print("---------")
                print(f"Event ID: {event.EventID}")
                print(f"Server: {server}")
                print(f"Description: {self.get_event_description(event.EventID)}")
                print(f"Time: {event.TimeGenerated}")
                print("---------")


    def add_event_details(self, event_obj):
        """
        Increments event's occurrence and total processed
        events, adds log generation timestamp to list.
        """
        self.event_occurrence[event_obj.EventID] += 1
        self.times_event_generated[event_obj.EventID].append(event_obj.TimeGenerated.timestamp())
        self.total_processed_events += 1


    def add_thread_failure(self):
        self.failures += 1


    def get_failure_total(self):
        return self.failures


    def get_event_IDs(self):
        return self.event_IDs


    def get_log_type(self):
        return self.log_type


    def get_total_event_occurrences(self, event_ID):
        return self.event_occurrence[event_ID]


    def get_event_occurrence_times(self, event_ID):
        return self.times_event_generated.get(event_ID)


    def get_total_processed_events(self):
        return self.total_processed_events


    def get_event_description(self, event_ID):
        return self.event_descriptions.get(event_ID)


    def get_server_name(self):
        return self.server_name


    def get_thread_name(self):
        return self.name


    def reset_all_event_occurrences(self):
        self.event_occurrence = defaultdict(int)


    def reset_all_event_times_of_occurrence(self):
        self.times_event_generated = defaultdict(list)


    def reset_all_processed_events(self):
        self.total_processed_events = 0

