"""
MongoDB access for the books app.

A single MongoClient is created lazily on first use. Because it is created
inside each Gunicorn worker (after the fork), every worker gets its own
connection pool, which is what PyMongo recommends.
"""
from datetime import datetime, timezone
from functools import lru_cache

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from pymongo import DESCENDING, MongoClient

STATUS_WANT_TO_READ = "Want to Read"
STATUS_READING = "Reading"
STATUS_COMPLETED = "Completed"
STATUSES = [STATUS_WANT_TO_READ, STATUS_READING, STATUS_COMPLETED]


@lru_cache(maxsize=1)
def get_client():
    return MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)


def books_collection():
    return get_client()[settings.MONGODB_DATABASE]["books"]


def to_book(doc):
    """Convert a MongoDB document into a dict that templates can use
    (templates cannot access keys that start with an underscore)."""
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "author": doc.get("author", ""),
        "category": doc.get("category", ""),
        "status": doc.get("status", STATUS_WANT_TO_READ),
        "created_date": doc.get("created_date"),
    }


def parse_id(book_id):
    """Return an ObjectId, or None if the string is not a valid id."""
    try:
        return ObjectId(book_id)
    except (InvalidId, TypeError):
        return None


# --- Queries ----------------------------------------------------------------

def list_books():
    return [to_book(doc) for doc in books_collection().find().sort("created_date", DESCENDING)]


def get_book(book_id):
    oid = parse_id(book_id)
    if oid is None:
        return None
    doc = books_collection().find_one({"_id": oid})
    return to_book(doc) if doc else None


def get_stats():
    books = books_collection()
    return {
        "total": books.count_documents({}),
        "completed": books.count_documents({"status": STATUS_COMPLETED}),
        "reading": books.count_documents({"status": STATUS_READING}),
    }


# --- Writes -----------------------------------------------------------------

def create_book(data):
    doc = {
        "title": data["title"],
        "author": data["author"],
        "category": data["category"],
        "status": data["status"],
        "created_date": datetime.now(timezone.utc),
    }
    return str(books_collection().insert_one(doc).inserted_id)


def update_book(book_id, data):
    fields = {key: data[key] for key in ("title", "author", "category", "status")}
    result = books_collection().update_one({"_id": parse_id(book_id)}, {"$set": fields})
    return result.matched_count == 1


def set_status(book_id, status):
    result = books_collection().update_one({"_id": parse_id(book_id)}, {"$set": {"status": status}})
    return result.matched_count == 1


def delete_book(book_id):
    result = books_collection().delete_one({"_id": parse_id(book_id)})
    return result.deleted_count == 1
