[AI no edit]

**Sumarry**
Let's fix some bugs before continuing



- sign in should stay after refreshing the page
I want this so it will be easier to test.

- Manual call for poll (in statistics) 
when we open statistic for specific URL, under the "refresh" button at the bottom, we should have "Poll now" button. 
When pressed, we try to call the polling right now.

1. we check for current polling for this url. If backend already made the request and haven't received a response yet - we raise popup.
2. If not waiting for response right now - then we initiating the new request

Note: making new poll will shift the scheduled polling of this URL. And this is OK.
"poll now" can be called during paused state. It will not resume the pauses on URL or group.



- Polling interval should accepts 30 seconds - 60 minutes
make it edditable spinbox. Clicking the spinbox will make a ton of "edit" calls and it's ok
60 minutes will be represented as 3600 seconds

- Add setting for expected code in response
Signed in user should be able to edit the expected error code 
Make it spinbox, from 100 to 599. Default 200
