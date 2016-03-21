
import collections
import datetime
import copy
from functools import wraps
import itertools
import json
import weakref  # This is some serious next-level stuff :D
import types  # For annotations

from .util import *
from .sql import *

# Forward declarations for annotations
MetaEntity = None
Entity = None
RTEntity = None

# Exceptions
# ==========

class PropertyConstraintFail(Error):
    """Raised when a property failed to follow its constraint."""
    
    def __init__(self, obj, prop):
        self.obj = obj
        self.prop = prop
    
    def __str__(self):
        return "Constraint of property {s.prop} of object {s.obj} failed".format(s=self)

class ObjectConstraintFail(Error):
    """Raised when an object failed to follow its constraint."""
    
    def __init__(self, obj):
        self.obj = obj
    
    def __str__(self):
        return "Object-wide constraint of object {s.obj} failed".format(s=self)


# Entity stuff
# ============

def create_where_comparison(op):
    def method(self, other):
        return Where(self, op, other)
    return method

def create_order(op):
    def method(self):
        return Order(self, op)
    return method

class Queryable:
    __lt__ = create_where_comparison("<")
    __gt__ = create_where_comparison(">")
    __le__ = create_where_comparison("<=")
    __ge__ = create_where_comparison(">=")
    __eq__ = create_where_comparison("=")
    __ne__ = create_where_comparison("!=")
    
    __pos__ = create_order("ASC")
    __neg__ = create_order("DESC")


class Property(Queryable):
    default_sqltypes = {
        int: "INT",
        str: "VARCHAR",
        float: "DOUBLE PRECISION",
        bool: "BOOL",
        datetime.datetime: "TIMESTAMP"  # but consider perhaps amount of milliseconds since UNIX epoch
    }
    
    def __init__(self, typ, sql_type: str =None, constraint: types.FunctionType = None, sql_extra: str = "", 
                 required: bool = True, json: bool = True):
        if sql_type is None:
            sql_type = Property.default_sqltypes[typ]
        self.type = typ
        self.sql_type = sql_type
        self.constraint = constraint
        self.sql_extra = sql_extra
        self.required = required
        self.json = json
        self.name = None  # Set by the metaclass
        self.dataname = None  # Idem, where to find the actual stored data inside an object
        self.cls = None  # Idem
    
    def sql_def(self):
        return "\t" + self.name + " " + self.type_sql_def()
    
    def type_sql_def(self):
        return self.sql_type + (" " + self.sql_extra if self.sql_extra != "" else "") + (" NOT NULL" if self.required else "")
    
    def __str__(self):
        return self.cls._table_name + "." + self.name
    

class Key(Queryable):
    """
    A reference to other properties that define the key of this object.
    """
    def __init__(self, *props):
        self.props = props
        self.single_prop = None
    
    def __postinit__(self):
        newprops = []
        for p in self.props:
            if isinstance(p, Reference):
                newprops.extend(p.props)
                assert len(p.props) >= 1
            else:
                newprops.append(p)
        self.props = newprops
        assert len(self.props) >= 1
        if len(self.props) == 1:
            self.single_prop = self.props[0]
            self.__class__ = SingleKey

    def referencing_props(self):
        yield from self.props
    
    def sql_constraint(self) -> str:
        """Returns the SQL needed to define the PRIMARY KEY constraint."""
        return "\tPRIMARY KEY " + str(self)
    
    def __str__(self):
        return "({keys})".format(keys=", ".join([p.name for p in self.referencing_props()]))
    
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return tuple([obj.__dict__[p.dataname] for p in self.referencing_props()])
    
    def __set__(self, obj, val):
        if obj is not None:
            for (i, p) in enumerate(self.referencing_props()):
                if p.constraint is not None and not p.constraint(val):
                    raise PropertyConstraintFail(obj, p.name)
                obj.__dict__[p.dataname] = val[i]
    
    def __delete__(self, obj):
        pass  # ?

class SingleKey(Key):
    """Version of Key with only one property.
    (Don't directly use this, it will be automatic.)
    """
    
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return obj.__dict__[self.single_prop.dataname]
    
    def __set__(self, obj, val):
        if obj is not None:
            if self.single_prop.constraint is not None and not self.single_prop.constraint(val):
                raise PropertyConstraintFail(obj, single_prop.name)
            obj.__dict__[self.single_prop.dataname] = val
    
    def __delete__(self, obj):
        pass  # ?

class KeyProperty(SingleKey, Property):
    """
    A specifically created property to be used as a key.
    Type in postgres is SERIAL.
    """
    def __init__(self):
        Property.__init__(self, int, sql_type="SERIAL", required=False)
        self.single_prop = self
    
    def __postinit__(self):
        pass
    
    def referencing_props(self):
        yield self
        
    def sql_constraint(self) -> str:
        return "\tPRIMARY KEY (" + self.name + ")"
    
    __str__ = Property.__str__
        

class Reference(Queryable):
    """A reference to another Entity type."""
    
    def __init__(self, ref: MetaEntity):
        self.ref = ref
        self.ref_props = list(ref.key.referencing_props())
        assert len(self.ref_props) >= 1
        self.props = []
        self.single_prop = None
        self.name = None  # Set by metaclass
    
    @classmethod
    def single_upgrade(cls):
        return SingleReference
    
    def __postinit__(self):  # called by metaclass
        for rp in self.ref_props:
            p = Property(rp.type, rp.sql_type if not rp.sql_type == "SERIAL" else "INT")
            p.cls = rp.cls
            p.name = self.name + "_" + rp.name
            p.dataname = self.name + "_" + rp.dataname
            self.props.append(p)
        assert len(self.props) >= 1
        if len(self.props) == 1:
            self.single_prop = self.props[0]
            self.__class__ = self.single_upgrade()
    
    def sql_constraint(self) -> str:
        """Will only generate the SQL constraint. The metaclass will take care of the properties."""
        return "\tFOREIGN KEY ({own_props}) REFERENCES {ref_name}".format(
            own_props=", ".join([p.name for p in self.props]),
            ref_name=self.ref._table_name,
        )
    
    def __str__(self):
        return "(" + ", ".join([str(p) for p in self.props]) + ")"
    
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return tuple([obj.__dict__[p.dataname] for p in self.props])
    
    def __set__(self, obj, val):
        if obj is not None:
            for (i, p) in enumerate(self.props):
                obj.__dict__[p.dataname] = val[i]
    
    def __delete__(self, obj):
        pass  # ?

class RTReference(Reference):
    """Reference that automatically notifies the referencing object."""
    
    def __init__(self, ref: MetaEntity):
        """`ref` needs to be a subclass of `RTEntity`."""
        assert issubclass(ref, RTEntity)
        Reference.__init__(self, ref)
    
    @classmethod
    def single_upgrade(cls):
        return RTSingleReference
    
    def __set__(self, obj, val):
        if obj is not None:
            try:
                key = self.__get__(obj)
                if key in self.ref.cache:
                    self.ref.cache[key].remove_reference(obj)
            except KeyError:
                pass
            for (i, p) in enumerate(self.props):
                obj.__dict__[p.dataname] = val[i]
            # Update
            if val in self.ref.cache:
                self.ref.cache[val].new_reference(obj)


class RTSingleReference(RTReference):
    """Version of RTReference with only one referencing property.
    (Don't directly use this, it will be automatic.)
    """
    
    def __set__(self, obj, val):
        # References can not be constrained
        if obj is not None:
            try:
                key = obj.__dict__[self.single_prop.dataname]
                if key in self.ref.cache:
                    self.ref.cache[key].remove_reference(obj)
            except KeyError:
                pass
            obj.__dict__[self.single_prop.dataname] = val
            # Update
            if val in self.ref.cache:
                self.ref.cache[val].new_reference(obj)

class SingleReference(Reference):
    """Version of Reference with only one referencing property.
    (Don't directly use this, it will be automatic.)
    """
    
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return obj.__dict__[self.single_prop.dataname]
    
    def __set__(self, obj, val):
        # References can not be constrained
        if obj is not None:
            obj.__dict__[self.single_prop.dataname] = val
    
    def __delete__(self, obj):
        pass  # ?
    
    def __str__(self):
        return str(self.single_prop)


# This is a better way of doing things than python's native property
class ConstrainedProperty(Property):
    # No init, just hack around it by setting __class__
    
    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return obj.__dict__[self.dataname]
    
    def __set__(self, obj, val):
        if obj is not None:
            if not self.constraint(val):
                raise PropertyConstraintFail(obj, self.name)
            obj.__dict__[self.dataname] = val
    
    def __delete__(self, obj):
        pass  # ?


class MetaEntity(type):
    """Metaclass for `Entity`. This does a whole lot of stuff you should not care about
    as user of this library. If you do want to know how it works I suggest you read the code.
    """
    
    @classmethod
    def __prepare__(self, name, bases):
        # Thanks to http://stackoverflow.com/a/27113652/2678118
        return collections.OrderedDict()

    def __new__(self, name, bases, dct):
        ordered_props = [k for (k, v) in dct.items()
                if isinstance(v, Property) and not k == "key"]
        
        ordered_refs = [k for (k, v) in dct.items()
                if isinstance(v, Reference)]
        
        if not("__no_meta__" in dct and dct["__no_meta__"] == True):
            props = []
            
            init_properties = []
            json_props = []
            for k in ordered_props:
                p = dct[k]
                # Set some stuff of properties that are not known at creation time
                p.name = k
                props.append(p)
                if p.json:
                    json_props.append(p)
                
                if p.constraint is not None:
                    p.dataname = "_data_" + p.name
                    p.__class__ = ConstrainedProperty  # woohoo HACK
                    init_properties.append((p,True))
                else:
                    p.dataname = p.name
                    init_properties.append((p,False))
                        
            dct["_props"] = props
            dct["_json_props"] = json_props
            
            refs = []
            init_ref_properties = []
            init_raw_ref_properties = []
            for k in ordered_refs:
                r = dct[k]
                r.name = k
                r.__postinit__()
                refs.append(r)
                props.extend(r.props)
                init_raw_ref_properties.extend(r.props)
                init_ref_properties.append(r)
                
            dct["_refs"] = refs
            
            def __metainit__(obj, db_args=None, **kwargs):
                if db_args is not None:
                    # Init from a simple list/tuple
                    obj.in_db = True
                    start = 0
                    for (i, (p, constrained)) in enumerate(init_properties):
                        val = db_args[i]
                        if constrained and (not p.constraint(val)):
                            raise PropertyConstraintFail(obj, p.name)
                        obj.__dict__[p.dataname] = val
                    for (i, p) in enumerate(init_raw_ref_properties, len(init_properties)):
                        obj.__dict__[p.dataname] = db_args[i]
                else:
                    obj.in_db = False
                    for (p, constrained) in init_properties:
                        val = None
                        try:
                            val = kwargs[p.name]
                        except KeyError as e:
                            if p.required:
                                raise e
                            else:
                                val = None
                        if constrained and (not p.constraint(val)):
                            raise PropertyConstraintFail(obj, p.name)
                        obj.__dict__[p.dataname] = val
                    for r in init_ref_properties:
                        r.__set__(obj, kwargs[r.name])
                obj.check()
                    
            dct["__metainit__"] = __metainit__
            
            assert "key" in dct, "Each class must have a key"
            the_key = dct["key"]
            the_key.__postinit__()
            dct["_incomplete"] = isinstance(the_key, KeyProperty)
            
            dct["_complete_props"] = [p for p in props if not isinstance(p, KeyProperty)]
            
            dct["_table_name"] = "table_" + name
        
            cls = type.__new__(self, name, bases, dct)
            
            for p in props:
                p.cls = cls
            
            cls._create_table_command = CreateTable(cls).to_raw()
            cls._drop_table_command = DropTable(cls).to_raw()
            if cls._incomplete:
                cls._insert_command = Insert(cls, returning=cls.key).to_raw()
            else:
                cls._insert_command = Insert(cls).to_raw()
            cls._update_command = Update(cls).to_raw()
            cls._delete_command = Delete(cls).to_raw()
            cls._find_by_key_query = Select(cls, [cls.key == Field("key")])
            
            # FANCYYYY
            cls.cache = weakref.WeakValueDictionary()
            
        else:
            cls = type.__new__(self, name, bases, dct)
        return cls
    
    def __call__(self, *args, **kwargs):
        inst = super(MetaEntity, self).__call__(*args, **kwargs)
        if inst.key is not None:
            if inst.key in self.cache:
                # Replacing by cached entry
                return self.cache[inst.key]
            else:
                self.cache[inst.key] = inst
        return inst
    

class Entity(metaclass=MetaEntity):
    """Central class for an Entity."""
    
    __no_meta__ = True
    
    def __init__(self, *args, **kwargs):
        self.__metainit__(*args, **kwargs)
    
    async def insert(self, db: Database):
        """Insert in database."""
        
        if self.key is None:
            assert type(self)._incomplete
            await self._simple_insert(db)
            assert self.key is not None
            assert self.key not in type(self).cache
            type(self).cache[self.key] = self
        else:
            await self._simple_insert(db)
    
    async def _simple_insert(self, db: Database):
        self.check()
        assert not self.in_db
        cls = type(self)
        dct = {}
        for p in self._complete_props:
            dct[p.name] = self.__dict__[p.dataname]
        insert = cls._insert_command.with_data(**dct)
        if cls._incomplete:
            result = await insert.raw(db)
            self.__dict__[cls.key.dataname] = result[0]
        else:
            await insert.exec(db)
        self.in_db = True
    
    async def update(self, db):
        """Update object in the database."""
        
        self.check()
        assert self.in_db
        dct = {}
        for p in self._complete_props:
            dct[p.name] = self.__dict__[p.dataname]
        if type(self)._incomplete:
            dct[type(self).key.name] = self.__dict__[type(self).key.dataname]
        await type(self)._update_command.with_data(**dct).exec(db)
    
    
    async def delete(self, db):
        """Delete object from the database."""
        
        assert self.in_db
        dct = {}
        for p in type(self).key.referencing_props():
            dct[p.name] = self.__dict__[p.dataname]
        await type(self)._delete_command.with_data(**dct).exec(db)
        self.in_db = False
    
    
    constraint = None
    """
    object-wide constraint is checked at three times:
        - `__init__`
        - `insert`
        - `update`
        - + manual calling of check
    """
    
    def check(self):
        """Check object-wide constraint."""
        if self.constraint is not None:
            if not self.constraint():
                raise ObjectConstraintFail(self)

    @classmethod
    def raw(cls: MetaEntity, text: str) -> RawSql:
        """Return a RawSql where the results will be interpreted as objects of `cls`."""
        return RawSql(text, cls)
    
    @classmethod
    def get(cls: MetaEntity, *where_clauses: list) -> Sql:
        return Select(cls, where_clauses)
    
    @classmethod
    async def find_by_key(cls: MetaEntity, key, db: Database) -> "cls":
        """Works different from `get`, as it will immediatly return the object"""
        try:
            return cls.cache[key]
        except KeyError:
            return await super(RTEntity, cls).find_by_key(key, db)
    
    def to_json(self) -> str:
        return json.dumps(self.json_repr())
    
    def json_repr(self) -> dict:
        """Returns a dictionary of all properties that don't contain `json = False`.
        When overriding this method, you can return anything you want as long as it is convertible
        to JSON.
        """
        
        d = {}
        for p in self._json_props:
            d[p.name] = self.__dict__[p.dataname]
        return d
    
    def __eq__(self, other):
        return type(self) == type(other) and self.key == other.key
    
    def __hash__(self):
        return hash(type(self)) + hash(self.key)
     

class Listener:
    """Interface for a listener to be used with `RTEntity`. Main use is documentation,
    not functionality.
    
    Most implementations will want to define a `set` of objects they are 
    listening to (*listenees*).
    """
    def _add_listenee(self, obj: RTEntity):
        """Add from listenees set.
        (This method has an underscore to discourage directly calling it. You should
        instead use the methods in `RTEntity`.)
        """
    
    def _remove_listenee(self, obj: RTEntity):
        """Remove from listenees set.
        (This method has an underscore to discourage directly calling it. You should
        instead use the methods in `RTEntity`.)
        """
    
    def update(self, obj: RTEntity):
        """Handle updates to the object."""
    
    def delete(self, o: RTEntity):
        """Handle deletions of the object."""
    
    def new_reference(self, obj: RTEntity, ref_obj: Entity):
        """Handle a new reference from `ref_obj` to `obj`. `ref_obj` does not have to be a
        `RTEntity`.
        """
        
    def remove_reference(self, obj: RTEntity, ref_obj: Entity):
        """Handle the removal of a reference from `ref_obj` to `obj`. `ref_obj` does not 
        have to be a `RTEntity`.
        """
    

# NOTE: Be careful with changing the key as it will fuck with caching
class RTEntity(Entity):
    """Subclass of Entity that sends live updates!
    Listeners should follow the interface of `Listener`.
    """
    __no_meta__ = True
    
    def __init__(self, *args, **kwargs):
        self._listeners = set()
        super(RTEntity, self).__init__(*args, **kwargs)
    
    async def update(self, db: Database):
        await super(RTEntity, self).update(db)
        for l in self._listeners:
            l.update(self)
    
    def send_update(self, db):
        """To manually send messages to all listeners. Won't save to database."""
        for l in self._listeners:
            l.update(self)
    
    async def delete(self, db):
        await super(RTEntity, self).delete(db)
        for l in self._listeners:
            l.delete(self)
            l._remove_listenee(self)
    
    def new_reference(self, ref_obj):
        for l in self._listeners:
            l.new_reference(self, ref_obj)
    
    def remove_reference(self, ref_obj):
        for l in self._listeners:
            l.remove_reference(self, ref_obj)
            # TODO perhaps a problem with deleting?
    
    def add_listener(self, l: Listener):
        """Add listeners to this object."""
        self._listeners.add(l)
        l._add_listenee(self)
    
    def remove_listener(self, l: Listener):
        if l in self._listeners:
            self._listeners.remove(l)
            l._remove_listenee(self)
    
    def remove_all_listeners(self, l: Listener):
        for l in self._listeners:
            self._listeners.remove(l)
            l._remove_listenee(self)


