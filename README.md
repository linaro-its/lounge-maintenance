This script, run under a cron job, checks the specified Lounge uploads directory to see how much disc space is being used and to check if any of the uploads are old enough that they need to be deleted.

The script uses the following configuration to control its behaviour:

```
{
    "folders": [
        {
            "name":
                Human-sensible name for this folder
            "upload_path":
                Path to the uploads directory to check
            "max_age"
                If a file was uploaded more than this period, it is deleted
            "max_storage"
                If the total usage of the uploads directory exceeds this amount, oldest files are deleted until the usage is below the limit
            "warn_storage"
                If the total usage of the uploads directory exceeds this amount, a warning message is posted to Slack if Slack is configured below otherwise to syslog
        }
    ]
    "slack_auth_token"
    "slack_channel_id"
}
```

`max_age` is in days
`max_storage` and `warn_storage` is in megabytes
