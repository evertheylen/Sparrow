
from .util import *
from .sql import *


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
        
    def info(self):
        """Print all sql statements."""
        for s in self.all_sql_statements():
            print(str(s))
            print("\n----------------\n")
