
import json
from collections import OrderedDict

from .util import *
from .sql import *
from .entity import *

# Helpers
# =======

def indent(s, i=4, code=True):
    lines = s.split("\n")
    prefix = "::\n\n" if code else ""
    return prefix + "\n".join([(" "*i) + l for l in lines])

def inline(s):
    return "``" + str(s) + "``"

# Central class
# =============

class SparrowModel:
    """
    The central class that keeps everything together.
    """
    def __init__(self, ioloop, db_args, classes, debug=True, db=None):
        self.ioloop = ioloop
        if db is not None:
            self.db = db
        else:
            self.db = Database(ioloop, **db_args)
        self.classes = classes
        self.debug = debug
        
        # Keeps track of all SQL statements
        self.sql_statements = set()
        
    def add_sql_statement(self, stat: Sql):
        """Add an `Sql` that you want printed on `info()`."""
        self.sql_statements.add(stat)
    
    def all_sql_statements(self):
        """Return all `Sql` statements that have been added or are automatically generated."""
        for c in self.classes:
            yield from self.sql_for_class(c)
        yield from self.sql_statements
    
    def sql_for_class(self, cls):
        for e in cls._enums:
            yield e._create_type_command
        yield cls._create_table_command
        yield cls._drop_table_command
        yield cls._insert_command
        yield cls._update_command
        yield cls._delete_command
        yield cls._find_by_key_query
    
    async def install(self):
        """Set up database, only once for each "install" of the model"""
        for c in self.classes:
            for e in c._enums:
                await e._create_type_command.exec(self.db)
            await c._create_table_command.exec(self.db)
            
    async def uninstall(self):
        """Very brutal operation, drops all tables."""
        for c in self.classes:
            await c._drop_table_command.exec(self.db)
            for e in c._enums:
                await e._drop_type_command.exec(self.db)
        
    def sql_info(self):
        """Print all SQL statements (as organized as possible)."""
        print("\n")
        print("All (logged) SQL statements")
        print("===========================")
        for c in self.classes:
            s = "Statements for object type ``{}``".format(c.__name__)
            print("\n\n" + s)
            print("-"*len(s), end="\n\n")
            for s in self.sql_for_class(c):
                print(str(s), end="\n\n")
        
        # TODO more categorizing
        print("Uncategorized statements")
        print("------------------------\n")
        for s in self.sql_statements:
            print(str(s), end="\n\n")
    
    def json_info(self):
        """Print all JSON info (as organized as possible). Send this to frontend devs."""
        print("\n")
        print("Automatically generated JSON definitions")
        print("========================================")
        for c in self.classes:
            s = "Definition for object type ``{}``".format(c.__name__)
            print("\n\n" + s)
            print("-"*len(s), end="\n\n")
            
            possible_for = False
            
            if c.json_repr is Entity.json_repr:
                d = OrderedDict()
                for p in c._json_props:
                    d[p.name] = str(p.type)
                    
                print(indent(json.dumps(d, indent=4)))
            else:
                print("Definition is custom!")
                if hasattr(c.json_repr, "__doc__"):
                    print("The documentation says:\n\n" + indent(c.json_repr.__doc__, code=False))
                possible_for = True
            
            print("\nKey properties are (might not be in definition): " + ", ".join([
                inline(p.name) for p in c.key.referencing_props()]))
            
            if isinstance(c.key, Key) and not isinstance(c.key, Property):
                refs = []
                for p in c.key.orig_props:
                    if isinstance(p, Reference) or isinstance(p, SingleReference):
                        refs.append(p)
                
                if possible_for and len(refs) > 0:
                    assert len(refs) == 1, "Multiple references in key not yet supported"
                    print('\nThere might be a "for" attribute needed when getting:\n')
                    ref = refs[0]
                    fordct = OrderedDict([("what", ref.ref.__name__)])
                    for p in ref.ref.key.referencing_props():
                        fordct[p.name] = str(p.type)
                    print(indent('"for": ' + json.dumps(fordct, indent=4)))
        print("")
                    


