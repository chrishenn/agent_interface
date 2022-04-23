
## current arch

(only for testing; in final impl old frames can be skipped)

Client sends message to server. Server buffers frames into list.
Browser requests a single frame, new to it. Browser draws frame, requests another, until all are drawn.

This process can draw 202 frames in 7.2 sec, or ~28 fps.

If only the latest frame is sent server->browser at each request, the process takes ~2 sec.


## todo

This call-response networking model is far too slow at a theoretical best 28 fps. Need to move to video-stream model to avoid 
back-and-forth network requests.


## timings 

cv2.imencode is timed at 10 msec per call for 1080p frame (cv2 version 3.4.2.17). 

resolving relative locs and rendering 1080p frame is timed at 2-3 msec.

base64 encoding 1080p frame is timed at 0.03 msec.

server->browser load appears to take 15 msec on local->local.