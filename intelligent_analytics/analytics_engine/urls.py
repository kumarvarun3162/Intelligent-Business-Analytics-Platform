from django.urls import path
from .views import upload_csv

urlpatterns = [
    path("upload/", upload_csv, name="upload_csv"),
]
