from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from pymongo.errors import PyMongoError

from . import db
from .forms import BookForm, StatusForm

DB_ERROR = "Could not reach MongoDB. Check MONGODB_URI and that the server is running."


def get_book_or_404(book_id):
    book = db.get_book(book_id)
    if book is None:
        raise Http404("Book not found")
    return book


def home(request):
    try:
        stats = db.get_stats()
    except PyMongoError:
        messages.error(request, DB_ERROR)
        stats = None
    return render(request, "books/home.html", {"stats": stats})


def book_list(request):
    try:
        books = db.list_books()
    except PyMongoError:
        messages.error(request, DB_ERROR)
        books = []
    return render(request, "books/book_list.html", {"books": books, "statuses": db.STATUSES})


def book_create(request):
    form = BookForm(request.POST or None, initial={"status": db.STATUS_WANT_TO_READ})
    if request.method == "POST" and form.is_valid():
        db.create_book(form.cleaned_data)
        messages.success(request, f'Added "{form.cleaned_data["title"]}".')
        return redirect("book_list")
    return render(request, "books/book_form.html", {"form": form, "is_edit": False})


def book_edit(request, book_id):
    book = get_book_or_404(book_id)
    form = BookForm(request.POST or None, initial=book)
    if request.method == "POST" and form.is_valid():
        db.update_book(book_id, form.cleaned_data)
        messages.success(request, f'Updated "{form.cleaned_data["title"]}".')
        return redirect("book_list")
    return render(request, "books/book_form.html", {"form": form, "is_edit": True, "book": book})


def book_delete(request, book_id):
    book = get_book_or_404(book_id)
    if request.method == "POST":
        db.delete_book(book_id)
        messages.success(request, f'Deleted "{book["title"]}".')
        return redirect("book_list")
    return render(request, "books/book_confirm_delete.html", {"book": book})


@require_POST
def book_status(request, book_id):
    book = get_book_or_404(book_id)
    form = StatusForm(request.POST)
    if form.is_valid():
        db.set_status(book_id, form.cleaned_data["status"])
        messages.success(request, f'"{book["title"]}" is now marked as {form.cleaned_data["status"]}.')
    else:
        messages.error(request, "Invalid status.")
    return redirect("book_list")
