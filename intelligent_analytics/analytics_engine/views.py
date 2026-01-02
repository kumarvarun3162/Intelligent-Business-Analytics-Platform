from django.http import JsonResponse
from .data_processing.data_loader import load_data
from .data_processing.data_cleaner import DataCleaner
import json
from .models import Dataset, CleanedData

def upload_data(request):
    if request.method == 'POST':
        file = request.FILES['file']

        dataset = Dataset.objects.create(
            name=file.name,
            file=file
        )


        df = load_data(dataset.file.path)
        cleaner = DataCleaner(df)
        cleaned_df = cleaner.clean()

        cleaned_json = cleaned_df.to_dict(orient='records')

        CleanedData.objects.create(
            dataset=dataset,
            data=cleaned_json
        )

        return JsonResponse({"status": "Data stored successfully"})
