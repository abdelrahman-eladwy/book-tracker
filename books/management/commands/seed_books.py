from django.core.management.base import BaseCommand

from books import db

SAMPLE_BOOKS = [
    {"title": "Clean Code", "author": "Robert C. Martin", "category": "Programming", "status": db.STATUS_COMPLETED},
    {"title": "Fluent Python", "author": "Luciano Ramalho", "category": "Programming", "status": db.STATUS_READING},
    {"title": "Atomic Habits", "author": "James Clear", "category": "Self-help", "status": db.STATUS_COMPLETED},
    {"title": "Dune", "author": "Frank Herbert", "category": "Science Fiction", "status": db.STATUS_READING},
    {"title": "The Pragmatic Programmer", "author": "Andrew Hunt & David Thomas", "category": "Programming", "status": db.STATUS_WANT_TO_READ},
    {"title": "Sapiens", "author": "Yuval Noah Harari", "category": "History", "status": db.STATUS_WANT_TO_READ},
]


class Command(BaseCommand):
    help = "Insert sample books into MongoDB (only if the books collection is empty)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Insert the samples even if books already exist.")

    def handle(self, *args, **options):
        existing = db.books_collection().count_documents({})
        if existing and not options["force"]:
            self.stdout.write(f"The books collection already has {existing} book(s). Use --force to add samples anyway.")
            return

        for book in SAMPLE_BOOKS:
            db.create_book(book)
        self.stdout.write(self.style.SUCCESS(f"Inserted {len(SAMPLE_BOOKS)} sample books."))
