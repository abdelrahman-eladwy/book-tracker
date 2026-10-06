from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from books import db


class Command(BaseCommand):
    help = "Verify that Django can connect to MongoDB."

    def handle(self, *args, **options):
        try:
            client = db.get_client()
            client.admin.command("ping")
            version = client.server_info()["version"]
            count = db.books_collection().count_documents({})
        except PyMongoError as exc:
            raise CommandError(f"Could not connect to MongoDB: {exc}")

        self.stdout.write(self.style.SUCCESS("Connected to MongoDB."))
        self.stdout.write(f"  Server version : {version}")
        self.stdout.write(f"  Database       : {settings.MONGODB_DATABASE}")
        self.stdout.write(f"  Books stored   : {count}")
