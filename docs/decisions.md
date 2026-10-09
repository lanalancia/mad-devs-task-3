Tech stack:

**Backend:**
Python. Should be good enough for this task. 

**Frontend: **
React. I choose it because many devs are familiar with it.
Vite: AI chose it for me, to host a website. Will look into it later.

**Storage:**
PostgreSQL, because task mentions it as preferred DB.
Installation script will prompt the user to download the postgres:17 Docker image or use an existing database. Docker itself must already be installed.

**EMAIL:**
The task wants me to use smtp. It allows to use mock smtp. 
I will use Mailpit for mock, but then a config will allow to work with real SMTP. As far as I know, the protocol is the same.


**Agent:** 
Grok 4.7. 
It just works™. Will give me good enough result and eat less of my subscription then Claude.



**Language:**
For simplicity, everything is English. This to not have problem with Cyrillic text encoding. And also to not switch the layout when typing.




**Timeout policy:**
If we got timeout on request - we will try twice. We will assume that single timeout is a packet loss and should not be stored in history. We will try sending a packet once more, and if there's a second tieout - we will add this in history