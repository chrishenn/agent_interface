$( function() {

    document.addEventListener('keydown', handle_key);
    function handle_key(event){
        $.ajax({url: "/key/update", type: "POST", dataType: "json", data:{'shiftKey':event.shiftKey, 'ctrlKey':event.ctrlKey, 'altKey':event.altKey, 'Key':event.key}});
    }

} );

