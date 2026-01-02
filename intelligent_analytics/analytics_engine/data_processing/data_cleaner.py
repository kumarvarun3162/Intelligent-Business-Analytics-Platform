class DataCleaner:
    def __init__(self,df):
        self.df = df
    
    def remove_duplicates(self):
        self.df.drop_duplicates(inplace = True)
    
    def handle_missing(self):
        self.df.fillna(method = 'ffill', inplace = True)

    def clean(self):
        self.remove_duplicates()
        self.handle_missing()
        return self.df