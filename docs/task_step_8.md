[AI no edit]


**Sumarry**
maintenance and emailing

First, i decide to not do SMTP. There will be a fake history of fake sent emails. 
Second, i decide to make Mainenance as a separated page. It is for UX




**Maintenances**
A page, that only sign in users can see and access
On maintenances page, we have 2 tables. URL maintenances and group maintenances

Both works by similar logic:
We can choose URL or a group from dropdown. We can set up the datetime of start and end of maintenance.
We can also delete that maintenance with [X] button

To create a new maintenance, we have an empty row below all maintenances. We have to change a dropdown from NONE to preferred URL or Group
Default datetime of start - 1 hour from now. Of end - 2 hours from now.

maintenances have statuses:
NOT_STARTED - before start time
STARTED_AND_UP - between start and end. None polling returned down
STARTED_AND_DOWN - at least one polling returned down
ENDED - after the end time

At the moment, a maintenance for URL or group ended - we check for their incidents. This is because of Emailing feature and policies. See more at Email

There may be multiple maintenances for same URL or Group. Overlap is alloved. See more at "Maintenance Email Overlapping"
Ending ove maintenance at 12:00 and starting the next one at 12:00 (same minute) will be treated as overlapping
Maintenance tables has paginations. Same rule 10 25 50 100 with default 10

**Maintenance removal**
maintenance can be deleted with [X] button
Deleting the maintenance should be treated the same as the end of maintenance by mailing policies. See more at "Email"


**Email**
1. remove "smtp" word from start.bat and start.sh
2. Add "mailing" page. Only signed in users can see and access it. The button is in a top left row
3. on this page, we see a history of "sent" emails. Each entry has array of email addresses and mock message

mesage samples: 
- "AAA downtime incident started at BBB." 
- "AAA downtime incident ended. It was started at BBB and ended at BBB."
Where AAA is a name of url, BBB is a timestamps

We send the email on the edge of the URL incident. At the start of incident and at the end of incident. 
Email will be sent to all the receivers in a group, responsible for this URL.

Exceptions to not send the email:
- URL must be in any group, and the group should have recepients. If nowhere to send - then we won't send.
- The email will not be send if this URL under the maintenance. 

At the given moment, for a single URL, we might have one or multiple active maintenances. There might be a case when maintenances are overlapping. The letter sending logic should treat it like a singular long maintenance.
Logic for letters during maintenance (or an overlapping group of maintenances):
- If the incident started before the maintenances and ended during the maintenances, the "incident ended" will be send after the end of maintenances.
- If the incident started during maintenances and ended after the maintenances - the "incident started" will be send after the end of maintenances.
- if the incident both started and ended during maintenances - the letter will not be sent at all.
- If the incicdent started before the maintenances and ended after the maintenances - both letters will be sent immediately. Nothing will be send at the end of maintenances. This case we just treat like there was no maintenances at all

We will not notify the receivers that one "bad" status changed to another "bad" status of some URL. Only notifying about the edges of incident.


**Maintenance Email Overlapping**
It is possible to overlap maintenances for same URL, same group, or one as a URL and one as a group. It is OK
The logic from above appplies if we have at least one currently active mmaintenance for that URL. 
The realistic scenario for it will be if XXX datacenter has a blackout and also flooding, and they have different schedule to fix it. 

If we deleted the maintenance window after the maintenance ended, and all the mails were sent - we will not send the new maintenance letter. 


Note:
The "Email" page is a quick sketch, and not like what i would actually do for prod. It won't have paginarion and other optimisations. Normally there won't be any "email" page as all the emails will be seen in a email client. But as i don't have smtp setup - the "email" page will just show the history of mails.