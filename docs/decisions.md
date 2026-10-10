Tech stack:

**Backend:**
Python. Should be good enough for this task. 

**Frontend:**
React. I choose it because many devs are familiar with it.
Vite: AI chose it for me, to host a website. Will look into it later.

**Storage:**
PostgreSQL, because task mentions it as preferred DB.
Installation script will prompt the user to download the postgres:17 Docker image or use an existing database. Docker itself must already be installed.

**EMAIL:**
won't do. Should've take more time for this, but i see i can't make itt in time. And i decide to not ask for more time.
instead, i make a mock email history.


**Agent:** 
Grok 4.7. 
It just works™. Will give me good enough result and eat less of my subscription then Claude.



**Language:**
For simplicity, everything is English. This to not have problem with Cyrillic text encoding. And also to not switch the layout when typing.




**Timeout policy:**
If we got timeout on request - we will try twice. We will assume that single timeout is a packet loss and should not be stored in history. We will try sending a packet once more, and if there's a second tieout - we will add this in history

**Public Page**
I will skip this one too because i am not sure what to put on a public page. For now, there is a guest mode, that only shows the guest the overview, with no precise statistic. I think it will pass for now.