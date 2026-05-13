# Create a file: scripts/filter_year.py
import pandas as pd

# Load the full dataset
df = pd.read_csv('data/ungdc_1946-2022.csv')

# Filter for 1950
df_1980 = df[df['year'] == 1980]

# Save the filtered data
df_1980.to_csv('data/ungdc_1980.csv', index=False)

print(f"Found {len(df_1980)} speeches from 1980")
print("Countries:", df_1980['iso'].tolist())