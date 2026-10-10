[AI no edit]


**Overview**
In this step we need to watch a down statistic for specific website. 
Only admin can see this. For signed in users, in table of URLs, in each line, add the "[i]" button. Hint is "Statistics"
It opens the page. Page should contain: 

- Percentage of successful checks per day, week, month (default: day). For this, we don't use calendar. The time period from month ago to today (calculate in hours. 24h, 24h*7 and 24h*30). 
Also shows average response time MS

- Graph. Line chart of ups and downs. It show graph for the response time in MS. Minimum 0 ms, maximum 1000 ms. If data on a graph exceed 1000 ms, we expand the maximum. 
For incident, we don't join the line.
For "no data" we also not join the line
the line graph is made with 500 dots, each dot takes an average of a fraction for this period. The width of a dot is roughly 1 pixel, so we would fit that graph on average full HD monitor. 
On graph, only the events with response shown. Timeouts are skipped.
The graph serves as a rough representation and doesn't meant to be absolutely precise. 

- Table of incidents. Should have calendar fields for dates from A to B. Should have pagination (10, 25, 50, 100, default: 10)
Incidents are sorted from newest. One incident contains all the downtime between the OK statuses. Even if we have different reasons (403, timeout etc)
Pressing on the incident reweals a popup, with a list of all errors, grouped by same error code and error messages. 
Accourding to the great task, we will not consider a singular "Not ok" as incident. Those will be skipped.

- "Return to main" button, top left corner

- "Refresh" button and "Refresh every 10 seconds" checkbox. Will request the data and update the values in fields without refreshing the page.

User shout be authorized to see this page. If no auth or token expired - we will not fetch anything and will show a "Please Sign in" popup

Fething the incident, backend should account for the time backend itself was turned off. See "No data"

**loading**
We should receive the empty page immediately, then request for data for that page, then fill the page. 


**No data**
During the incindents fetch, if we miss a data for prolongued period, we should insert a "No data, backend was logged off" line. 
Same logic for paused pollings. We can calculate a time period from last polling atempt to next polling attempt.
The "prolongued period" means "At least 1 skipped poll plus 1 minute". We expect, that high load on infrastructure may cause a delay in polling, but it won't reach the 1 minute. 

Formula to place the "No data" in a list:
next polled_at - previous polled_at >= 2 * polling_interval + 60 seconds

We should specify a reason for "no data". Be it "Server was down" or "polling was paused", or "entry was deactivated" (for deleted and restored)
For this, we need a table of pausing, resuming, deleting and restoring.


**Edits**
- Limit displayed URL field to 20 symbols. Hint should reveal a full url.
- Remove trailing slash after domain name. Keep it for page URLS
- Adding and edditing should only accept valid URL: http, https, www, localhost. The system should process port too.