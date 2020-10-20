# JIRA version sorter

Python script to sort JIRA versions. Tested only on JIRA server v7.1.6.

## Prerequisites
- python3
- pip3 package `requests` is installed
- Your JIRA account has permission to edit JIRA versions
- You have a certificat file, needed to access the JIRA website.

## Usage
1. Manually make sure that all first builds (".0" at the end) are positioned
   properly.
2. You have to provide file `config.py` with following properties:
   ```
   my_user_name = "<your JIRA login>"
   jira_url = "<URL of the JIRA server>"
   verify = "path/to/certificate/file"
   ```
3. Choose which project to sort by uncommenting one of the lines at the bottom
   of `jira_versions.py`, or writing your own call to `clean_up_release()`.
4. Launch the script using `python3 jira_versions.py` or `./jira_versions.py`.
   The script will ask your JIRA password for authentication.
