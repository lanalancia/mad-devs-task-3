[AI no edit]


For step 1, only doing the backend. It will show the result to console. Backend on python.

if Install.py chosen option is "Install posgresql", it should read init-poll-entries.json and fill the database.
For now it's google.com and http://aylfgktaggndajwyndgaydgahpdawpdhmawnydghmawnygdoamndhawm.com/
install.py only adds the URLS from init-poll-entries.json to freshly installed postgresql. If the user decides to not install postgresql, then installer will not add those entries to polling. 
The idea that if it's connected to existing DB - there's no neexd to "install" urls on it.

for init-poll-entries.json we need the next keys and values:
url : https://www.google.com and http://aylfgktaggndajwyndgaydgahpdawpdhmawnydghmawnygdoamndhawm.com/
timeout: 5 seconds
polling rate: 30 seconds
expected code: 200
polling status: ACTIVE (enum ACTIVE, PAUSED)

**Creating the table:**
1. install.py will create the tables in created database.
2. Only in created database! We will not edit the existing databases, local or remote. 
3. On startup, backend will check if the required table is present in database. If the table is missing - backend exits with error message. For now this is ok, we will solve it in a future

There should be tables for history, urls to poll, and user authorisation.
Lets not make it too secure. admin-admin with no password encryption is enough.
User credentials will be in init-users.json
On this step, we won't check that table in any way, we just make it exist

If we run install.py the second time - it will see that the database and tables already exist. it will prompt us to reinstall the database on this step. This will be useful in a future as a quick cleanup+fresh install for every step.


**Startup (backend)**
1. We check the presence and access to database. If no access to database - error, exit
2. Backend check the table in DB. If no table or wrong format - error, exit
3. For every entry, we check the time since the last poll. If it exceeds the ppolling rate - we start that polling immediately.



**Polling**
all pollings should work in parallel.
For every entry, backend makes the request to URL. Then expects the result during timeout. 
if we didn't get response during timeout - we repeat it one time. just to make sure, we won't mark packet loss as a "service down"
only if we had timeout twice, it will be saved to history as "Down detected"
if it's time to make a new request, but we are haven't reach timeout on a previous request - we skip the new polling. For now it should be good enough. 
normally it will work like that:
1. backend polls entries
2. backend received the response
3. backend appends to history and prints to console
4. Wait for time when we should poll and then poll
5. poll this entry again
The timeout is not added to interwal. If it's time for new poll, but we process through the old poll for this entry - we just skip that new poll.

Explicitly repeating: polls should be indeppendent from eachother and don't block each other

Every entry will be polled repeatedly no matter the result: success, fail, dead domen, prohibited etc. 

Backend should write the polling result into DB. Backend outputs to console thhe copy of history entry, it made to DB. 
Ensure that it appends to history. Not owerrides or erases it.

**Problems dring runtime and how to solve them:**
- PAUSED entries is not polled. 
- If we don't have a history for entry - we poll it immediatelly after it's added. 
- When the entry is unpaused or added - we check the history. If it's time to poll - we poll immediately. Or wait for timme to poll and then poll
- The polling should occure at the polling rate. i.e. if the poll rate is every 30 seconds and we got response after 2 seconds - we make new request on 30th second form request. Not on 32nd!


**Starting the whole project**
I also want start.bat to be a starter for specific service: be it frontend, backend+db+smtp, one option per mock website 
For now, the only valid option is named "backend+db+smtp", and in fact it does the backend+db part, skips the smtp.
In a future there will be "master_start.bat". For now, i will just start the start.bat myself multiple times

**Criteria of completion:**
- backend writes to console "Requesting the URL, response status: AAA, message: BBB"
- backend fills the DB when should
- polling rate and other field matches the settings.

**Skipping:**
- SMTP. Not needed for now
- Creating table on remote DB. For now, we only create table on our DB. We don't edit the remote DB




**post completion note**
Task 1 completed, tested, closed.

