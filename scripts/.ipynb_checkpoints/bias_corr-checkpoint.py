#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import pandas as pd
import numpy as np
import geopandas as gpd
from collections import defaultdict
import re
import shutil
import subprocess
import sys


# ### Inputs

# In[2]:


# Inputs
# Directory with bias corrected csv
#bc_dir= '/work/comphyd_lab/users/paul.coderre/Data/'
bc_dir= '/work/comphyd_lab/users/paul.coderre/Data/'

# Define directory containing non bias corrected forcings
forcing_dir= '../../official_forcings/'

# Read shapefile path
shapefile_path= '../../../SMM_Models/hype/geospacial/shapefiles/modified_shapefiles/Modified_SMMcat.shp'

# Directory contiaining HYPE
model_dir= '../../model_v10_1/'

hype_executable = './hype' 

# Number of str seperated by _ at the end of the filenames to make them unique
number_of_fields= 6


# In[3]:


# Access the environment variable set by the shell script
directory_index = os.getenv("SLURM_ARRAY_TASK_ID")
if len(sys.argv) != 2:
    print("Usage: python run_easymore.py <index>")
    sys.exit(1)

run_number = int(sys.argv[1])
print(f'Run number= {run_number}')

# run_number=1


# ### Setup

# In[4]:



# In[5]:


shapefile= gpd.read_file(shapefile_path)


# In[6]:


# Read shapefile
shapefile= gpd.read_file(shapefile_path)

# Convert ID cols to int
shapefile['hru_nhm'] = shapefile['hru_nhm'].astype(int)
shapefile['seg_nhm'] = shapefile['seg_nhm'].astype(int)

# Create dictionary for IDs
id_dict = dict(zip(shapefile['hru_nhm'], shapefile['seg_nhm']))

# Check number of entries in the ID dict
id_dict_len = len(id_dict)


# In[7]:


# Initialize list of all bias corrected csv files 
bc_csv_files = []

# Loop through all files in the directory and find each bias correction file
for filename in os.listdir(bc_dir):
    if filename.endswith('.csv') and filename.startswith('BC'):
        bc_csv_files.append(filename)

# Optional: sort the list
bc_csv_files.sort()


# In[8]:


# Initialize list of unique members
unique_suffixes = set()

# Find unique member identifiers
for filename in bc_csv_files:
    parts = filename.replace('.csv', '').split('_')
    if len(parts) >= number_of_fields:
        suffix = '_'.join(parts[-number_of_fields:])
        unique_suffixes.add(suffix)

# Convert to sorted list for readability
unique_suffix_list = sorted(list(unique_suffixes))
print(len(unique_suffix_list))


# In[9]:


# Dictionary to store filepaths grouped by variable type and suffix
grouped_files = defaultdict(lambda: {'Pr': [], 'TMax': [], 'TMin': []})

# Group forcing files for each ensemble member
for suffix in unique_suffixes:
    for filename in bc_csv_files:
        if filename.endswith(suffix + '.csv'):
            full_path = os.path.join(bc_dir, filename)
            if 'Pr' in filename:
                grouped_files[suffix]['Pr'].append(full_path)
            elif 'TMax' in filename:
                grouped_files[suffix]['TMax'].append(full_path)
            elif 'TMin' in filename:
                grouped_files[suffix]['TMin'].append(full_path)

# Example: print how many matches were found for each suffix
for suffix, files in grouped_files.items():
    print(f"\nSuffix: {suffix}")
    print(f"  Pr: {len(files['Pr'])} file(s)")
    print(f"  TMax: {len(files['TMax'])} file(s)")
    print(f"  TMin: {len(files['TMin'])} file(s)")


# In[10]:


# Remove suffixes that don't have matching files for any variable type
filtered_grouped_files = {}

for suffix in list(grouped_files.keys()):
    pr_files = len(grouped_files[suffix]['Pr'])
    tmax_files = len(grouped_files[suffix]['TMax'])
    tmin_files = len(grouped_files[suffix]['TMin'])

    # Check if none of the file counts match id_dict_len
    if pr_files != id_dict_len and tmax_files != id_dict_len and tmin_files != id_dict_len:
        print(f"Removing suffix {suffix} because none of the variable types have matching files.")
    else:
        filtered_grouped_files[suffix] = grouped_files[suffix]

# Now, proceed with sorting and trimming to match the run_number
sorted_suffixes = sorted(filtered_grouped_files.keys())

print(f'New list of ensemble members is: {sorted_suffixes}')

# Ensure the run_number is within the bounds of the sorted suffixes
if run_number - 1 < 0 or run_number - 1 >= len(sorted_suffixes):
    print(f"Error: run_number {run_number} is out of range. There are {len(sorted_suffixes)} suffixes.")
    sys.exit(1)

# Get the suffix corresponding to the run_number (1-based index)
selected_suffix = sorted_suffixes[run_number - 1]
print(f"This run number applies to: {selected_suffix}")

# Filter grouped_files to only include the selected suffix
grouped_files = {selected_suffix: filtered_grouped_files[selected_suffix]}

# Example: print how many matches were found for each suffix after filtering
for suffix, files in grouped_files.items():
    print(f"\nSuffix: {suffix}")
    print(f"  Pr: {len(files['Pr'])} file(s)")
    print(f"  TMax: {len(files['TMax'])} file(s)")
    print(f"  TMin: {len(files['TMin'])} file(s)")


# ### Process

# In[11]:


# Define the function to check for invalid dates (Feb 29 or 30)
def is_invalid_date(date):
    return (date.month == 2 and date.day == 29) or (date.month == 2 and date.day == 30)


# In[12]:


# Process each ensemble member
for suffix, files in grouped_files.items():
    # Skip if all are empty
    if not any(files.values()):
        continue

    suffix_dir = f'./working_dir_{suffix}'
    results_dir = f'./results_{suffix}'
    
    # Create the directory if it doesn't exist
    os.makedirs(suffix_dir, exist_ok=True)

        # Create the directory if it doesn't exist
 #   os.makedirs(results_dir, exist_ok=True)

    # Copy all files from model_dir to the current suffix directory
    for filename in os.listdir(model_dir):
        model_file_path = os.path.join(model_dir, filename)
        if os.path.isfile(model_file_path):  # Only copy files, not directories
            shutil.copy(model_file_path, suffix_dir)

    print(f"Copied all files from {model_dir} to {suffix_dir}")
    print(f"\nProcessing group with suffix: {suffix}")

    # Iterate through variable types ['Pr', 'TMax', 'TMin']
    for var_type in ['Pr', 'TMax', 'TMin']:
        file_list = files.get(var_type, [])

        # Check if the number of files matches the length of id_dict
        if len(file_list) != id_dict_len:
            print(f"Warning: The number of files for {var_type} ({len(file_list)}) doesn't match the number of IDs in id_dict ({id_dict_len}) for group {suffix}. Skipping {var_type}.")
            continue

        merged_df = None
        for path in file_list:
            df = pd.read_csv(path, parse_dates=[0], index_col=0)

            match = re.search(r'(\d{4,})', os.path.basename(path))
            if match:
                unique_id = int(match.group(1))
            else:
                raise ValueError(f"Could not extract a unique ID from filename: {path}")

            df.rename(columns={df.columns[0]: unique_id}, inplace=True)

            if merged_df is None:
                merged_df = df
            else:
                if not merged_df.index.equals(df.index):
                    raise ValueError(f"Index mismatch in file: {path}")
                merged_df = merged_df.join(df)

        # Ensure index is datetime
        if not pd.api.types.is_datetime64_any_dtype(merged_df.index):
            merged_df.index = pd.to_datetime(merged_df.index)

        # Convert column headers to integers and map to seg_nhm
        merged_df.columns = merged_df.columns.astype(int)
        column_map = {col: id_dict.get(col, f"ID_{col}") for col in merged_df.columns}
        merged_df.rename(columns=column_map, inplace=True)

        # Remove Feb 29 and Feb 30 if present
        initial_len = len(merged_df)
        merged_df = merged_df[~merged_df.index.to_series().apply(is_invalid_date)]
        if len(merged_df) < initial_len:
            print(f"Removed {initial_len - len(merged_df)} invalid dates (Feb 29/30)")

        # Fill in missing dates
        min_date = merged_df.index.min()
        max_date = merged_df.index.max()
        expected_dates = pd.date_range(start=min_date, end=max_date, freq='D')

        missing_dates = expected_dates.difference(merged_df.index)
        if not missing_dates.empty:
            print(f"Adding {len(missing_dates)} missing dates to complete time series.")
            merged_df = merged_df.reindex(expected_dates)
        
          # Step 1: Convert strings like '0.0023+0i' to proper Python complex numbers
        def safe_to_complex(x):
            try:
                return complex(str(x).replace(" ", "").replace("+0i", "+0j").replace("i", "j"))
            except ValueError:
                return np.nan
        
        merged_df = merged_df.applymap(safe_to_complex)
        
        # Step 2: Strip imaginary parts (and warn if not zero)
        def check_and_strip_complex(x):
            if isinstance(x, complex):
                if x.imag != 0:
                    print(f"⚠️ Warning: Found complex number with non-zero imaginary part: {x}")
                return x.real
            return x
        
        merged_df = merged_df.applymap(check_and_strip_complex)

        merged_df = merged_df.astype(float)
        merged_df.fillna(0, inplace=True)

        # Remove values smaller than 0 to account for drizzle effect
        merged_df[merged_df < 1] = 0 

        # Save to correct file based on var_type
        if var_type == 'Pr':
            merged_df.to_csv(os.path.join(suffix_dir, 'Pobs.txt'), sep='\t', index_label='time')
            print(f"Saved {var_type} data to Pobs.txt")
        elif var_type == 'TMax':
            merged_df.to_csv(os.path.join(suffix_dir, 'TMAXobs.txt'), sep='\t', index_label='time')
            print(f"Saved {var_type} data to TMAXobs.txt")
        elif var_type == 'TMin':
            merged_df.to_csv(os.path.join(suffix_dir, 'TMINobs.txt'), sep='\t', index_label='time')
            print(f"Saved {var_type} data to TMINobs.txt")

        # --- Check and copy missing forcing files (Pobs, TMAXobs, TMINobs) ---
        for required_file in ['Pobs', 'TMAXobs', 'TMINobs', 'Tobs']:
            file_path = os.path.join(suffix_dir, f"{required_file}.txt")

            if not os.path.exists(file_path):
                print(f"{required_file}.txt is missing in {suffix_dir}. Looking for it in {forcing_dir}...")
                
                # Look for a match in forcing_dir
                found_match = False
                for forcing_file in os.listdir(forcing_dir):
                    if required_file in forcing_file and forcing_file.endswith('.txt'):
                        matching_file = forcing_file
                        source_path = os.path.join(forcing_dir, matching_file)
                        shutil.copy(source_path, file_path)  # Rename the file to the required filename
                        print(f"Copied {matching_file} to {file_path}")
                        found_match = True
                        break
                
                if not found_match:
                    print(f"Warning: {required_file}.txt not found in {forcing_dir}. Skipping group {suffix}.")

        # --- Run the HYPE model ---
        print("Running HYPE model...")
        try:
            subprocess.run(hype_executable, cwd=suffix_dir, check=True)
            print("HYPE program executed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error running HYPE program in {suffix_dir}:", e)
            continue

        # --- Check for output files starting with '00' ---
        hype_outputs = os.listdir(suffix_dir)
        matching_files = [file for file in hype_outputs if file.startswith("00") and file.endswith(".txt")]

        if matching_files:
            print(f"Found output files in {suffix_dir}: {matching_files}")
        else:
            print(f"No output files starting with '00' found in {suffix_dir}.")

        # # --- Copy output files to results_dir ---
        # for file in matching_files:
        #     source_path = os.path.join(suffix_dir, file)
        #     new_filename = f"{suffix}_{file}"
        #     destination_path = os.path.join(results_dir, new_filename)

        #     shutil.copy(source_path, destination_path)
        #     print(f"Copied {file} to {destination_path}")


# In[13]:


# # After all processing is done, remove the working directory
# if os.path.exists(working_dir_location):
#     shutil.rmtree(working_dir_location)
#     print(f"Deleted working directory: {working_dir_location}")


# In[ ]:




