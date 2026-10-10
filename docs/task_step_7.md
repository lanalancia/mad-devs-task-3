[AI no edit]


**Sumarry**
mock websites with errors.
Option #3 in start.bat
Will launch multiple simple websites at once. 

1) always returns 200, artificial delay 100 ms
2) always return 404,atificial delay 300 ms
3) Switches every 3 minutes. Returns 200, but the delay is either 100 ms or 900 ms. the "3 minutes" is in UTC time, so we would have pretty noticeable squarred teeth
4) Website that respond in 6 seconds. This will show what happens if we exceed timeout

the posts are 17781, 17782, 17783, 17784

Also add those addresses in init-poll-entries.json
Polling parameters are the same as usual: 30s interval, 5s timout

Note for website #3:
Accourding to my calculations, day can be split in 500 pieces roughly below 3 minutes. So a 3 minute "switching" interval and 30 seconds polling interval gives me couple of dots at 100 ms and then couple of dots at 900 ms
We split the current UTC time on pieces of 3 minutes. Even piece for 100 ms, odd piece for 900 ms. 



Mock websites shouldn't be configurable. We don't need to configure them


**Changes**
Page with statistic of specific url: if we have open incident - how long is it down.
If all incidents are closed - "no incidents right now"

Also the response time from the last polling. 
Should be placed between "Last polling timestamp" and "poll now" button

