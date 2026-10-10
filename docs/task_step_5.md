[AI no edit]

**overview**
Need to implement groups

When signed in, on top left, there should be "Groups" page link. Guest can't access the groups page.
opening the page url as guest will return to URL list page.  
Groups page has list of group

Group can be ppaused. Pausing because of a group policy should be displayed correctly in URL info.

Each displayed group entry has next field
- id 
- name
- amount of urls in group
- pause button 
- health (UP, DOWN)
- status of responses (see "Status of Responses")
- [X] button - deletes the group
- [M] button - Opens the popup for list of email addresses

name field is edditable

**Creating new group**
Same logic as urls. After the last existing entry, there will be an empty row. 
only the name is edditable.
After clicking outside of the name, the group will be added. 
We can't create froup with empty name, or the same name as already existing group. The maximum length is 50 characters.
Same rule if we edit the group
Group created as not paused. 


**Status of Responses**
sorted by priority. 
EMPTY - if group has no URLs. 
URLS_PAUSED - if every URL is paused. This have priority over GROUP_PAUSED
GROUP_PAUSED - if the group is paused. 
POLLING - nothing above interfere the analytics. 
ERROR - every case that doesn't obey those rules

Note: if both group, and every url in a group, is paused - we show it as URLS_PAUSED. As it have greater priority.

health is separated. Health will only show "up" or "down" if the status if responses is POLLING. Otherwise, there will be NO DATA YET
DOWN - if at least one url in group is down right now, and that url. Paused are skipped.
UP - every URL was checked and it last respond was good. Paused are also skipped.
NO_DATA_YET - every else case

**URLs**
As we now have 2 pause conditions, the URL entry should show different "paused" statuses for url's own pause and for group paused policy
Something like ACTIVE, URL_PAUSED, GROUP_PAUSED
Deleted urls will not be considered for group processing. The group stays on URL entry during deletion, so it can be restored into the same group


**Adding to the group**
Each entry on URLSs page should have dropdown menu with all the groups. The first value is NONE, every URL is NONE by default.
Every entry in dropdown menu should have the same name as a name of a group it represents. 
Only admin can set the group
Same as other parts of edditing entry, we change it optimistically, and update to received payload.

**Deleting the group**
After the group deleted, every url with this group is set to NONE


**Emails**
We don't have SMTP yet. Let's just save and edit them for now. 
For mails popup, we use same logic with  table representation. Each row has editable email address and [X] button. 
After the last row, there's an empty row. Clicking outside of email field saves the data

**Guest**
Guest can't see the URL's group.


**Pause priority**
Polling will happen only if both URL and Group are not paused. 
If URL has no group - it will not be affected by group pause policy
The idea of a group is to pause many URLs at once, and also to notify a status over emails.
