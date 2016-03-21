
======================
 Database and Queries
======================

Example::

    res = await User.get(User.mail == Unsafe(usermail)).exec(db)
    u = res.single()

Shorter example::

    u = await User.get(User.mail == Unsafe(usermail)).single(db)

For preprocessing a query, you can translate it into `RawSql`, this is faster::

    users_query = User.get(User.mail == Field("mail")).to_raw()
    users = await users_query.with_data(mail = usermail).all(db)

Raw requests are also possible::

    query = User.raw("SELECT * FROM table_User WHERE UID = %(name)s")

Or if you don't like pyformat::

    query = User.raw("SELECT * FROM table_User WHERE UID = {}".format(Field("name")))
    u = await query.with_data(name = "evert").single(db)

You don't have to mention a class::

    query = RawSql("SELECT * FROM users WHERE name = 'Evert'")

More general and safer example::

    query = RawSql("SELECT * FROM users WHERE name = %(name)s", {"name": some_user_data})


Reference
=========

.. automodule:: sparrow.sql
    :members:
    :undoc-members:
    :inherited-members:
    :show-inheritance:
