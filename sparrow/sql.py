

"""


"""

from functools import wraps
import copy

import psycopg2
import momoko

from .util import *


# Exceptions
# ==========

class SqlError(Error):
    """Exception raised while executing a query (or command). Wraps a psycopg2 error to
    also include the query that went wrong.
    """
    
    def __init__(self, err: psycopg2.Error, query: "Sql", data: dict):
        self.err = err
        self.query = query
        self.data = data
        
    def __str__(self):
        return "While executing this SQL:\n{s.query}\nWith this data:{data}\nThis exception occured:{s.err}".format(
            s = self, data = repr(self.data))

class NotSingle(Error):
    pass

# Classes
# =======

class Database:
    """Class for Postgres database."""
    
    def __init__(self, ioloop, dbname, user="postgres", password="postgres", host="localhost", port=5432, momoko_poolsize=5):
        dsn = "dbname={dbname} user={user} password={password} host={host} port={port}".format(
            dbname=dbname, user=user, password=password, host=host, port=port)
        self.pdb = momoko.Pool(dsn=dsn, size=momoko_poolsize, ioloop=ioloop)
        self.pdb.connect()

    async def get_cursor(self, statement: "Sql", unsafe_dict: dict):
        statement = str(statement)
        cursor = await self.pdb.execute(statement, unsafe_dict)
        return cursor


# Helper classes for building a query
# -----------------------------------

class Unsafe:
    """Wrapper for unsafe data. (For data that needs to inserted later, use Field.)"""
    
    def __init__(self, value):
        self.key = str(id(self))
        self.text = "%({0})s".format(self.key)
        self.value = value
    
    def __str__(self):
        return self.text


class Field:
    """Wrapper for data that is to be inserted into the query (with Sql.with_data) later on."""
    
    def __init__(self, name):
        self.text = "%({0})s".format(name)
    
    def __str__(self):
        return self.text


# Main classes for queries and their results
# ------------------------------------------

class SqlResult:
    """Class wrapping a database cursor. Note that most of the time, you can use the 'easier'
    methods in Sql. Instead of:
    
    >>> res = await User.get(User.name == "Evert").exec(db)
    >>> u = res.single()
    
    You can do:
    
    >>> u = await User.get(User.name == "Evert").single(db)
    
    This doesn't work for scrolling and getting raw data.
    
    The methods `single`, `all` and `amount` will try to interpret the result as object(s) of the
    given class in `self.query.cls`, don't try them if it that class is `None`.
    """
    
    def __init__(self, cursor, query: "Sql"):
        self.cursor = cursor
        self.query = query
    
    def raw(self):
        """
        Returns the raw (single) result, without any interpreting.
        If you want to do more than getting a single raw value, consider
        accessing self.cursor directly.
        """
        return self.cursor.fetchone()
    
    def raw_all(self):
        """Returns all raw values."""
        return self.cursor.fetchall()
    
    def single(self):
        """Returns a single object (and raises NotSingle if there is not only one."""
        if self.cursor.rowcount != 1:
            raise NotSingle("Not 1 result but {} result(s).".format(self.cursor.rowcount))
        return self.query.cls(db_args=self.cursor.fetchone())
        
    def all(self):
        """Returns all objects in the query."""
        return [self.query.cls(db_args=t) for t in self.cursor.fetchall()]
    
    def amount(self, i: int):
        """Returns a given number of objects in the query."""
        # TODO consider creating a version that asserts the amount specified is found
        return [self.query.cls(db_args=t) for t in self.cursor.fetchmany(size=i)]
    
    def scroll(self, i: int):
        """Scroll the cursor `i` steps. `i` can be negative. This method is chainable."""
        self.cursor.scroll(i)
        return self
    
    def count(self):
        """Return the number of rows found in the query."""
        return self.cursor.rowcount


def _wrapper_sqlresult(method):
    @wraps(method)
    async def wrapper(self, db: Database, *args, **kwargs):
        result = await self.exec(db)
        return method(result, *args, **kwargs)
    wrapper.__doc__ += "\n\nWrapped version, first argument is the database."
    return wrapper


class Sql:
    """Main class to save a given SQL query/command. Do not use directly, use the subclasses."""
    
    def __init__(self, data = {}):
        if hasattr(self, "data"):
            self.data.update(data)
        else:
            self.data = data
    
    def __preinit__(self):
        self.data = {}
    
    # By default, there is no class
    cls = None
    
    async def exec(self, db: Database):
        """Execute the SQL statement on the given database."""
        try:
            return SqlResult(await db.get_cursor(str(self), self.data), self)
        except psycopg2.Error as e:
            raise SqlError(e, str(self), self.data)
    
    # Allows you to call these method immediatly on a statement:
    single = _wrapper_sqlresult(SqlResult.single)
    all = _wrapper_sqlresult(SqlResult.all)
    amount = _wrapper_sqlresult(SqlResult.amount)
    count = _wrapper_sqlresult(SqlResult.count)
    raw = _wrapper_sqlresult(SqlResult.raw)
    raw_all = _wrapper_sqlresult(SqlResult.raw_all)
    
    def with_data(self, **kwargs):
        """This function creates a copy of the statement with added data, passed as keyword arguments."""
        newself = self.copy()
        newself.data.update(kwargs)
        return newself
    
    # By default simply create a deepcopy
    def copy(self):
        """Create a copy of the statement, by default uses `copy.deepcopy`."""
        return copy.deepcopy(self)
    
    def check(self, what):
        """Helper function to *parse* parts of a query and insert their data in `self.data`.
        Handles `Unsafe`, `Field`, other `Sql` instances and tuples. It will simply return 
        all others types.
        """
        
        if isinstance(what, Sql):
            self.data.update(what.data)
            return what.to_raw()
        elif isinstance(what, Unsafe):
            self.data[what.key] = what.value
        elif isinstance(what, Field):
            return str(what)
        elif isinstance(what, tuple):
            l = []
            for t in what:
                l.append(self.check(t))
            return tuple(l)
        return what
    
    def to_raw(self):
        """Compile this to a `RawSql` instance for more performance!"""
        return RawSql(str(self), self.data)
    
    def __str__(self):
        return "undefined so far"


class ClassedSql(Sql):
    """Version of `Sql` that also saves a given class. `SqlResult` will later try to parse its result
    as instances of this class.
    """
    
    def __init__(self, cls: type, data={}):
        self.cls = cls
        Sql.__init__(self, data)
    
    def to_raw(self):
        return RawClassedSql(self.cls, str(self), self.data)


class RawSql(Sql):
    """Simply saves a string, and also some data. This is in contrast with `Sql`, which may save
    the query in a more abstract way.
    """
    
    def __init__(self, text, data = {}):
        self.text = text
        Sql.__init__(self, data)
    
    def to_raw(self):
        """Already raw, just return self."""
        return self
    
    def copy(self):
        """More optimized version of copy."""
        return RawSql(self.text, copy.copy(self.data))
    
    def __str__(self):
        return self.text


class RawClassedSql(RawSql, ClassedSql):
    """Version of `RawSql` that also saves a given class like `ClassedSql`."""
    
    def __init__(self, cls, text, data = {}):
        # TODO possibly make this use super but I suspect it will fuck around
        self.cls = cls
        self.text = text
        Sql.__init__(self, data)
    
    def copy(self):
        return RawClassedSql(self.cls, self.text, copy.copy(self.data))


class Condition(Sql):
    pass


class Not(Condition):
    def __init__(self, cond):
        Sql.__preinit__(self)
        self.cond = self.check(cond)
        Sql.__init__(self)
    
    def __str__(self):
        return "(NOT {})".format(self.cond)

class MultiCondition(Condition):
    def __init__(self, *conds):
        Sql.__preinit__(self)
        self.conditions = [self.check(c) for c in conds]
        Sql.__init__(self)

class And(MultiCondition):
    def __str__(self):
        return "(" + " AND ".join([str(c) for c in self.conditions]) + ")"

class Or(MultiCondition):
    def __str__(self):
        return "(" + " OR ".join([str(c) for c in self.conditions]) + ")"


class Where(Condition):
    """Encodes a single 'WHERE' clause."""
    
    def __init__(self, lfield, op: str, rfield, data={}):
        """Initialize a 'WHERE' clause.
        
        Parameters:
            - `lfield` and `rfield`: Anything that can be interpreted as a part of an SQL query,
              could be of type string, `Sql`, `Field`, `Unsafe`, ...
            - `op`: Some operation that needs to be performed. Examples: '==', '>', ...
        """
        
        Sql.__preinit__(self)
        self.lfield = self.check(lfield)
        self.op = op
        self.rfield = self.check(rfield)
        Sql.__init__(self, data)
    
    def __str__(self):
        return "{s.lfield} {s.op} {s.rfield}".format(s=self)

class Order(Sql):  # TODO order on multiple attributes (might work already?)
    """Encodes an 'ORDER BY' clause."""
    
    def __init__(self, field, op: str, data={}):
        """Initialize an 'ORDER BY' clause.
        
        Parameters:
            - `field`: Anything that can be interpreted as a part of an SQL query,
              could be of type string, `Sql`, `Field`, `Unsafe`, ...
            - `op`: Either 'ASC' or 'DESC'.
        """
        
        Sql.__preinit__(self)
        self.field = self.check(field)
        self.op = op
        Sql.__init__(self, data)
        
    def __str__(self):
        return "{s.field} {s.op}".format(s=self)

class Select(ClassedSql):
    """Encodes a 'SELECT' query."""
    
    def __init__(self, cls, where_clauses = [], order: Order = None, offset=None, limit=None):
        """Initialize a 'SELECT' query. Most likely you will use `SomeEntityClass.get(...)` instead of this."""
        
        Sql.__preinit__(self)
        self.where_clauses = [self.check(c) for c in where_clauses]
        self._order = self.check(order)
        self._offset = self.check(offset)
        self._limit = self.check(limit)
        ClassedSql.__init__(self, cls)
    
    def limit(self, l):
        """'LIMIT' the query. Can be used for chaining."""
        self._limit = l
        return self
    
    def offset(self, o):
        """'OFFSET' the query. Can be used for chaining."""
        self._offset = o
        return self
    
    def where(self, *clauses):
        """'OFFSET' the query. Can be used for chaining.
        
        Parameters: a number of Where clauses.
        """
        
        self.where_clauses.extend(clauses)
        return self
    
    def order(self, _order: Order):
        """'ORDER' the query. Can be used for chaining."""
        if not isinstance(_order, Order):
            _order = +_order
        self._order = _order
        return self
    
    def __str__(self):
        s = "SELECT * FROM {cls._table_name}".format(cls=self.cls)
        if len(self.where_clauses) > 0:
            s += " WHERE " + " AND ".join(["("+str(c)+")" for c in self.where_clauses])
        if self._order is not None:
            s += " ORDER BY {}".format(self._order)
        if self._limit is not None:
            s += " LIMIT {}".format(self._limit)
        if self._offset is not None:
            s += " OFFSET {}".format(self._offset)
        return s
    

class Command(ClassedSql):
    """For INSERT, DELETE, UPDATE, CREATE TABLE, DROP TABLE, ... statements."""
    pass


sql_create_table_template = """
CREATE TABLE {tname} (
{stuff}
); 
"""

class CreateTable(Command):
    """For CREATE TABLE statements."""
    
    def __init__(self, cls):
        Command.__init__(self, cls)
    
    def __str__(self):
        return sql_create_table_template.format(
            tname = self.cls._table_name,
            stuff = ",\n".join([p.sql_def() for p in self.cls._props]
                               + [r.sql_constraint() for r in self.cls._refs]
                               + [self.cls.key.sql_constraint()])
        )

class DropTable(Command):
    """For DROP TABLE statements."""
    
    def __init__(self, cls):
        Command.__init__(self, cls)
        self.tname = cls._table_name
    
    def __str__(self):
        return "DROP TABLE IF EXISTS {tname} CASCADE".format(
            tname = self.tname
        )

class EntityCommand(Command):
    """Class for commands that work for both classes (will require inserting data later on)
    as objects.
    """
    
    def __preinit__(self, what):
        Sql.__preinit__(self)
        if isinstance(what, type):
            # an Insert that needs to be filled later on
            self.cls = what
        else:
            self.cls = type(what)
            for p in self.cls._complete_props:
                self.data[p.name] = what.__dict__[p.dataname]
        

class Insert(EntityCommand):
    """For INSERT statements."""
    
    def __init__(self, what, returning=None):
        """
        Parameters:
            - `what`: Either an instance of an `Entity` or a subclass of `Entity`.
            - `returning`: What should the database return? Expects a `Property` or None.
        """
        
        EntityCommand.__preinit__(self, what)
        self._returning = self.check(returning)
        Command.__init__(self, self.cls)
    
    def returning(self, prop):  # TODO return multiple attributes?
        """Set what the database should return. Can be chained."""
        self._returning = prop
        return self
    
    def __str__(self):
        s = "INSERT INTO {cls._table_name} ({props}) VALUES({vals})".format(
            cls = self.cls,
            props = ", ".join([p.name for p in self.cls._complete_props]),
            vals = ", ".join(["%("+p.name+")s" for p in self.cls._complete_props])
        )
        if self._returning is not None:
            s += " RETURNING " + str(self._returning)
        return s
    

class Update(EntityCommand):
    def __init__(self, what):
        """
        Parameters:
            - `what`: Either an instance of an `Entity` or a subclass of `Entity`.
        """
        
        EntityCommand.__preinit__(self, what)
        EntityCommand.__init__(self, self.cls)
    
    def __str__(self):
        return "UPDATE {cls._table_name} SET ({props}) = ({vals}) WHERE {cls.key} = ({keyvals})".format(
            cls = self.cls,
            props = ", ".join([p.name for p in self.cls._complete_props]),
            vals = ", ".join(["%("+p.name+")s" for p in self.cls._complete_props]),
            keyvals = ", ".join(["%("+p.name+")s" for p in self.cls.key.referencing_props()])
        )

class Delete(Command):
    def __init__(self, what):
        """
        Parameters:
            - `what`: Either an instance of an `Entity` or a subclass of `Entity`.
        """
        
        EntityCommand.__preinit__(self, what)
        EntityCommand.__init__(self, self.cls)
    
    def __str__(self):
        return "DELETE FROM {cls._table_name} WHERE {cls.key} = ({keyvals})".format(
            cls = self.cls,
            keyvals = ", ".join(["%("+p.name+")s" for p in self.cls.key.referencing_props()])
        )

