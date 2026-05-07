import os

import mysql.connector


def get_db_config(include_database: bool = True):
    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "M@nu2425"),
    }
    if include_database:
        config["database"] = os.getenv("DB_NAME", "patrimonio_ideau_v2")
    return config


def get_connection():
    return mysql.connector.connect(**get_db_config(include_database=True))

