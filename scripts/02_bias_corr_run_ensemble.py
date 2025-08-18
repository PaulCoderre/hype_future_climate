import xarray as xr
import os
import pandas as pd
import cftime
import sys
import glob
import shutil
import subprocess
import re
import shutil
import sys
import geopandas as gpd

# Run options
perform_bias_corr =False
remove_drizzle= False

# Define the inputs
forcings_directory = '../../official_easymore'  # directory containing results from easymore
bias_corr_directory= '/work/comphyd_lab/users/paul.coderre/Data_2_compact/'
shapefile_path= '../../../SMM_Models/hype/geospatial/shapefiles/modified_shapefiles/Modified_SMMcat.shp'
model_directory = '../../model_v10_3'  # directory containing HYPE model files
hype_executable = './hype'  # command line argument to run HYPE
runs_per_script = 1
file_pattern = "*.nc"

print('Program Running')

# Get the current working directory
current_directory = os.getcwd()

# Access the environment variable set by the shell script
directory_index = os.getenv("SLURM_ARRAY_TASK_ID")
if len(sys.argv) != 2:
    print("Usage: python run_easymore.py <index>")
    sys.exit(1)

run_number = int(sys.argv[1])
print(f'Run number= {run_number}')

# debug
#run_number = 22

# Get a list of each directory in the specified directory
directory_list = sorted([d for d in os.listdir(forcings_directory) if os.path.isdir(os.path.join(forcings_directory, d))])
# Remove .ipynb_checkpoints from the list if present
if '.ipynb_checkpoints' in directory_list:
    directory_list.remove('.ipynb_checkpoints')
    
print(directory_list)

# Define ranges 
low_range = run_number * runs_per_script - runs_per_script
upper_range = run_number * runs_per_script

print(f'Run from {low_range} to {upper_range}')
    
# Slice the directory list based on the specified range
directory_subset = directory_list[low_range:upper_range]

print(directory_subset)

working_directory = f'working_directory_{run_number}'
results_directory = f'results_{run_number}'  # will be created if not present 

# Create the working directory if it doesn't exist
if not os.path.exists(working_directory):
    os.makedirs(working_directory)

# Copy all files from the source directory to the working directory
for file_name in os.listdir(model_directory):
    source_file = os.path.join(model_directory, file_name)
    if os.path.isfile(source_file):
        shutil.copy(source_file, working_directory)
        
# Create the results directory if it doesn't exist
if not os.path.exists(results_directory):
    os.makedirs(results_directory)

# Function to correct invalid dates
def correct_invalid_dates(date_str):
    try:
        return pd.to_datetime(date_str)
    except ValueError:
        return pd.NaT

# Read shapefile 
shapefile= gpd.read_file(shapefile_path)

# Convert ID cols to int
shapefile['hru_nhm'] = shapefile['hru_nhm'].astype(int)
shapefile['seg_nhm'] = shapefile['seg_nhm'].astype(int)

# Create dictionary for IDs
id_dict = dict(zip(shapefile['hru_nhm'], shapefile['seg_nhm']))

# List all CSV files in the directory
csv_files = [file for file in os.listdir(bias_corr_directory) if file.endswith('.csv')]

# Iterate through each directory in the directory_subset
for directory in directory_subset:
    
    # Exclude .ipynb_checkpoints directory
    if directory == ".ipynb_checkpoints":
        continue
    directory_path = os.path.join(forcings_directory, directory)

    # Extract the two-digit number from the directory name using regular expression
    match = re.search(r'\d{2}', directory)  # This matches a two-digit number
    if match:
        directory_id_num = match.group(0)
        print(f"Extracted number: {directory_id_num}")
    else:
        print(f"No two-digit number found in directory: {directory}")
        continue  # Skip if no number is found
        
    if os.path.isdir(directory_path):
        # Open and concatenate the files using open_mfdataset
        combined_dataset = xr.open_mfdataset(os.path.join(directory_path, file_pattern), combine="by_coords")
        
        # Extract the number from the directory name
        directory_number = re.findall(r'\d+', directory)[0]
        
        print(f'Beginning run for cmip: {directory_number}')
        
        # Extract forcings as dataframes
        precipitation_df = combined_dataset['precipitation'].to_dataframe()  # in kg/m2/s
        tmax_df = combined_dataset['max_temperature'].to_dataframe()  # in kelvin
        tmin_df = combined_dataset['min_temperature'].to_dataframe()  # in kelvin

        # Pivot forcing dataframes to match HYPE input format
        precipitation_pivoted = precipitation_df.reset_index().pivot(index='time', columns='ID', values='precipitation')
        tmax_pivoted = tmax_df.reset_index().pivot(index='time', columns='ID', values='max_temperature')
        tmin_pivoted = tmin_df.reset_index().pivot(index='time', columns='ID', values='min_temperature')

        # Convert column headers to integers
        precipitation_pivoted.columns = [int(col) for col in precipitation_pivoted.columns]
        tmax_pivoted.columns = [int(col) for col in tmax_pivoted.columns]
        tmin_pivoted.columns = [int(col) for col in tmin_pivoted.columns]
     
        print(f'Forcings reformated for cmip: {directory_number}')

        # Convert tmax and tmin from kelvin to celsius
        tmax_celsius = tmax_pivoted - 273.15
        tmin_celsius = tmin_pivoted - 273.15

        # Write tobs as the mean of tmax and tmin
        tobs_celsius = (tmax_celsius + tmin_celsius) / 2

        # Convert p from kg/m2/s to mm/day
        precipitation_mm = precipitation_pivoted * 3600 * 24 / 1000 * 1000  # convert s to day, divide by density 1000 kg/m3, multiply by 1000mm in 1 m

        os.chdir(working_directory)
        
        # Convert cftime objects to string format
        precipitation_mm.index = [date.strftime('%Y-%m-%d') for date in precipitation_mm.index]
        tmax_celsius.index = [date.strftime('%Y-%m-%d') for date in tmax_celsius.index]
        tmin_celsius.index = [date.strftime('%Y-%m-%d') for date in tmin_celsius.index]
        tobs_celsius.index = [date.strftime('%Y-%m-%d') for date in tobs_celsius.index]

        # Function to check if a date string is invalid (02-29 or 02-30)
        def is_invalid_date(date_str):
            try:
                month_day = date_str[5:10]  # Extract MM-DD part of the date string
                if month_day in ['02-29', '02-30']: 
                    print("Invalid dates removed")
                    return True
                return False
            except:
                return True  # Treat any parsing issue as invalid

            # Reset the index to make it a column
        precipitation_mm.reset_index(inplace=True)
        tmax_celsius.reset_index(inplace=True)
        tmin_celsius.reset_index(inplace=True)
        tobs_celsius.reset_index(inplace=True)
        
        # Apply the function to filter out invalid dates
        invalid_dates = precipitation_mm['index'].apply(is_invalid_date)

        precipitation_mm_valid = precipitation_mm[~invalid_dates].copy() 
        tmax_celsius_valid = tmax_celsius[~invalid_dates].copy() 
        tmin_celsius_valid = tmin_celsius[~invalid_dates].copy() 
        tobs_celsius_valid = tobs_celsius[~invalid_dates].copy() # Keep only rows with valid dates
        
        
        # Convert the valid dates to datetime format
        precipitation_mm_valid['index'] = pd.to_datetime(precipitation_mm_valid['index'])
        tmax_celsius_valid['index'] = pd.to_datetime(tmax_celsius_valid['index'])
        tmin_celsius_valid['index'] = pd.to_datetime(tmin_celsius_valid['index'])
        tobs_celsius_valid['index'] = pd.to_datetime(tobs_celsius_valid['index'])

        # Set the valid dates as the index
        precipitation_mm_valid.set_index('index', inplace=True)
        tmax_celsius_valid.set_index('index', inplace=True)
        tmin_celsius_valid.set_index('index', inplace=True)
        tobs_celsius_valid.set_index('index', inplace=True)

        # set columns to numeric
        precipitation_mm_valid = precipitation_mm_valid.apply(pd.to_numeric, errors='coerce')
        tmax_celsius_valid = tmax_celsius_valid.apply(pd.to_numeric, errors='coerce')
        tmin_celsius_valid = tmin_celsius_valid.apply(pd.to_numeric, errors='coerce')
        tobs_celsius_valid = tobs_celsius_valid.apply(pd.to_numeric, errors='coerce')
        
        # Find the minimum and maximum dates in the DataFrame index
        min_date = precipitation_mm_valid.index.min()
        max_date = precipitation_mm_valid.index.max()

        # Ensure max_date includes the entire day of December 31
        # Add one day to max_date and then subtract one second to ensure we cover the entire last day
        max_date = pd.Timestamp(year=max_date.year, month=12, day=31)

        # Calculate the full expected date range, including both min_date and max_date
        expected_dates = pd.date_range(start=min_date, end=max_date, freq='D')

        # Identify missing dates by checking which expected dates are not in the DataFrame index
        missing_dates = expected_dates[~expected_dates.isin(precipitation_mm_valid.index)]
        
        if not missing_dates.empty:
            precipitation_mm_valid = precipitation_mm_valid.reindex(expected_dates)
            precipitation_mm_valid = precipitation_mm_valid.ffill().bfill()
            precipitation_mm_valid = precipitation_mm_valid.dropna()

            tmax_celsius_valid = tmax_celsius_valid.reindex(expected_dates)
            tmax_celsius_valid = tmax_celsius_valid.ffill().bfill()
            tmax_celsius_valid = tmax_celsius_valid.dropna()

            tmin_celsius_valid = tmin_celsius_valid.reindex(expected_dates)
            tmin_celsius_valid = tmin_celsius_valid.ffill().bfill()
            tmin_celsius_valid = tmin_celsius_valid.dropna()

            tobs_celsius_valid = tobs_celsius_valid.reindex(expected_dates)
            tobs_celsius_valid = tobs_celsius_valid.ffill().bfill()
            tobs_celsius_valid = tobs_celsius_valid.dropna()

            print("Missing dates filled")
        else:
            print("No missing dates")

            # Rename the index to 'time'
        precipitation_mm_valid = precipitation_mm_valid.rename_axis('time')
        tmax_celsius_valid = tmax_celsius_valid.rename_axis('time')
        tmin_celsius_valid = tmin_celsius_valid.rename_axis('time')
        tobs_celsius_valid = tobs_celsius_valid.rename_axis('time')

        if remove_drizzle == True:
            precipitation_mm_valid[precipitation_mm_valid < 1] = 0
            print('Removed drizzle in non-corrected precip')

            
        # # debug
        # # Trim to date range 1950-01-01 to 1993-12-31
        # start_date = '1950-01-01'
        # end_date = '1953-12-31'
        
        # precipitation_mm_valid = precipitation_mm_valid.loc[start_date:end_date]
        # tmax_celsius_valid = tmax_celsius_valid.loc[start_date:end_date]
        # tmin_celsius_valid = tmin_celsius_valid.loc[start_date:end_date]
        # tobs_celsius_valid = tobs_celsius_valid.loc[start_date:end_date]
        
        # Save the DataFrame to a tab-separated text file
        tmax_celsius_valid.to_csv('TMAXobs.txt', sep='\t')
        tmin_celsius_valid.to_csv('TMINobs.txt', sep='\t')
        tobs_celsius_valid.to_csv('Tobs.txt', sep='\t')

        # If bias correction
        if perform_bias_corr == True:

            print('Preparing bias corrected precipitation forcing')
            # Find the file that contains the defined number in its name
            matching_file = None
            for file in csv_files:
                if directory_id_num in file:
                    matching_file = file
                    print(f'Matching file: {matching_file}')
                    break
            
            # Concatenate the full filepath
            file_path = os.path.join(bias_corr_directory, matching_file)
            
            # Read the bias corrected forcing
            df= pd.read_csv(file_path, index_col=0)
            
            # Convert the index to datetime
            df.index = pd.to_datetime(df.index)
            
            # Remove 'Basin_' prefix and convert column names to integers
            df.columns = df.columns.str.replace('Basin_', '', regex=False).astype(int)
            
            # Rename headers to HYPE basin ID
            df = df.rename(columns=id_dict)
            
            # Remove invalid dates
            # Function to check if a date is invalid (Feb 29 or Feb 30)
            def bc_is_invalid_date(date):
                try:
                    month_day = date.strftime('%m-%d')  # Get MM-DD string
                    if month_day in ['02-29', '02-30']:
                        print("Invalid date removed:", date)
                        return True
                    return False
                except Exception as e:
                    print("Error parsing date:", date, "-", e)
                    return True
            
            # Apply the invalid date check
            invalid_mask = df.index.to_series().apply(bc_is_invalid_date)
            
            # Report
            num_invalid = invalid_mask.sum()
            if num_invalid > 0:
                print(f"{num_invalid} invalid dates removed.")
            else:
                print("No invalid dates found.")
            
            # Keep only valid dates
            df = df[~invalid_mask].copy()
            
            # Add back missing dates
            # Define full expected daily date range
            min_date = df.index.min()
            max_date = df.index.max()

            print("min_date:", min_date)
            print("max_date:", max_date)
            print("Type of min_date:", type(min_date))
            print("Type of max_date:", type(max_date))
                        
            # Define expected dates for that range
            expected_dates = pd.date_range(start=min_date, end=max_date, freq='D')
            
            # Identify the missing dates
            missing_dates = expected_dates.difference(df.index)
            
            # Add the missign dates and backfill them
            if not missing_dates.empty:
                print(f"{len(missing_dates)} missing dates found. Filling...")
            
                df = df.reindex(expected_dates)
            
                # Use the updated, preferred syntax
                df = df.ffill().bfill()

            # Step 1: Convert entries like '0.0023+0i' to complex numbers
            def safe_to_complex(x):
                try:
                    return complex(str(x).replace(" ", "").replace("+0i", "+0j").replace("i", "j"))
                except ValueError:
                    return np.nan
            
            df = df.applymap(safe_to_complex)
            
            # Step 2: Strip imaginary parts (warn if imag ≠ 0)
            def check_and_strip_complex(x):
                if isinstance(x, complex):
                    if x.imag != 0:
                        print(f"⚠️ Warning: Found complex number with non-zero imaginary part: {x}")
                    return x.real
                return x
            
            df = df.applymap(check_and_strip_complex)

            # Reformat data
            df = df.astype(float)
            df.fillna(0, inplace=True)
                
            if remove_drizzle == True:
                df[df < 1] = 0
                print('Removed drizzle in bias corrected precip')
            
            # Rename the index
            df.index.name = "time"

            # # Trim to date range 1950-01-01 to 1993-12-31
            # start_date = '1950-01-01'
            # end_date = '1953-12-31'
            
            # df = df.loc[start_date:end_date]
            
            # Save to a tab-separated file
            df.to_csv("Pobs.txt", sep="\t")

            print('Running bias corrected forcings')

        else:
            precipitation_mm_valid.to_csv('Pobs.txt', sep='\t')
            print('Running without bias correction')

        # Run HYPE
        try:
            subprocess.run(hype_executable, check=True)
            print("HYPE program executed successfully.")
        except subprocess.CalledProcessError as e:
            print("Error running HYPE program:", e)
            
        os.chdir(current_directory)

        # Get a list of all files in the working directory
        files = os.listdir(working_directory)
        
        # Find the name of any text file starting with "00" and "time" for both kinds of outputs
        matching_files = [file for file in files if (file.startswith("time") or file.startswith("00")) and file.endswith(".txt")]


        # Rename each file by adding the directory name as a prefix
        for file in matching_files:
            # Construct the new file name with the directory name as a prefix
            new_file_name = os.path.join(working_directory, f"{directory_number}_{file}")

            # Rename the file
            os.rename(os.path.join(working_directory, file), new_file_name)
        
                # Move files starting with directory_number in working_directory to results_directory
        for file in os.listdir(working_directory):
            if file.startswith(directory_number):
                shutil.move(os.path.join(working_directory, file), os.path.join(results_directory, file))
                
        print(f'End of run for cmip: {directory_number}')

# Delete the working directory
# shutil.rmtree(working_directory)