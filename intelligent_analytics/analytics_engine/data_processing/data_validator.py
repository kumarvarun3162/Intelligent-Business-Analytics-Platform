class DataValidator:
    def __int__ (self,df):
        self.df = df
    
    def validate(self):
        return{
            'rows': len(self.df),
            'columns': list(self.df.columns),
            'missing_values': self.df.isnull().sum().to_dict()
        }