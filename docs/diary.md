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

