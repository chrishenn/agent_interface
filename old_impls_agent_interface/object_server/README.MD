# Agent Interface

## To Run

Launch webserver from run_server.py

Launch clients from run_client.py

Connect to server url:port to interact


## Current Functionality

The webserver listens for mouse movement in the browser, and communicates mouse locations back to a separate (client) python process. The mouse-listening client right now
just prints those locations.

A client process can also pass messages to the webserver, which will push them to the browser. 
Messages are strings, where each string can specify multiple objects for the browser to draw -  where each object has a unique uuid.
A message can be used to delete previously drawn objects, by sending multiple object uuids to /state/rm.
Formatting for each type of object can be found in run_client.py.

Clients are segregated into their own processes right now for convenience, but that's not necessary per any existing spec.

Note: your python debugger/IDE may not shut down the server cleanly. Mine makes a mess of things and I have to restart the browser to get a clean connection, even though caching is 
'off' - I often will just run in terminal instead. I've had better luck with firefox on ubuntu than brave.


## TODO
#### TODO: generic latency benchmark for the webserver
At different amounts of simultaneous traffic in each direction, I'd like to see how long the webserver takes to report changes in each direction. We can also evaluate a multithreaded
impl of the webserver if necessary (tornado makes it super easy; see the tornado doc).

#### TODO: figure out image draw/delete issue
The graphics context on the browser seems to struggle with images that are drawn and then immediately overdrawn, 
as would happen when catching up with many buffered draws/deletions. Even under normal draw/del latency, having the mouse present
seems to break the overwriting 'del' fn in js, which draws a clear rectangle over the image.
The mouse requires the browser to report its location, which may delay the image drawing. If the overwrite command comes 
before the image has finished drawing, perhaps that would cause the behavior.

#### TODO: latency benchmark for sending via request vs. sending via localpath at different image sizes



