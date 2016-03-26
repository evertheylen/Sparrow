
import json
from collections import OrderedDict

from .util import *
from .sql import *
from .entity import *

# Central class
# =============

class SparrowModel:
    """
    The central class that keeps everything together.
    """
    def __init__(self, ioloop, db_args, classes, debug=True):
        self.ioloop = ioloop
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
            yield c._create_table_command
            yield c._drop_table_command
            yield c._insert_command
            yield c._update_command
            yield c._delete_command
            yield c._find_by_key_query
        yield from self.sql_statements
    
    async def install(self):
        """Set up database, only once for each "install" of the model"""
        for c in self.classes:
            await c._create_table_command.exec(self.db)
            
    async def uninstall(self):
        """Very brutal operation, drops all tables."""
        for c in self.classes:
            await c._drop_table_command.exec(self.db)
        
    def sql_info(self):
        """Print all sql statements."""
        for s in self.all_sql_statements():
            print(str(s))
            print("\n----------------\n")
    
    def json_info(self):
        print("Automatically generated JSON definitions")
        print("========================================")
        for c in self.classes:
            s = "Definition for object type '{}'".format(c.__name__)
            print("\n" + s)
            print("-"*len(s))
            d = OrderedDict()
            for p in c._json_props:
                d[p.name] = str(p.type)
                
            print(json.dumps(d, indent=4))
            
            print("\nKey properties are (might not be in definition): " + ", ".join([
                p.name for p in key.referencing_props()]))
            
            refs = []
            for p in c.key.props:
                if isinstance(c, Reference):
                    refs.append(p)
            
            if len(refs) > 0:
                assert len(refs) == 1, "Multiple references in key not yet supported"
                print("\nYou should also mention a 'for' attribute:")
                ref = refs[0]
                fordct = OrderedDict([("what", ref.ref.__name__)])
                for p in ref.ref.referencing_props():
                    fordct[p.name] = "<...>"
                print("for: " + json.dumps(fordct, indent=4))
                    


