from django.urls import include, path

urlpatterns = [
    path("", include("books.urls")),
]
