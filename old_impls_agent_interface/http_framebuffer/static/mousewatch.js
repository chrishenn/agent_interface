$( function() {

    document.addEventListener('mousemove', handleMouseMove);
    function handleMouseMove(event) {
        $.ajax({url: "/mouse/move", type: "POST", dataType: "json", data:{x:event.pageX, y:event.pageY}});
    }

    document.addEventListener('mousedown', handleMouseDown);
    function handleMouseDown(event) {
        $.ajax({url: "/mouse/click", type: "POST", dataType: "json", data:{button:event.button}});
    }

} );