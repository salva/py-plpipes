from plpipes.config import cfg
import logging
import plpipes.plugin

_driver_registry = plpipes.plugin.Registry("db_driver", "plpipes.database.driver.plugin")

_db_registry = {}

def lookup(db=None):
    if db is None:
        db = "work"
    if db not in _db_registry:
        _db_registry[db] = _init_driver(db)
    return _db_registry[db]

def _init_driver(name):
    drv_cfg = cfg.cd(f"db.instance.{name}")
    driver_name = drv_cfg.get("driver", "sqlite")
    logging.debug(f"Initializing database instance {name} using driver {driver_name}")
    driver = _driver_registry.lookup(driver_name)
    return driver(name, drv_cfg)

def begin(db=None):
    return lookup(db).begin()

def query_first(sql, parameters=None, db=None, backend=None, **kws):
    with begin(db) as txn:
        return txn.query_first(sql, parameters, backend, **kws)

def query_first_value(sql, parameters=None, db=None, backend="tuple", **kws):
    with begin(db) as txn:
        return txn.query_first_value(sql, parameters, backend, **kws)

def query(sql, parameters=None, db=None, backend=None, **kws):
    with begin(db) as txn:
        return txn.query(sql, parameters, backend, **kws)

def execute(sql, parameters=None, db=None):
    with begin(db) as txn:
        return txn.execute(sql, parameters)

def create_table(table_name, sql_or_df, parameters=None, db=None, if_exists="replace", **kws):
    logging.debug(f"create table {table_name}")
    with begin(db) as txn:
        return txn.create_table(table_name, sql_or_df, parameters, if_exists, **kws)

def create_view(view_name, sql, parameters=None, db=None, if_exists="replace", **kws):
    with begin(db) as txn:
        return txn.create_view(view_name, sql, parameters, if_exists, **kws)

def read_table(table_name, db=None, backend=None, **kws):
    with begin(db) as txn:
        return txn.read_table(table_name, backend, **kws)

def execute_script(sql_script, db=None):
    with begin(db) as txn:
        return txn.execute_script(sql_script)

def query_chunked(sql, parameters=None, db=None, backend=None, **kws):
    with begin(db) as txn:
        for df in txn.query_chunked(sql, parameters, backend, **kws):
            yield df

def query_group(sql, parameters=None, db=None, by=None, backend=None, **kws):
    with begin(db) as txn:
        return txn.query_group(sql, parameters, by, backend, **kws)

def copy_table(from_table_name, to_table_name=None,
               from_db=None, to_db=None, db=None,
               if_exists="replace", **kws):
    if to_table_name is None:
        to_table_name = from_table_name

    from_driver = lookup(db if from_db is None else from_db)
    to_driver = lookup(db if to_db is None else to_db)

    with from_driver.begin() as from_txn:
        logging.debug(f"copy table {from_table_name} from db {from_db} as {to_table_name} in db {to_db}")
        if from_driver is to_driver:
            from_txn.copy_table(from_table_name, to_table_name, if_exists=if_exists, **kws)
        else:
            with to_driver.begin() as to_txn:
                if if_exists == "replace":
                    to_txn.drop_table(to_table_name)
                first = True
                for df in from_txn.read_table_chunked(from_table_name, **kws):
                    if first:
                        to_txn.create_table(to_table_name, df, if_exists=if_exists)
                        first = False
                    else:
                        to_txn.create_table(to_table_name, df, if_exists="append")

_key_dir_unpacked = {
    '>' : (True , True ), # Ascending, Strict
    '>=': (True , False),
    '<' : (False, True ),
    '<=': (False, False)
}

def update_table(from_table_name, to_table_name=None,
                 from_db=None, to_db=None, db=None,
                 key=None, key_dir=">=", **kws):
    if to_table_name is None:
        to_table_name = from_table_name

    from_driver = lookup(db if from_db is None else from_db)
    to_driver = lookup(db if to_db is None else to_db)

    try:
        ascending, strict = _key_dir_unpacked[key_dir]
    except KeyError:
        raise ValueError(f"Invalid key_dir value {key_dir}")

    with from_driver.begin() as from_txn:
        logging.debug(f"Updating table {from_table_name} from db {from_db} as {to_table_name} in db {to_db}")
        with to_driver.begin() as to_txn:
            if to_driver._engine.dialect.has_table(to_txn._conn, to_table_name):
                count = to_txn.query_first_value(f"select count(*) from (select {key} from {to_table_name} limit 1) as t")
                if count > 0:
                    top_func = "max" if ascending else "min"
                    # FIXME: escape key identifier properly!
                    top = to_txn.query_first_value(f"select {top_func}({key}) from {to_table_name}")
                    if not strict:
                        # we don't know if the we have all the rows with key=top, so we have to delete any previous row!
                        to_txn.execute(f"delete from {to_table_name} where {key} = :top", parameters={'top': top})
                    for df in from_txn.query_chunked(f"select * from {from_table_name} where {key} {key_dir} :top",
                                                     parameters={'top': top}):
                        to_txn.create_table(to_table_name, df, if_exists="append")
                    return
            # No table, or table is empty

            for df in from_txn.read_table_chunked(from_table_name):
                to_txn.create_table(to_table_name, df, if_exists="append")


def engine(db=None):
    return lookup(db).engine()

def load_backend(name, db=None):
    lookup(db).load_backend(name)
