# JIRA version sorter

Python script to sort JIRA versions.  Sorts "lineages" of versions.  A lineage
is defined by user-provided predicate on the `name` of the version.  The sorting
is done using user-provided comparator.

Tested only on JIRA server v7.1.6.

## Prerequisites
- python3 is installed.
- pip3 package `requests` is installed.
- Your JIRA account has permission to edit JIRA versions.
- You have a certificate file, needed to access the JIRA website.

## Usage
1. Manually make sure that all first builds in a lineage are positioned
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
