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
        threading.Thread.__init__(self, target = self.monitor_events, args = [server, log_type, event_IDs])
        now = datetime.now()
        self._initial_start_timestamp = now.timestamp()
        self._latest_start = now
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
        self._failures = 0
        self._restart_time = None
        self._acknowledged_failure = False

        with open("config.json", "r") as config:
            config_data_dict = json.loads(config.read())
            event_descriptions = config_data_dict["Event Descriptions"][self._log_type]
            self._event_descriptions = { # Dictionary comprehension
                int(event): event_descriptions[event] # Event IDs in json are strings
                    for event in event_descriptions
                        if int(event) in self.get_event_IDs()
            }


    def event_fits_criteria(self, event):
        return event.EventID in self.get_event_IDs() and event.TimeGenerated > self._latest_start


    def respawn_thread(self, delta):
        """
        Copies relevant data from dead thread and adds it to a new one.

        Parameter delta (datetime.timedelta): timedelta that sets how long
        from now to respawn the thread.

        Returns thread.
        """
        new_thread = Monitor_Thread(self._server_name, self._log_type, self._event_IDs)

        now = datetime.now()
        new_thread._latest_start = now
        new_thread._initial_start_timestamp = self._initial_start_timestamp
        new_thread._start_date = self._start_date
        new_thread._event_occurrence = self._event_occurrence
        new_thread._times_event_generated = self._times_event_generated
        new_thread._total_processed_events = self._total_processed_events
        new_thread._failures = self._failures
        new_thread._restart_time = now + delta
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
        self._event_occurrence[event_obj.EventID] += 1
        self._times_event_generated[event_obj.EventID].append(event_obj.TimeGenerated.timestamp())
        self._total_processed_events += 1


    def add_thread_failure(self):
        self._failures += 1


    def get_failure_total(self):
        return self._failures


    def get_event_IDs(self):
        return self._event_IDs


    def get_log_type(self):
        return self._log_type


    def get_total_event_occurrences(self, event_ID):
        return self._event_occurrence[event_ID]


    def get_event_occurrence_times(self, event_ID):
        return self._times_event_generated.get(event_ID)


    def get_total_processed_events(self):
        return self._total_processed_events


    def get_event_description(self, event_ID):
        return self._event_descriptions.get(event_ID)


    def get_server_name(self):
        return self._server_name


    def get_thread_name(self):
        return self.name


    def reset_all_event_occurrences(self):
        self._event_occurrence = defaultdict(int)


    def reset_all_event_times_of_occurrence(self):
        self._times_event_generated = defaultdict(list)


    def reset_all_processed_events(self):
        self._total_processed_events = 0

