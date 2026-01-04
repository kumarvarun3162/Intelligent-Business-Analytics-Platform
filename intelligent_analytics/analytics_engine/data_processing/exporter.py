def export_for_powerbi(df):
    df.to_csv("powerbi_dataset.csv", index=False)
