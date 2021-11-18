# G_bCommunityWorker
Heroku worker that:  
* Tracks Vk G_b community members online activity
* Provide an activity of Vk bot that answers users' requests

Ideally it would be two dyno's: ```worker``` and ```clock```. 
But in that way they will consume 2x more Heroku's hours.

You may see the website [here](https://general-bum-activity-tracker.herokuapp.com/) 