from django.http import JsonResponse
from .data_processing.data_cleaner import DataCleaner
from .data_processing.data_loader import load_data

def upload_data(request):
    if request.method == 'POST':
        file = request.FILES['file']
        df = load_data(file)
        cleaner = DataCleaner(df)
        cleaned_df = cleaner.clean()
        return JsonResponse({'status': "Data Cleaned Succesfully"})