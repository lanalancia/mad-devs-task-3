[AI no edit]


We have somewhat working backend, that can poll the websites. 
I tested, it works and looks like the timings are correct. Time to make some React frontend. 
in start.bat, option "Frontend" should launch a webserver. The website should be reachable from http://localhost:17777

frontend/config.ini should specify the address of backend
For now, we will not make the frontend-backend interraction. only the layout. 


It should have a list with pagination. default value is 10, available values are 10, 25, 50, 100. 
Don't make it pretty. Just make it working.

Filling it will be in step 3. For now, just hardcode a google.com entry (consider the data format from previous task)

Each list entry should have:
- index
- url
- polling rate
- play-pause button
- Status of polling (ACTIVE, DOWN and so on)
- Erorr message if any
- Time of last polling attempt in UTC. On mouse hover shows hint: next time of polling in UTC. 

Play-pause button will optimistically change it state on click. For now, it will do nothing, only change visual.

"Sign In" button. It is placed in a top right corner of a page. It should create a Simple HTTP Auth popup. For now, any combo of username and password returns us to guest page. 

The plan is to use JWT token pattern for edits. But at this stage don't have a backend access anyway.

This is a guest version of a page. Authorized version will be in the next task.

**New stuff**
Frontend page


**Editting existing stuff**
init-poll-entries should contain our frontend page. For not particular purpose, it just will be funny. 
Add Node.js to requirementes in readme
Specify in readme, which requirements are needed for backend and for frontend. It is because the user would want to run backend and frontend on different machines 