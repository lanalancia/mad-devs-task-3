Developer's diary. 


GMT+4
09.10.2026

12:47 
started a project, created a repo. 
Choosing optimal model. Cursor has Grok, Claude and Gemini.
The task is not too complicated, Grok should be fine. Tbh, even a deepseek will be good enough.
Task is written in `docs/task.md`

14:50
Working on startup and installation requirements.
Decide that the script will prompt user to install PostgreSQL
User should have a docker tho. I think it is the most reasonable solution: my responsibility is database software, client's responsibility is to have satisfy the requirements (docker etc). 

15:06
In a real scenario, i think it should've been multiple repos: Backend, Frontend and one repo per tested website. Then launching them separately.
But, as a testing task, it's better to have everything in one repo.
There will me a demo_start.bat, that will launch everything. And just start.bat, that will prompt to launch either only Frontend, or Backend+DB, or a pack of websites.
To clarify. I am planning to open a couple of locally hosted simple websites, that are artificially lag and crash.

15:50 
After analysing the task, got myself a roadmap.
1) make a very minimal. Polling the google.com and show the result of polling. No frontend yet
2) make the frontend
3) make the mock websites
This is not a final plan.

17:17 
Still working on step 1: making the backend. 

17:30 
prompted AI to make the step 1, from `docs\task_step_1.md`

17:44
First iteration of agentoutput. Testing and planning next steps

18:00
tested the step 1. We now have a working backend. Committing and planning the next step. 
I want to have a react website. AI says react is a better choice, as there more devs familiar with React then Vue.

18:30 
React frontend works great. Step 2 completed
Planning the step 3: Frontend-backend communication, and also edditing 

18:30-20:00 break

21:00 
Finished writing task 3 and getting Agent's approval. making the step 3

21:25
Looks like agent is struggling with tests. later i will give it some playwright

21:32
Step 3 completed. Frontend and backend are communicate. Auth works. Creating entries works. Everything else will check tomorrow.
I rest for today. 


GMT+4
10.10.2026

10:41 
new day. Testing the completion of of task 2
Note: backend will not start if docker is not launched
Note: will not process "url.com" urls. Only works with "http://google.com"
Note: will treat "http://google.com" and "http://google.com/" as different websites
Decide to remove trailing slash after domain name, but keep the different pages of a same website. 
I think this is what task meant: checking the different pages of a same website.

13:54 
finished planning for "graph" step. Launching agent