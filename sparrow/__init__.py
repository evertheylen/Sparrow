"""

=========
 Sparrow
=========

::


             .-----.  __  .-----------
            / /     \(..)/    -----
           //////   ' \/ `   ---
          //// / // :    : ---
         // /   /  /`    '--
        //          //..\\
  @================UU====UU================@
  |                '//||\\`                |
  |                   ''                   |
  |             S P A R R O W              |
  |                                        |
  |   Single Page Application Real-time    |
  |                                        |
  |       Relational Object Wrapper        |
  |                                        |
  @========================================@
  

Author: Evert Heylen

Basic usage
===========

Define some classes, see documentation of `entity.py` for more info.::

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
    

"""

from .sparrow import *
from .sql import *
from .entity import *
from .util import *
