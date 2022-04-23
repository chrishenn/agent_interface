$( function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};

    $("#document").one("", shapeDraw.setup() );

    stateGetter.poll();

});


const M_SEP = ";-MSEP-;";
const T_SEP = ";-TYPE-;";


var stateGetter = {
    errorSleepTime: 50,
    min_errorSleepTime: 100,
    max_errorSleepTime: 4000,

    cursor: 0,
    state_type: [],
    state_data: [],

    poll: function() {

        console.log("stateGetter.poll called");

        var args = {'cursor':stateGetter.cursor};

        $.ajax({url: "/state/update", type: "GET", dataType: "text", data:args,
            success: stateGetter.onSuccess,
            error: stateGetter.onError});
    },

    onSuccess: function(response) {
        try {
            stateGetter.newMessages(response);
        } catch (e) {
            console.log("error when handling stateGetter request-response")
            stateGetter.onError();
            return;
        }
        // stateGetter.errorSleepTime = stateGetter.min_errorSleepTime;
        // window.setTimeout(stateGetter.poll, 0);
    },

    onError: function(response) {

        stateGetter.errorSleepTime = Math.min(stateGetter.errorSleepTime*2, stateGetter.max_errorSleepTime);

        // console.log("Poll error; sleeping for", stateGetter.errorSleepTime, "ms");
        // window.setTimeout(stateGetter.poll, stateGetter.errorSleepTime);
    },

    newMessages: function(response) {

        // var messages = response.trim().split(M_SEP);
        //
        // for (var i = 0; i < messages.length; i++)
        // {
        //     // cursor counts number of messages received
        //     stateGetter.cursor += 1;
        //
        //     var message = messages[i].trim();
        //
        //     if (message) stateGetter.handleMessage(message);
        // }

        stateGetter.cursor += 1;
        shapeDraw.draw_frame(response.trim());
    },

    // This handler will call the appropriate function by appending 'draw_' to the object 'type' name specified by the message.
    // Functions to draw are contained in the 'shapeDraw' class.
    handleMessage: function(message) {
        var m_parts = message.split(T_SEP);

        var mode = m_parts[0].trim();
        var type = m_parts[1].trim();
        var data = m_parts[2].trim().slice(1,-1).trim();

        // set the canvas into default draw-over mode to draw, or destination-out mode to overwrite existing shape
        switch(mode){
            case "draw": shapeDraw.set_draw(); break;
            case "del": shapeDraw.set_del(); break;
            default: console.log("invalid mode string in message");
        }

        // also call custom function depending on the mode
        var draw_fn = shapeDraw[mode + "_" + type];
        if (typeof draw_fn === "function") draw_fn(data);
    },

};




var shapeDraw = {
    // for each shape-drawing fn, the 'data' argument is a string.
    // fields within the 'data' string are space-separated
    c: null,
    fileElem: null,
    canvas: null,

    //////////////////////
    // Utilities

    setup: function() {
        console.log("shapeDraw.setup called");

        const canvas = document.querySelector('canvas');
        canvas.width = innerWidth;
        canvas.height = innerHeight;
        shapeDraw.canvas = canvas;

        shapeDraw.c = canvas.getContext('2d');

        window.addEventListener('resize', shapeDraw.resizeCanvas, false);
    },

    resizeCanvas: function () {
        console.log(" resizeCanvas called ")
        shapeDraw.c.width = window.innerWidth;
        shapeDraw.c.height = window.innerHeight;
    },

    // helper to apply JSON.parse to each item in an array in-place
    parseItem: function(item, index, arr) {
        arr[index] = JSON.parse(item);
    },

    set_draw: function() {
        shapeDraw.c.globalCompositeOperation = "source-over";
    },
    set_del: function() {
        shapeDraw.c.globalCompositeOperation = "destination-out";
    },



    //////////////////////
    // Draw functions

    draw_circle: function(data) {
        console.log("draw_circle called");

        shapeDraw.c.beginPath();
        shapeDraw.c.arc( ...data.split(" "), 0, Math.PI * 2);
        shapeDraw.c.fill();
    },

    draw_rect: function(data) {
        console.log("draw_rect called");

        shapeDraw.c.beginPath();
        shapeDraw.c.rect(...data.split(" "));
        shapeDraw.c.fill();
    },

    draw_text: function(data) {
        console.log("draw_text called");

        data = data.split(" ");

        var font = data.slice(3, data.length);
        font = font.join(" ");
        shapeDraw.c.font = font;

        shapeDraw.c.fillText( ...data.slice(0, 3) );
    },

    draw_im_path: function(data) {
        console.log("draw_image called");
        // for security reasons, we must ask the server for the image data from disk

        data = data.split(" ");

        var oReq = new XMLHttpRequest();
        oReq.open("get", "/image/upload" + data[0], true );
        oReq.responseType = "blob";
        oReq.onload = function ( oEvent )
        {
            var imgSrc = URL.createObjectURL( oReq.response );

            var img = new Image();
            img.src = imgSrc;

            img.onload = function() {
                data = data.filter(e => e !== 'null');
                shapeDraw.c.drawImage(img, ...data.slice(1));
            }
            window.URL.revokeObjectURL( imgSrc );

        };
        oReq.send( null );
    },

    draw_im_blob: function(data) {
        console.log("draw_blob called");

        data = data.split(" ");

        var img = new Image();
        img.src = data[0];
        img.onload = function(){
            shapeDraw.c.drawImage(img, ...data.slice(1));
        }
    },

    draw_frame: function(frame_data) {
        console.log("draw_frame called");

        var img = new Image();
        img.src = frame_data;
        img.onload = function(){
            shapeDraw.c.drawImage(img, 0, 0, 1920, 1080);
            stateGetter.poll();
        }
    },



    //////////////////////
    // Deleter Functions

    del_circle: function(data) {
        // stroke around the circle with size 20, or else circle leaves ring behind
        shapeDraw.c.lineWidth = 20;

        shapeDraw.c.beginPath();
        shapeDraw.c.arc( ...data.split(" "), 0, Math.PI * 2);
        shapeDraw.c.stroke();
        shapeDraw.c.fill();
    },

    del_rect: function(data) {
        if ( typeof data === "string" ) data = data.split(" ");
        shapeDraw.c.clearRect( ...data );
    },

    del_text: function(data) {

        data = data.split(" ");

        var font = data.slice(3, data.length);
        font = font.join(" ");
        shapeDraw.c.font = font;

        shapeDraw.c.lineWidth = 20;

        shapeDraw.c.strokeText(...data.slice(0, 3));
        shapeDraw.c.fillText(...data.slice(0, 3));
        shapeDraw.c.stroke();
    },

    del_im_path: function(data) {
        shapeDraw.del_rect(data.split(" ").slice(1));
    },

    del_im_blob: function(data) {
        shapeDraw.del_rect(data.split(" ").slice(1));
    },

};