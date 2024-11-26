from os import environ as env

LOG_LEVEL = env.get("LOGLEVEL", "INFO").upper()
LOG_FILE_NAME = env.get("LOGFILE", "debug.log")
