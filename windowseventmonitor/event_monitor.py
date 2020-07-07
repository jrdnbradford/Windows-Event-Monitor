import json
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

from windowseventmonitor import monitor_thread



class Event_Monitor:
    """
    Class is an application that monitors Windows Event Logs.

    Parameter config_file (string): File containing necessary data

    Parameter retry_delta (datetime.timedelta): Kwarg that sets how
    often the program should attempt to respawn threads. Defaults to 5 minutes.

    Parameter export_delta (datetime.timedelta): Kwarg that sets how
    often the program exports data. Defaults to 1 hour.
    """
    def __init__(self, config_file, retry_delta = timedelta(minutes = 5), export_delta = timedelta(hours = 1)):
        try:
            with open(config_file, "r") as config:
                data = json.loads(config.read())
        except:
            raise FileNotFoundError("Config file not found")

        self._app_start = datetime.now()
        self._active_threads = []
        self._servers = set()
        for server in data["Servers"]:
            self._servers.add(server)
            for log_type in data["Servers"][server]:
                event_IDs = data["Servers"][server][log_type]
                thread = monitor_thread.Monitor_Thread(server, log_type, event_IDs)
                self._active_threads.append(thread)
        self._threads_to_restart = []
        self._retry_delta = retry_delta
        self._export_delta = export_delta


    def run(self):
        """
        Main thread of execution. run() ensures that spawned Monitor_Threads
        stay alive. If any are found dead, it attempts to start a new thread
        with the dead Monitor_Thread's data in case the problem is temporary.

        Stoppable with Ctrl+C.
        """
        start = datetime.now()
        for thread in self.get_active_threads(): thread.start()
        try: # Runs concurrently with threads
            while True:
                for thread in self.get_active_threads():
                    if not thread.is_alive():
                        self.get_dead_threads().append(thread.respawn_thread(self.get_retry_delta()))
                        thread.add_thread_failure()
                        thread._acknowledged_failure = True
                # Don't remove threads that died AFTER iteration
                self.remove_dead_threads()

                for thread in self.get_dead_threads():
                    if not thread._failure_printed_to_console:
                        print(f"{thread.name} failed. Will attempt restart in {self.get_retry_delta()}")
                        thread._failure_printed_to_console = True

                    if thread._restart_time < datetime.now():
                        print(f"Attempting to restart {thread.name}")
                        thread._failure_printed_to_console = False
                        thread._restart_time = None
                        thread.start()
                        self.get_active_threads().append(thread)
                # Remove threads that have respawned
                self.remove_respawned_threads()

                # Export after time specified by delta
                if datetime.now() >= start + self.get_export_delta():
                    self.export_json()
                    start = datetime.now()

        except KeyboardInterrupt:
            print("Keyboard interrupt")
        except Exception as err:
            print(err)
        finally: # Save necessary data before exit
            self.export_json()
            print("Exiting program")
            sys.exit(0)


    def export_json(self):
        """Writes data from application to json file."""
        export_timestamp = datetime.now().timestamp()

        # Application data
        data_dict = { # Dictionary to be exported to json file
            "Monitor App": {
                "Export Timestamp": export_timestamp,
                "Servers": list(self.get_servers()),
                "Event Logs": {
                    server: {} for server in self.get_servers()
                }
            }
        }
    
        # Thread data
        for thread in self.get_all_threads():
            data_dict["Monitor App"]["Event Logs"][thread.get_server_name()][thread.get_log_type()] = {
                "Thread Start Timestamp": thread._latest_start.timestamp(),
                "Total Processed Events": thread.get_total_processed_events(),
                "Total Thread Failures": thread.get_failure_total(),
                "Event IDs": { # Value built below
                    # 1111: {
                    #   "Total": int,
                    #   "Description": str or None,
                    #   "Timestamps": [floats] or None
                    # }
                }
            }
            event_ID_key = data_dict["Monitor App"]["Event Logs"][thread.get_server_name()][thread.get_log_type()]["Event IDs"]
            try: # Build Event IDs dictionary value for data_dict
                for event_ID in thread._event_IDs:
                    event_ID_key[event_ID] = {
                        "Total": thread.get_total_event_occurrences(event_ID),
                        "Description": thread.get_event_description(event_ID),
                        "Timestamps": thread.get_event_occurrence_times(event_ID)
                    }
            except KeyError as err:
                print(err)

        # Create log directory
        if not os.path.exists(os.path.join("windowseventmonitor", "eventlogs")):
            os.mkdir(os.path.join("windowseventmonitor", "eventlogs"))
        
        event_log_json_file = os.path.join("windowseventmonitor", "eventlogs", f"{export_timestamp}.json")
        try: # Write to json
            with open(event_log_json_file, "w") as f:
                data = json.dumps(data_dict, indent = 4)
                f.write(data)
            print("Exported logs")
        except PermissionError as err:
            print(err)


    def get_active_threads(self):
        return self._active_threads


    def get_all_threads(self):
        return self._active_threads + self._threads_to_restart


    def get_dead_threads(self):
        return self._threads_to_restart


    def get_export_delta(self):
        return self._export_delta


    def get_retry_delta(self):
        return self._retry_delta


    def get_servers(self):
        return self._servers


    def remove_respawned_threads(self):
        self._threads_to_restart = [thread for thread in self.get_dead_threads() if thread._restart_time != None]


    def remove_dead_threads(self):
        self._active_threads = [thread for thread in self.get_active_threads() if not thread._acknowledged_failure]