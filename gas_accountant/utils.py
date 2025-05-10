import numpy as np
import random
import os
import pandas as pd

def set_global_seed(env, seed=20):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)

def convert_numpy(obj):
    if isinstance(obj, np.integer):
        return int(obj)  # Convert np.int64 → int
    elif isinstance(obj, np.floating):
        return float(obj)  # Convert np.float64 → float
    elif isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}  # Convert dict values
    elif isinstance(obj, list):
        return [convert_numpy(i) for i in obj]  # Convert list elements
    return obj  # Return original if not NumPy type

def normalize_portfolio(portfolio):
    total = np.sum(portfolio)
    if total == 0:
        # If the total is zero, avoid division by zero and return an equally distributed portfolio
        return np.ones_like(portfolio) / len(portfolio)
    return portfolio / total

def to_time(df):
    time_cols = ['date','dt','hour','time','day','month','year','week','timestamp','date(utc)','block_timestamp']
    for col in df.columns:
        if col.lower() in time_cols and col.lower() != 'timestamp':
            df[col] = pd.to_datetime(df[col])
            df.set_index(col, inplace=True)
        elif col.lower() == 'timestamp':
            df[col] = pd.to_datetime(df[col], unit='ms')
            df.set_index(col, inplace=True)
    print(df.index)
    return df 

def clean_prices(prices_df):
    print('cleaning prices')
    # Pivot the dataframe
    breakpoint()
    prices_df = prices_df.drop_duplicates(subset=['hour', 'symbol'])
    prices_df_pivot = prices_df.pivot(
        index='hour',
        columns='symbol',
        values='price'
    )
    prices_df_pivot = prices_df_pivot.reset_index()

    # Rename the columns by combining 'symbol' with a suffix
    prices_df_pivot.columns = ['dt'] + [f'{col}_price' for col in prices_df_pivot.columns[1:]]
    
    print(f'cleaned prices: {prices_df_pivot}')
    return prices_df_pivot

def data_processing(df,dropna=True):
    df.columns=df.columns.str.lower()
    clean_df = clean_prices(df)
    clean_df = to_time(clean_df)
    if dropna == True:
        clean_df = clean_df.dropna(axis=1, how='any')

    if '__row_index' in clean_df.columns:
        clean_df.drop(columns=['__row_index'], inplace=True)

    return clean_df