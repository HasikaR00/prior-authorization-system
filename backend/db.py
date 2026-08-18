import os
import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
PA_SYSTEM_DB = os.getenv("DB_NAME", "pa_system")
PA_KB_DB = os.getenv("PA_KB_NAME", "pa_kb")

SYSTEM_DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": PA_SYSTEM_DB,
    "charset": "utf8mb4",
    "autocommit": True
}

KB_DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": PA_KB_DB,
    "charset": "utf8mb4",
    "autocommit": True
}

def get_system_db():
    return pymysql.connect(**SYSTEM_DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)

def get_kb_db():
    return pymysql.connect(**KB_DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
