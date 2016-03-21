
=============
 Basic usage
=============

Define some classes and create a ``SparrowModel``::

    from sparrow import *
    
    class User(RTEntity):
        username = Property(str, sql_extra="UNIQUE")
        password = Property(str, constraint = lambda p: len(p) > 8)
        key = UID = KeyProperty()
        
    class Message(Entity):
        msg = Property(str)
        from = Reference(User)
        to = RTReference(User)
        key = MID = KeyProperty()
    
    model = SparrowModel(ioloop, {"dbname": "Example"}, [User, Message])
    
    class MyListener:
        # For example, inside a websocket connection
        def new_reference(self, obj, ref_obj):
            # Send the user (registered to this connection) the new message
            self.send(ref_obj, ref_obj.to_json())
    
Dependencies
============

Sparrow depends on ``psycopg2`` and ``momoko``. The examples may use Tornado for an ioloop, but this is not required.
