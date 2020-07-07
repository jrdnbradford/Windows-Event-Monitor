# Windows Event Monitoring
Python 3-based multithreaded Windows Event monitoring program.

## Config File
The program requires a user supplied json file that provides the program's data and arguments.

### Servers
The "Servers" field name specifies the hostnames of Windows machines you wish to monitor, along with the names of the logs and the event IDs you want to monitor on those machines.

### Event Descriptions
The "Event Descriptions" field name contains user provided descriptions of the events. I've edited and used the descriptions provided by Microsoft below.

### Config Data Example
```json
{
    "Servers": {
        "localhost": {
            "Security": [4732, 4735, 4740, 4756]
        },
        "remotecomputer": {
            "Security": [4624, 4625, 4648, 4728],
            "System": [1500, 1501]
        }
    },
    "Event Descriptions": {
        "Security": {
            "4624": "An account was successfully logged on.",
            "4625": "An account failed to log on.",
            "4648": "A logon was attempted using explicit credentials.",
            "4728": "A member was added to a security-enabled global group.",
            "4732": "A member was added to a security-enabled local group.",
            "4735": "A security-enabled local group was changed.",
            "4740": "A user account was locked out.",
            "4756": "A member was added to a security-enabled universal group."
        },
        "System": {
            "1500": "The Group Policy settings for the computer were processed successfully. There were no changes detected since the last successful processing of Group Policy.",
            "1501": "The Group Policy settings for the user were processed successfully. There were no changes detected since the last successful processing of Group Policy."
        }
    }
}
```

## Usage
With a config file structured as above, you can run the monitor with:
```python
from windowseventmonitor import event_monitor

if __name__ == "__main__":
    app = event_monitor.Event_Monitor("config.json")
    app.run()
```

## Dependencies
* [pywin32](https://github.com/mhammond/pywin32)

## Authors
**Jordan Bradford** - GitHub: [jrdnbradford](https://github.com/jrdnbradford)

## License
This project is licensed under the MIT license. See [LICENSE.txt](LICENSE.txt) for details.