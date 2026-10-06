from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("books/", views.book_list, name="book_list"),
    path("books/add/", views.book_create, name="book_create"),
    path("books/<str:book_id>/edit/", views.book_edit, name="book_edit"),
    path("books/<str:book_id>/delete/", views.book_delete, name="book_delete"),
    path("books/<str:book_id>/status/", views.book_status, name="book_status"),
]
