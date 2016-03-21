
==========
 Entities
==========

How? Simple, inherit from Entity and define some properties. Define a property with its type and 
possibly an extra string that gets included in the 'CREATE TABLE' statement. Example::

    class User(Entity):
        name = Property(str)
        mail = Property(str, sql_extra="UNIQUE")

(In what follows I will often skip properties that are not essential to exemplify the topic at 
hand.)

Keys
====

If you try the above example, sparrow will complain, because there is no key. An Entity class
can only have 1 key, and you define it with ``key``. So if we for example want to have a ``UID``
attribute and define it as key, we would do::

    class User(Entity):
        name = Property(str)
        UID = Property(int)
        key = Key(UID)
        
However, this would be irritating. We would have to come up with a unique UID every time we
create a User. To solve this problem, we have a ``KeyProperty``. This will use Postgres' ``SERIAL``
type to create the property. Use it like this::

    class User(Entity):
        name = Property(str)
        UID = KeyProperty()
        key = UID

We can shorten this even further::

    class User(Entity):
        name = Property(str)
        key = UID = KeyProperty()

Note that for a ``KeyProperty``, its value will be ``None`` until you insert the object into
the database (which will provide the value for it).

A ``Key`` can also contain multiple properties::

    class User(Entity):
        firstname = Property(str)
        lastname = Property(str)
        key = Key(firstname, lastname)

You can always use a ``key`` attribute of an object as if it was an entity::

    u = User(...)
    u.key = ("Evert", "Heylen")

In case of multiple properties, you need to put it in a tuple. Otherwise (also in the case of a
``KeyProperty``, it has to be a simple value.

Constraints
===========

There are two types of constraints: constraints for properties and object-wide constraints.
The latter is only checked when calling ``__init__``, ``update`` and ``insert``. An example::

    class User(Entity):
        name = Property(str)
        password = Property(str, constraint=lambda p: len(p) >= 8)  # Password of minimum length

        constraint = lambda u: u.name != u.password  # Don't use your name as password

References
==========

Often, you want to keep a reference to other objects. In sparrow, you use a ``Reference`` to do so.
A Reference will automatically create properties to fully save a key of another Entity class. 
Note that a ``Reference`` can not be constrained, but it can be used in a ``Key``.::
    
    class User(Entity):
        firstname = Property(str)
        lastname = Property(str)
        key = Key(firstname, lastname)
    
    class Message(Entity):
        msg = Property(str)
        to = Reference(User)
        from = Reference(User)

In this case, the table created for ``Message`` will have 5 attributes: ``msg``, ``to_firstname``,
``to_lastname``, ``from_firstname`` and ``from_lastname``. It will also be constrained (in the DB) so
so that always refers to a ``User`` in the database. However, you should not set these attributes 
directly, you should rather use ``to`` and ``from`` as if it were properties.::

    >>> msg = Message(msg="Test", to=some_user.key, from=other_user.key)
    >>> # Or after initializing
    >>> msg.to = another_user.key

Remember to always refer to the key of an object, not the object itself.

JSON
====

To get a JSON representation, simply call ``obj.to_json()``. Some options are available to change
this output. You can override ``json_repr``, which has to return some datatype that is convertible
to JSON. By default, it returns a dictionary of all properties. This too you can control::

    class User(Entity):
        name = Property(str)
        password = Property(str, json=False)  # We don't want to send passwords

Real-time
=========

Sparrow has excellent support for real-time updates. Or you could call it live updates but
'spalrow' is not a word. Anyway, in its simplest form, just inherit from ``RTEntity`` instead of
``Entity``. This will allow you to call ``add_listener`` (and ``remove_listener``) on the object::

    class User(RTEntity):
        name = Property(str)
        key = UID = KeyProperty()

Whenever ``update`` or ``delete`` is called, all listeners will get notified of this.

A ``RTEntity`` gets an extra method ``send_update`` which will trigger all listeners to be notified
of an update without actually writing to the database.

Real-time references
--------------------

The real fancy stuff is a ``RTReference`` though. This will make sure that whenever some object
refers to another object, it will automatically call ``add_reference`` on all listeners of the
referencing object. For example, with a few modifications we can add live messaging to our
``Message`` class of before::
    
    class Message(Entity):
        msg = Property(str)
        to = RTReference(User)  # 
        from = Reference(User)  # Assuming the sender knows it has sent a message, it doesn't
                                # need to know it has sent a message again.

A ``RTReference`` requires a ``RTEntity`` as referencing class.

Both ``RTReference`` and ``RTEntity`` add some overhead, so only use it when necessary.

The listeners need to following a certain interface, more info about that in ``RTEntity``.

Database
========

More info about this can be found in the docs for the file ``sql.py``. However, some 
``Entity``-specific things are not explained there. A list of the possibilities 

    * Classmethods (where ``Cls`` is a subclass of ``Entity``):
        - ``Cls.get(Cls.prop1 == val, Cls.prop2 <= Cls.prop3)``: returns a ``SELECT`` query.
        - ``Cls.raw("SELECT * FROM ...")``: returns whatever query you want.
        - ``obj = await Cls.find_by_key(some_key, db)``: returns **an instance** with that key.
    * Methods (where ``obj`` is an instance of a subclass of ``Entity``):
        - ``await obj.insert(db)``: inserts the object in the database. Will also fill in the
          ``KeyProperty`` if it exists.
        - ``await obj.update(db)``: update in the database.
        - ``await obj.delete(db)``: delete from the database.

Caching
=======

It's there, and it's magic. All objects in memory with the same key will, in fact, be the exact
same object (I'm talking about ``is`` equality, not ``==`` equality). It will regulate itself and you
shouldn't really care about it. However, I'd like to mention that if an object is in the cache, it
will be crazy fast to call ``find_by_key``, as it will not use the database at all.


Reference
=========

.. automodule:: sparrow.entity
    :members:
    :undoc-members:
    :inherited-members:
    :show-inheritance:
