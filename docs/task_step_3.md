[AI no edit]


Now we need to befriend backend and frontend.
Backend should be reacheable at port 17778 (configurable)
backend should respond on HTTP requests and return the current states for database entries. With pagination. 
Frontend will never access a table. Fronend makes requests to backend, backend takes data from frontend, and sends to Frontend.


**Auth**
Should make Auth into real. Wrong credentials returns to quest mode
When we authorized, the page has next changes:

1) No sign in button. Instead just a logout button. To the left of logout button will be written "Signed in as USERNAME"
2) polling rate, timeout fields are now edditable. 
3) Play-Pause button for each entry.
4) "Delete entry" button. The most right. looks like "[X]", the hint is "Delete entry". See the "Deletion"
5) After the last received line the empty entry is drawn, with edditable fields. URL is empty, polling set to 30, timeout set to 5. paused. If we fill the url, it will request the backend to add this entry to DB

Clicking outside of eddited field (after edditing anything) and/or on a pause button will push the changes to backend
Should also use the JWT token. Unless we press ESC, then it will not push send the field edits and will return to saved state.

in response, there should be a payload of our page. See dynamic refresh

JWT token lifetime is 1 hour. if in response JWT token expired, a popup will say "Please sign in again". Popup should have a sigh in button that opens a HTTP auth form.

**Dynamic refresh**
Frondtend will request the fresh data for current page every 5 seconds. On receiving, it will update the fields and a play-pause button (or label).
The field should not refresh if we are mid edditing right now.

If there's an error in response, or if response timed out (5 seconds), bring a popup with error message

**pagination for dynamic refresh:**
- Frontend keeps in memory, what page and what (10, 25, 50, 100 entries) it requested the last time. Refreshing the page returns to default "page 1, 10 entries"
- When we request edit, we put pagination params in payload. Kinda like "Set entry with url GOOGLE to 30 sec, 5 sec, active. In return, give me page 1, 10 entries". 

**Deletion**
Admin can request to delete the entry. It will not delete the history. It marks the entry to "deleted"
Backend will not include the deleted entries in responses.
If we make new entry, and the URL matches the "deleted" entry, it will change the status of deleted entry to paused. Basically, restorring it.


**Creation**
After the last received line the empty entry is drawn, with edditable fields. URL is empty, polling set to 30, timeout set to 5. paused. If we fill the url, it will request the backend to add this entry to DB.
We should check for entries. If no entries with this URL - creating.
If entry with this URL exists and status "DELETED" - restoring the deleted. In restored, the values will be from entry creaton line (30 sec, 5 sec, paused for example)
If entry with this URL exists and it's not deleted - we get popup "Can't create entry, already exists"
The empty line is the only place where URL is an edditable text field

**Edditing**
URL can't be eddited. ID can't be eddited.


**Changes**
- Remove play-pause button from guest mode. Instead have a text label "polling" or "paused"
- In table, the first collumn should be ID, not index. If we have id 3 deleted, the entries should be 1, 2, 4, 5 (3 skipped)
