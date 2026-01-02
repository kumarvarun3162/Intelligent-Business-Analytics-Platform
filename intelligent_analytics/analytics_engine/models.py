from django.db import models

# Create your models here.
class Dataset(models.Model):
    name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='datasets/')

    def __str__(self):
        return self.name 


class CleanedData(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
