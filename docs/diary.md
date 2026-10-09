Developer's diary. 


GMT+4
10.09.2026

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
