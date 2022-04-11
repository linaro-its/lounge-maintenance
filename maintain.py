#!/usr/bin/env python3
""" Script to check that uploads usage is within configured parameters """

import json
import os
import sys
from datetime import datetime, timedelta, date
from io import StringIO

import requests

CONFIG_FILE = "config.json"
SLACK_TOKEN = None
SLACK_CHANNEL = None

def load_configuration():
    """ Read configuration file from script's directory """
    script_path = os.path.split(os.path.realpath(__file__))[0]
    config_file = os.path.join(script_path, CONFIG_FILE)
    if not os.path.isfile(config_file):
        sys.exit(f"Cannot find configuration file; looking at '{config_file}'")
    # Read the configuration file
    with open(config_file, "r") as config_h:
        config = json.load(config_h)
    if "folders" not in config:
        sys.exit(f"Cannot find 'folders' in configuration '{config_file}'")
    # Validate the configuration
    validate_folders(config)
    return config

def validate_folders(config):
    """ Check that the folders configuration is sane """
    folders = config["folders"]
    for folder in folders:
        validate_folder(folder)

def validate_folder(folder):
    """ Validate an individual folder configuration as sane """
    validate_attribute(folder, "name")
    validate_attribute(folder, "upload_path")
    validate_attribute(folder, "max_age")
    validate_attribute(folder, "max_storage")
    validate_attribute(folder, "warn_storage", False)

    path = folder["upload_path"]
    if not os.path.isdir(path):
        sys.exit(f"'{path}' is not a valid directory for 'upload_path'")

def validate_attribute(folder, attribute, must_have_value=True):
    """ Validate a specific attribute """
    if attribute not in folder:
        sys.exit(f"'{attribute}' attribute missing from configuration")
    if must_have_value and folder[attribute].strip() == "":
        sys.exit(f"'{attribute}' attribute cannot be empty")

def report_header(folder, done_header):
    """ Output the report header if we haven't already """
    if not done_header:
        folder_name = folder["name"]
        post_message(
            f"*Maintenance report for {folder_name}*",
            f"Maintenance report for {folder_name}")
    return True

def process_folder(folder):
    """ Check specified folder and take any appropriate action """
    output_header = False
    days_to_keep = int(folder["max_age"])
    max_storage = int(folder["max_storage"]) * 1024 * 1024
    if "warn_storage" in folder:
        warn_storage = int(folder["warn_storage"]) * 1024 * 1024
    else:
        warn_storage = None
    earliest_date = datetime.now() - timedelta(days=days_to_keep)
    # Start by getting a full list of files with their dates and sizes
    total_size = 0
    file_list = []
    deleted_files_report = StringIO()
    for dir_name, _, files in os.walk(folder["upload_path"]):
        for fname in files:
            full_name = f"{dir_name}/{fname}"
            file_stat = os.stat(full_name)
            size = file_stat.st_size
            date = datetime.fromtimestamp(file_stat.st_mtime)
            if date < earliest_date:
                delete_file(full_name, date, deleted_files_report)
            else:
                file_list.append(
                    (full_name, date, size)
                )
                total_size += size
    # Have we deleted any files?
    report_output = deleted_files_report.getvalue()
    if len(report_output) != 0:
        output_header = report_header(folder, output_header)
        post_message(None, f"A number of files have been deleted because they are over {days_to_keep} days old")
        report_date = date.today().strftime("%d-%b-%Y")
        if SLACK_CHANNEL is not None:
            upload_file(
                report_output,
                f"{report_date} - old files deleted report"
            )
        else:
            print(report_output)
    if total_size > max_storage:
        output_header = report_header(folder, output_header)
        # If we have a warning limit, we need to reduce to that, otherwise we reduce to
        # the max storage.
        target = warn_storage if warn_storage is not None else max_storage
        post_message(None,
            f"Storage is over-limit. Need to free up {total_size-target:,d} bytes")
        get_under_max_size(file_list, total_size, target)
    elif total_size > warn_storage:
        output_header = report_header(folder, output_header)
        post_message(
            f"*_WARNING!_* Total usage is {total_size:,d} bytes; warning threshold is {warn_storage:,d} bytes",
            f"WARNING! Total usage is {total_size:,d} bytes; warning threshold is {warn_storage:,d} bytes")

def upload_file(content, title):
    """ Upload text report to Slack """
    body = {
        "content": content,
        "channels": SLACK_CHANNEL,
        "title": title,
        "filetype": "text"
    }
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {SLACK_TOKEN}"
    }
    res = requests.post(
        "https://slack.com/api/files.upload",
        data=body,
        headers=headers
    )
    print(res.status_code, res.text)

def get_under_max_size(file_list, total_size, max_storage):
    """ Delete enough oldest-first files to get under the size limit """
    # Each tuple in file_list is the name, date and size.
    # We need to sort by date, oldest first.
    sorted_list = sorted(file_list, key= lambda x:x[1])
    report = StringIO()
    index = 0
    while total_size > max_storage:
        delete_file(sorted_list[index][0], sorted_list[index][1], report)
        total_size -= sorted_list[index][2]
        index += 1
    report_date = date.today().strftime("%d-%b-%Y")
    report_output = report.getvalue()
    if SLACK_CHANNEL is not None:
        upload_file(
            report_output,
            f"{report_date} - over-quota file deletion report"
        )
    else:
        print(report_output)

def delete_file(filename, mdate, io_report):
    """ Delete the specified file and notify """
    io_report.write(f"{filename} ({mdate})\n")
    os.remove(filename)

def post_message(mrkdwn, plain):
    """ Post message to Slack or screen """
    if SLACK_CHANNEL is None:
        print(plain)
        return

    headers = {
        "Content-type": "application/json; charset=UTF-8",
        "Authorization": f"Bearer {SLACK_TOKEN}"
    }
    body = {
        "channel": SLACK_CHANNEL,
        "text": plain
    }
    if mrkdwn is not None:
        body["blocks"] = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": mrkdwn
                }
            }
        ]
    res = requests.post(
        "https://slack.com/api/chat.postMessage",
        json=body,
        headers=headers
    )
    print(res.status_code, res.text)

def main():
    """ Main! """
    global SLACK_TOKEN, SLACK_CHANNEL
    config = load_configuration()
    folders = config["folders"]
    count = 0
    if "slack_auth_token" in config:
        value = config["slack_auth_token"].strip()
        if value != "":
            SLACK_TOKEN = value
            count += 1
    if "slack_channel_id" in config:
        value = config["slack_channel_id"].strip()
        if value != "":
            SLACK_CHANNEL = value
            count += 1
    if count != 0 and count != 2:
        sys.exit("Slack configuration not set correctly")
    for folder in folders:
        process_folder(folder)

if __name__ == "__main__":
    main()
