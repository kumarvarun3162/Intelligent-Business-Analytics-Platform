from django.shortcuts import render
from .models import Dataset, CleanedData
from .data_processing.data_loader import load_data
from .data_processing.data_cleaner import DataCleaner

def upload_csv(request):
    message = ""

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")

        # 1. Save dataset info
        dataset = Dataset.objects.create(
            name=uploaded_file.name,
            file=uploaded_file
        )

        # 2. Load data using Pandas
        df = load_data(dataset.file.path)

        # 3. Clean data
        cleaner = DataCleaner(df)
        cleaned_df = cleaner.clean()

        # 4. Convert to JSON
        cleaned_json = cleaned_df.to_dict(orient="records")

        # 5. Store cleaned data in MySQL
        CleanedData.objects.create(
            dataset=dataset,
            data=cleaned_json
        )

        message = "File uploaded, cleaned, and stored successfully!"

    return render(request, "analytics_engine/upload.html", {
        "message": message
    })
